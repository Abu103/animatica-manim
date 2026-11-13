"""AI provider protocol, JSON extraction, and storyboard generation error."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Protocol, runtime_checkable

import httpx


@runtime_checkable
class AIProvider(Protocol):
    """Provider that turns a prompt into a storyboard JSON string."""

    name: str

    def generate(self, prompt: str, schema: dict) -> str:
        """Return a JSON string (possibly wrapped in markdown fences/prose)."""


class StoryboardGenerationError(Exception):
    """Raised when the provider cannot produce a valid storyboard after retries."""

    def __init__(self, message: str, errors: list[str]):
        super().__init__(message)
        self.errors = errors


_FENCE = re.compile(r"```(?:json)?\s*\n?(.*?)\n?\s*```", re.DOTALL | re.IGNORECASE)


def _close_open_brackets(text: str) -> str | None:
    """Return `text` plus the closers it is missing, or None if it is not a cut-off object.

    Models sometimes stop one `}` or `]` short (or hit their token limit right after a value).
    Brackets inside strings do not count. Text that ends inside a string cannot be repaired.
    """
    stack: list[str] = []
    in_string = escaped = False
    for ch in text:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
        elif ch in "}]":
            if not stack or stack.pop() != ch:
                return None
    if in_string or not stack:
        return None
    return text + "".join(reversed(stack))


def _balanced_end(text: str, start: int) -> int | None:
    """Index just past the object that opens at `start`, ignoring brackets inside strings."""
    depth = 0
    in_string = escaped = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
        elif ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return i + 1
    return None


def _loads_object(text: str) -> dict:
    """json.loads for one object, finishing it when the model left closing brackets off."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        closed = _close_open_brackets(text)
        if closed is None:
            raise
        try:
            return json.loads(closed)
        except json.JSONDecodeError:
            raise exc from None


def extract_json(text: str) -> dict:
    """Extract the first JSON object from `text`.

    Handles markdown fences (with or without the ``json`` tag), leading/trailing
    prose, and the first balanced `{...}` block. If the object is cut off, with
    only closing brackets missing, they are added. Raises `ValueError` if none.
    """
    if not isinstance(text, str):
        raise ValueError(f"provider output must be a string, got {type(text).__name__}")
    m = _FENCE.search(text)
    if m:
        return _loads_object(m.group(1))
    start = text.find("{")
    if start == -1:
        raise ValueError("no JSON object found in provider output")
    end = _balanced_end(text, start)
    if end is not None:
        return _loads_object(text[start:end])
    closed = _close_open_brackets(text[start:].rstrip())
    if closed is not None:
        try:
            return json.loads(closed)
        except json.JSONDecodeError:
            pass
    raise ValueError("JSON object is cut off or has unbalanced brackets (end of output reached before it was closed)")


class RateLimited(Exception):
    """Raised when a provider returns HTTP 429."""

    def __init__(self, retry_after: float | None = None):
        self.retry_after = retry_after
        msg = f"rate limited; retry after {retry_after}s" if retry_after else "rate limited"
        super().__init__(msg)


class ProviderError(Exception):
    """Raised when a provider request fails for a clear, nameable reason."""


class BaseProvider:
    name: str = ""
    base_url: str = ""
    default_model: str = ""
    needs_key: bool = True

    def __init__(self, client: httpx.Client | None = None, model: str | None = None):
        self._client = client or httpx.Client(timeout=60.0)
        self.model = model or os.environ.get("ANIMATICA_MODEL") or self.default_model

    def _post(self, url: str, headers: dict, payload: dict) -> httpx.Response:
        try:
            resp = self._client.post(url, headers=headers, json=payload)
        except httpx.RequestError as exc:  # pragma: no cover - network
            raise ProviderError(f"{self.name}: request failed: {exc}") from exc
        if resp.status_code == 429:
            retry_after = None
            raw = resp.headers.get("retry-after")
            if raw:
                try:
                    retry_after = float(raw)
                except ValueError:
                    retry_after = None
            raise RateLimited(retry_after=retry_after)
        if resp.status_code >= 400:
            hint = ""
            if resp.status_code in (400, 404, 410):
                hint = (
                    f" (model: {payload.get('model')!r}; if the model was renamed or retired, "
                    "pass --model <id> or set ANIMATICA_MODEL)"
                )
            raise ProviderError(
                f"{self.name}: HTTP {resp.status_code}: {(resp.text or '')[:200]}{hint}"
            )
        return resp


def _openrouter_allow_paid() -> bool:
    import tomllib

    toml_path = Path(__file__).resolve().parent / "providers.toml"
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        return bool(data.get("openrouter", {}).get("allow_paid", False))
    except Exception:
        return False

