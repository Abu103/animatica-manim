"""Compute-and-verify: facts, number grounding and claim checks.

Nothing in this package imports Manim: it is imported by the pipeline, the
report and the tests, and it must stay cheap and renderer-free.
"""
from __future__ import annotations

from dataclasses import dataclass


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


__all__ = ["Finding"]
