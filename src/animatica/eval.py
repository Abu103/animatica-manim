"""`animatica eval` -- deterministic eval harness (roadmap P1.2).

Runs reference prompts through storyboard generation and scores each one:
valid on first try, retries used, lint warnings, total duration. No LLM judging.
Supports single-provider (P1.2) and multi-provider comparison (Phase 2.1).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from animatica.ai.base import EmptyCompletion, ProviderUnreachable, StoryboardGenerationError
from animatica.ai.repair import generate_storyboard
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Storyboard


@dataclass
class EvalResult:
    prompt: str
    provider: str
    model: str  # actual model ID used by the provider
    valid_first_try: bool
    eventual_success: bool  # True if valid after any number of retries
    retries: int
    warnings: list[str] = field(default_factory=list)
    duration: float = 0.0
    error: str | None = None


@dataclass
class EvalSummary:
    results: list[EvalResult]

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def valid_first_try_count(self) -> int:
        return sum(1 for r in self.results if r.valid_first_try)

    @property
    def eventual_success_count(self) -> int:
        return sum(1 for r in self.results if r.eventual_success)

    @property
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.error is not None)

    @property
    def retry_success_count(self) -> int:
        """Succeeded only after one or more retries (not first try)."""
        return sum(1 for r in self.results if r.eventual_success and not r.valid_first_try)

    def by_provider(self, provider: str) -> list[EvalResult]:
        return [r for r in self.results if r.provider == provider]


def _duration(sb: Storyboard, registry: ComponentRegistry) -> float:
    total = 0.0
    for scene in sb.scenes:
        for beat in scene.beats:
            comp = registry.get(beat.component)
            total += comp.duration(comp.Params.model_validate(beat.params))
    return total


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40] or "prompt"


def _record(save_dir: Path, index: int, record: dict) -> None:
    """Write one prompt's raw outputs so a run can be replayed offline (T17 fixtures)."""
    save_dir.mkdir(parents=True, exist_ok=True)
    name = f"{_slug(record['provider'])}__{index:02d}-{_slug(record['prompt'])}.json"
    (save_dir / name).write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _eval_one(
    prompts: list[str],
    provider,
    registry: ComponentRegistry,
    max_retries: int,
    save_dir: Path | None = None,
) -> list[EvalResult]:
    """Generate a storyboard per prompt with a single provider and score it."""

    class _Counting:
        def __init__(self, inner):
            self._inner = inner
            self.name = getattr(inner, "name", "provider")
            self.model = getattr(inner, "model", "unknown")
            self.calls = 0
            self.responses: list[str] = []

        def generate(self, prompt, schema):
            self.calls += 1
            text = self._inner.generate(prompt, schema)
            self.responses.append(text)
            return text

    prov_name = getattr(provider, "name", "provider")
    prov_model = getattr(provider, "model", "unknown")
    results: list[EvalResult] = []
    for index, prompt in enumerate(prompts, start=1):
        prov = _Counting(provider)
        try:
            sb = generate_storyboard(prompt, prov, registry, max_retries=max_retries)
            raw_sb = sb.model_dump(mode="json")
            sb, notes = lint_storyboard(sb)
            results.append(EvalResult(
                prompt=prompt,
                provider=prov_name,
                model=prov_model,
                valid_first_try=prov.calls == 1,
                eventual_success=True,
                retries=prov.calls - 1,
                warnings=notes,
                duration=_duration(sb, registry),
            ))
            if save_dir is not None:
                _record(save_dir, index, {
                    "prompt": prompt, "provider": prov_name, "model": prov_model, "ok": True,
                    "calls": prov.calls, "storyboard": raw_sb, "responses": prov.responses,
                })
        except (StoryboardGenerationError, EmptyCompletion, ProviderUnreachable) as exc:
            results.append(EvalResult(
                prompt=prompt,
                provider=prov_name,
                model=prov_model,
                valid_first_try=False,
                eventual_success=False,
                retries=prov.calls - 1,
                error=str(exc),
            ))
            if save_dir is not None:
                _record(save_dir, index, {
                    "prompt": prompt, "provider": prov_name, "model": prov_model, "ok": False,
                    "calls": prov.calls, "error": str(exc), "errors": list(getattr(exc, "errors", [])),
                    "responses": prov.responses,
                })
    return results


def run_eval(
    prompts: list[str],
    provider,
    registry: ComponentRegistry | None = None,
    max_retries: int = 2,
    as_table: bool = False,
    save_dir: Path | None = None,
) -> list[EvalResult] | str:
    """Generate a storyboard per prompt and score it. Returns results (or a table)."""
    registry = registry or default_registry()
    results = _eval_one(prompts, provider, registry, max_retries, save_dir)
    if as_table:
        return format_table(results)
    return results


def run_eval_multi(
    prompts: list[str],
    providers: list,
    registry: ComponentRegistry | None = None,
    max_retries: int = 2,
    save_dir: Path | None = None,
) -> EvalSummary:
    """Run the same prompts through multiple providers and return a combined summary."""
    registry = registry or default_registry()
    all_results: list[EvalResult] = []
    for provider in providers:
        all_results.extend(_eval_one(prompts, provider, registry, max_retries, save_dir))
    return EvalSummary(results=all_results)


def format_table(results: list[EvalResult]) -> str:
    """Format eval results as a plain-text score table."""
    lines = [f"{'provider':<14} {'model':<20} {'prompt':<30} {'first':<6} {'eventual':<9} {'retries':<7} {'warn':<5} {'secs':<6}"]
    for r in results:
        err = f" ERROR: {r.error[:25]}" if r.error else ""
        first = "yes" if r.valid_first_try else "NO"
        eventual = "yes" if r.eventual_success else "NO"
        lines.append(
            f"{r.provider:<14} {r.model:<20} {r.prompt[:30]:<30} "
            f"{first:<6} {eventual:<9} {r.retries:<7} {len(r.warnings):<5} {r.duration:<6.1f}{err}"
        )
    ok = sum(1 for r in results if r.valid_first_try)
    eventual = sum(1 for r in results if r.eventual_success)
    retry_ok = sum(1 for r in results if r.eventual_success and not r.valid_first_try)
    errs = sum(1 for r in results if r.error is not None)
    lines.append(
        f"\n{ok}/{len(results)} first-try valid, {retry_ok} retry-valid, "
        f"{eventual}/{len(results)} eventual valid, {errs} errored"
    )
    return "\n".join(lines)


def format_multi_table(summary: EvalSummary) -> str:
    """Format multi-provider eval results as a comparison table."""
    providers = sorted({r.provider for r in summary.results})
    prompts = sorted({r.prompt for r in summary.results})

    # Header
    lines = [f"{'prompt':<38} " + " ".join(f"{p:<18}" for p in providers)]
    lines.append("-" * (38 + 19 * len(providers)))

    # One row per prompt, columns per provider
    for prompt in prompts:
        row = f"{prompt[:38]:<38}"
        for p in providers:
            result = next((r for r in summary.results if r.provider == p and r.prompt == prompt), None)
            if result is None:
                row += f"{'n/a':<18}"
            elif result.error:
                row += f"{'ERROR':<18}"
            else:
                status = "ok" if result.valid_first_try else f"r{result.retries}"
                row += f"{status:<18}"
        lines.append(row)

    # Summary row
    lines.append("-" * (38 + 19 * len(providers)))
    summary_row = f"{'VALID/Total':<38}"
    for p in providers:
        prov_results = summary.by_provider(p)
        ok = sum(1 for r in prov_results if r.valid_first_try)
        retry_ok = sum(1 for r in prov_results if r.eventual_success and not r.valid_first_try)
        errs = sum(1 for r in prov_results if r.error is not None)
        cell = f"{ok}/{len(prov_results)}" + (f" e{errs}" if errs else "")
        cell += f" ({retry_ok} retry)" if retry_ok else ""
        summary_row += cell.ljust(18)
    lines.append(summary_row)

    return "\n".join(lines)
