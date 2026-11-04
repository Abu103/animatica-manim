"""`animatica eval` -- deterministic eval harness (roadmap P1.2).

Runs reference prompts through storyboard generation and scores each one:
valid on first try, retries used, lint warnings, total duration. No LLM judging.
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
    valid_first_try: bool
    retries: int
    warnings: list[str] = field(default_factory=list)
    duration: float = 0.0
    error: str | None = None


def _duration(sb: Storyboard, registry: ComponentRegistry) -> float:
    total = 0.0
    for scene in sb.scenes:
        for beat in scene.beats:
            comp = registry.get(beat.component)
            total += comp.duration(comp.Params.model_validate(beat.params))
    return total


def run_eval(
    prompts: list[str],
    provider,
    registry: ComponentRegistry | None = None,
    max_retries: int = 2,
    as_table: bool = False,
) -> list[EvalResult] | str:
    """Generate a storyboard per prompt and score it. Returns results (or a table)."""
    registry = registry or default_registry()

    class _Counting:
        def __init__(self, inner):
            self._inner = inner
            self.name = getattr(inner, "name", "provider")
            self.calls = 0
        def generate(self, prompt, schema):
            self.calls += 1
            return self._inner.generate(prompt, schema)

    results: list[EvalResult] = []
    for prompt in prompts:
        prov = _Counting(provider)
        try:
            sb = generate_storyboard(prompt, prov, registry, max_retries=max_retries)
            sb, notes = lint_storyboard(sb)
            results.append(EvalResult(
                prompt=prompt,
                valid_first_try=prov.calls == 1,
                retries=prov.calls - 1,
                warnings=notes,
                duration=_duration(sb, registry),
            ))
        except StoryboardGenerationError as exc:
            results.append(EvalResult(
                prompt=prompt, valid_first_try=False, retries=prov.calls - 1,
                error=str(exc),
            ))
    if as_table:
        lines = [f"{'prompt':<40} {'valid':<6} {'retries':<7} {'warn':<5} {'secs':<6}"]
        for r in results:
            lines.append(
                f"{r.prompt[:40]:<40} {'yes' if r.valid_first_try else 'NO':<6} "
                f"{r.retries:<7} {len(r.warnings):<5} {r.duration:<6.1f}"
            )
        ok = sum(1 for r in results if r.valid_first_try)
        lines.append(f"\n{ok}/{len(results)} valid on generation")
        return "\n".join(lines)
    return results
