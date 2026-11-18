"""Compute-and-verify: facts, number grounding and claim checks.

Nothing in this package imports Manim: it is imported by the pipeline, the
report and the tests, and it must stay cheap and renderer-free.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Finding:
    """One failed check, addressed to the beat and field that caused it.

    ``severity`` is ``"error"`` (V2 sends it back to the model) or ``"warn"``
    (shown in the report only). ``beat`` is a ``(scene_index, beat_index)``
    pair, both 0-based. ``field`` is ``"caption"``, ``"narration"`` or
    ``"params"``. ``message`` is written for a model: it names the claim, the
    computed value and what is missing.
    """

    severity: str
    beat: tuple[int, int]
    field: str
    message: str


@dataclass(frozen=True)
class VerifyResult:
    """Everything one verify pass produced; the report block is built from it."""

    findings: list[Finding]
    #: Numbers looked at plus claim patterns examined (design 5.7).
    checked: int
    #: Sentences (and fact-failure notes) nobody could check, in beat order.
    unchecked: list[str] = field(default_factory=list)
    #: {"error": n, "warn": n}
    by_severity: dict[str, int] = field(default_factory=dict)


class VerifyStrictError(RuntimeError):
    """Raised by the pipeline under ``--strict`` when error findings survive.

    The report is written before this is raised; the message carries the
    counts and never claims the findings were right.
    """

    def __init__(self, result: VerifyResult) -> None:
        errors = result.by_severity.get("error", 0)
        warns = result.by_severity.get("warn", 0)
        super().__init__(
            f"strict: {errors} verify error(s), {warns} warning(s) survived "
            f"after {result.checked} check(s); see report.json"
        )


def verify_storyboard(sb, registry) -> VerifyResult:
    """Run number grounding (5.2) and claim checks (5.3) over a storyboard.

    Facts are computed exactly once per beat per run and shared by both
    checks. A beat whose facts could not be computed (params invalid or
    facts() raising) counts as unchecked, never passed. Never raises.
    """
    from animatica.verify.claims import scan_claims, unchecked_sentences  # noqa: PLC0415
    from animatica.verify.facts import try_facts  # noqa: PLC0415
    from animatica.verify.numbers import scan_numbers  # noqa: PLC0415

    facts_map: dict[tuple[int, int], list] = {}
    skipped: dict[tuple[int, int], str] = {}
    for si, scene in enumerate(sb.scenes):
        for bi, beat in enumerate(scene.beats):
            facts, note = try_facts(registry, beat)
            facts_map[(si, bi)] = facts
            if note:
                skipped[(si, bi)] = note
    checked_sentences: set[tuple[int, int, str]] = set()
    n_numbers, number_findings = scan_numbers(sb, registry, facts_map, set(skipped), checked_sentences)
    n_claims, claim_findings = scan_claims(sb, registry, facts_map, set(skipped))
    unchecked = unchecked_sentences(sb, registry, facts_map, set(skipped), checked_sentences)
    findings = sorted(number_findings + claim_findings, key=lambda f: (f.beat, f.field))
    by_severity = {
        "error": sum(1 for f in findings if f.severity == "error"),
        "warn": sum(1 for f in findings if f.severity == "warn"),
    }
    notes = [f"scene {si} beat {bi} ({sb.scenes[si].beats[bi].component}): {note}"
             for (si, bi), note in sorted(skipped.items())]
    return VerifyResult(
        findings=findings,
        checked=n_numbers + n_claims,
        unchecked=[s for _, s in unchecked] + notes,
        by_severity=by_severity,
    )


__all__ = ["Finding", "VerifyResult", "VerifyStrictError", "verify_storyboard"]
