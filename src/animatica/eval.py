"""`animatica eval` -- deterministic eval harness (roadmap P1.2).

Runs reference prompts through storyboard generation and scores each one:
valid on first try, retries used, lint warnings, total duration. No LLM judging.
Supports single-provider (P1.2) and multi-provider comparison (Phase 2.1).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from animatica.ai.base import StoryboardGenerationError
from animatica.ai.repair import generate_storyboard
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Storyboard


@dataclass
class EvalResult:
    prompt: str
    provider: str
    valid_first_try: bool
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
    def error_count(self) -> int:
        return sum(1 for r in self.results if r.error is not None)

    def by_provider(self, provider: str) -> list[EvalResult]:
        return [r for r in self.results if r.provider == provider]


def _duration(sb: Storyboard, registry: ComponentRegistry) -> float:
    total = 0.0
    for scene in sb.scenes:
        for beat in scene.beats:
            comp = registry.get(beat.component)
            total += comp.duration(comp.Params.model_validate(beat.params))
    return total


def _eval_one(
    prompts: list[str],
    provider,
    registry: ComponentRegistry,
    max_retries: int,
) -> list[EvalResult]:
    """Generate a storyboard per prompt with a single provider and score it."""

    class _Counting:
        def __init__(self, inner):
            self._inner = inner
            self.name = getattr(inner, "name", "provider")
            self.calls = 0

        def generate(self, prompt, schema):
            self.calls += 1
            return self._inner.generate(prompt, schema)

    prov_name = getattr(provider, "name", "provider")
    results: list[EvalResult] = []
    for prompt in prompts:
        prov = _Counting(provider)
        try:
            sb = generate_storyboard(prompt, prov, registry, max_retries=max_retries)
            sb, notes = lint_storyboard(sb)
            results.append(EvalResult(
                prompt=prompt,
                provider=prov_name,
                valid_first_try=prov.calls == 1,
                retries=prov.calls - 1,
                warnings=notes,
                duration=_duration(sb, registry),
            ))
        except StoryboardGenerationError as exc:
            results.append(EvalResult(
                prompt=prompt,
                provider=prov_name,
                valid_first_try=False,
                retries=prov.calls - 1,
                error=str(exc),
            ))
    return results


def run_eval(
    prompts: list[str],
    provider,
    registry: ComponentRegistry | None = None,
    max_retries: int = 2,
    as_table: bool = False,
) -> list[EvalResult] | str:
    """Generate a storyboard per prompt and score it. Returns results (or a table)."""
    registry = registry or default_registry()
    results = _eval_one(prompts, provider, registry, max_retries)
    if as_table:
        return format_table(results)
    return results


def run_eval_multi(
    prompts: list[str],
    providers: list,
    registry: ComponentRegistry | None = None,
    max_retries: int = 2,
) -> EvalSummary:
    """Run the same prompts through multiple providers and return a combined summary."""
    registry = registry or default_registry()
    all_results: list[EvalResult] = []
    for provider in providers:
        all_results.extend(_eval_one(prompts, provider, registry, max_retries))
    return EvalSummary(results=all_results)


def format_table(results: list[EvalResult]) -> str:
    """Format eval results as a plain-text score table."""
    lines = [f"{'provider':<14} {'prompt':<36} {'valid':<6} {'retries':<7} {'warn':<5} {'secs':<6}"]
    for r in results:
        err = f" ERROR: {r.error[:30]}" if r.error else ""
        lines.append(
            f"{r.provider:<14} {r.prompt[:36]:<36} "
            f"{'yes' if r.valid_first_try else 'NO':<6} "
            f"{r.retries:<7} {len(r.warnings):<5} {r.duration:<6.1f}{err}"
        )
    ok = sum(1 for r in results if r.valid_first_try)
    errs = sum(1 for r in results if r.error is not None)
    lines.append(f"\n{ok}/{len(results)} valid on generation, {errs} errored")
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
        errs = sum(1 for r in prov_results if r.error is not None)
        cell = f"{ok}/{len(prov_results)}" + (f" e{errs}" if errs else "")
        summary_row += cell.ljust(18)
    lines.append(summary_row)

    return "\n".join(lines)
