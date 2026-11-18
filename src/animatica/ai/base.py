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


def _recover_json(text: str) -> str | None:
    """Repair common model truncations: a missing ':' after a key, an
    unterminated string, or brackets left open at the end of the output.

    Brackets and quotes inside strings are ignored. Returns the repaired
    text, or None when the bracket structure is beyond repair.
    """
    out: list[str] = []
    stack: list[str] = []
    in_string = escaped = False
    prev = ""  # last significant char outside strings
    before_string = ""
    for i, ch in enumerate(text):
        if in_string:
            out.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
                # A string in key position ({ or , before it) must be
                # followed by ':'; models sometimes drop it after a long value.
                j = i + 1
                while j < len(text) and text[j].isspace():
                    j += 1
                if before_string in "{," and j < len(text) and text[j] not in ":,]}":
                    out.append(":")
                prev = '"'
            continue
        if ch.isspace():
            out.append(ch)
            continue
        if ch == '"':
            before_string = prev
            in_string = True
            out.append(ch)
            prev = '"'
        elif ch in "{[":
            stack.append("}" if ch == "{" else "]")
            out.append(ch)
            prev = ch
        elif ch in "}]":
            if not stack or stack.pop() != ch:
                return None
            out.append(ch)
            prev = ch
        else:
            out.append(ch)
            prev = ch
    if in_string:
        # A string cut mid-value stays an error (tests/test_extract_json.py):
        # closing it would invent text the model never produced.
        return None
    if stack:
        out.extend(reversed(stack))
    recovered = "".join(out)
    return recovered if recovered != text else None


def _cuts_trailing_prose(text: str) -> str | None:
    """Drop everything after the last complete object, when there is one."""
    end = text.rfind("}")
    return text[: end + 1] if end > 0 else None


def _loads_object(text: str) -> dict:
    """json.loads for one object, repairing the usual malformed-output shapes."""
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        for candidate in (_recover_json(text), _cuts_trailing_prose(text),
                          _close_open_brackets(text)):
            if not candidate or candidate == text:
                continue
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                continue
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
    body = text[start:].rstrip()
    try:
        return _loads_object(body)
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


class ProviderUnreachable(ProviderError):
    """The request never got an answer (DNS failure, refused connection, timeout)."""


class EmptyCompletion(ProviderError):
    """The provider answered HTTP 200 but the message had no text in it."""


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
            raise ProviderUnreachable(f"{self.name}: request failed: {exc}") from exc
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

    def _chat_text(self, url: str, headers: dict, payload: dict, attempts: int = 2) -> str:
        """POST a chat completion and return the reply text.

        An empty reply is retried once, because it is usually a one-off. When
        the reply was cut off by the token limit (a reasoning model that spent
        its whole budget thinking), the retry doubles ``max_tokens`` up to
        ``RETRY_MAX_TOKENS_CAP`` -- resending the identical request would just
        fail the same way. If it is still empty, raises `EmptyCompletion`
        saying why.
        """
        reason = ""
        for _ in range(attempts):
            data = self._post(url, headers, payload).json()
            try:
                text = _message_text(data["choices"][0]["message"])
            except (KeyError, IndexError, TypeError):
                text = ""
            if text.strip():
                return text
            reason = _empty_reason(data)
            if _finish_reason(data) == "length" and "max_tokens" in payload:
                payload = {**payload, "max_tokens": min(payload["max_tokens"] * 2, RETRY_MAX_TOKENS_CAP)}
        raise EmptyCompletion(
            f"{self.name}: empty reply after {attempts} attempt(s) ({reason}; model: {self.model!r})"
        )


def _message_text(message: object) -> str:
    """Text of one chat-completion message; "" when it has none.

    `content` is null when a reasoning model spends its whole token budget
    thinking, or when the answer is filtered. Some servers send a list of parts.
    """
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            part.get("text", "") for part in content
            if isinstance(part, dict) and isinstance(part.get("text"), str)
        )
    return ""


#: Hosted NIM lists 32768 as the maximum output for Nemotron 3 Super; the
#: other providers accept at least this much for the models we ship.
RETRY_MAX_TOKENS_CAP = 32768


def _finish_reason(data: object) -> str | None:
    try:
        return data["choices"][0].get("finish_reason")  # type: ignore[index]
    except (KeyError, IndexError, TypeError, AttributeError):
        return None


def _empty_reason(data: object) -> str:
    try:
        choice = data["choices"][0]  # type: ignore[index]
    except (KeyError, IndexError, TypeError):
        return "no choices in the response"
    bits = [f"finish_reason={choice.get('finish_reason')!r}"]
    message = choice.get("message") or {}
    if message.get("reasoning_content") or message.get("reasoning"):
        bits.append("the model returned reasoning but no answer, so it likely ran out of max_tokens")
    return ", ".join(bits)


def _openrouter_allow_paid() -> bool:
    import tomllib

    toml_path = Path(__file__).resolve().parent / "providers.toml"
    try:
        data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
        return bool(data.get("openrouter", {}).get("allow_paid", False))
    except Exception:
        return False

