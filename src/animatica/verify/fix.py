"""V2a: mechanical fixes that cannot change a beat's meaning.

Only one fix exists so far: a graph whose curve is clipped by its requested
``y_range``. The fix widens the window to the *unclipped* sample range with
10% padding; captions and narration are never rewritten. Applying the fixes
to their own output finds nothing (idempotent), so a ``--from`` re-run of the
written storyboard is stable.

This module imports no Manim: it reads facts and the graph's pure data helper.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from animatica.verify.facts import try_facts

#: A needed window this many times the requested *half* span (the room the
#: model asked for on each side) means an asymptote, not a mis-sized window.
#: tan(x) on (-1.5, 1.5) needs 28.20 against 10 * 2 = 20 of requested room, so
#: it is left as a finding; x**2 on (-2, 2) needs 4.0 against 10 * 0.5 = 5 and
#: is widened.
ASYMPTOTE_SPAN_RATIO = 10.0
#: Padding added to each side of the unclipped range, as a fraction of its span.
Y_RANGE_PADDING = 0.10


@dataclass(frozen=True)
class Fix:
    """One recorded, before/after change to a beat's params."""

    beat: tuple[int, int]
    field: str
    before: Any
    after: Any
    reason: str

    def as_dict(self) -> dict:
        d = asdict(self)
        d["beat"] = list(self.beat)  # JSON-friendly; beats are (scene, beat) pairs
        return d


def apply_fixes(sb: Any, registry: Any) -> tuple[Any, list[Fix]]:
    """Apply all mechanical fixes to ``sb`` in place; return it and the fixes.

    A clipped graph is widened to the unclipped finite sample range with 10%
    padding, rounded to 2 decimals. The fix is skipped when the needed window
    is more than ``ASYMPTOTE_SPAN_RATIO`` times the requested half span (an
    asymptote such as tan). Never raises: verification must not break a run.
    """
    from animatica.components.graph import unclipped_range  # noqa: PLC0415 - avoid a render-time import cycle

    fixes: list[Fix] = []
    for s_idx, scene in enumerate(sb.scenes):
        for b_idx, beat in enumerate(scene.beats):
            if beat.component != "graph":
                continue
            facts, note = try_facts(registry, beat)
            if note:
                continue
            clipped = next((f for f in facts if f.kind == "clipped"), None)
            if clipped is None or clipped.value is not True:
                continue
            try:
                comp = registry.get(beat.component)
                params = comp.Params.model_validate(beat.params)
                unclipped = unclipped_range(params)
                if unclipped is None:
                    continue
                lo, hi = unclipped
                span = hi - lo
                if span <= 0:
                    continue
                y0, y1 = params.y_range
                if span > ASYMPTOTE_SPAN_RATIO * ((y1 - y0) / 2):
                    continue  # an asymptote: widening would flatten the curve
                pad = Y_RANGE_PADDING * span
                after = [round(lo - pad, 2), round(hi + pad, 2)]
                before = list(beat.params.get("y_range", []))
                if after == before:
                    continue
                beat.params["y_range"] = after
                fixes.append(
                    Fix(
                        beat=(s_idx, b_idx),
                        field="y_range",
                        before=before,
                        after=after,
                        reason="graph curve is clipped by y_range; widened to the unclipped sample range with 10% padding",
                    )
                )
            except Exception:  # pragma: no cover - a fix must never break a run
                continue
    return sb, fixes


__all__ = ["Fix", "apply_fixes"]
