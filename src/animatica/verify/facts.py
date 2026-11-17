"""Facts: what a component draws, computed from its params alone.

A ``Fact`` is one checkable statement about a beat's picture. Components
build facts from the same pure data function their ``play()`` draws from, so
a fact cannot drift from the picture (design 5.1). No Manim here.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Fact:
    """One plain statement about a beat, for checking words against the picture."""

    kind: str  # "range" | "extremum" | "zero" | ... (see the task card)
    subject: str  # what it is about: "fn", "approx_fn", "bars", "final_state", ...
    value: object  # float | int | bool | str | tuple[float, ...]
    text: str  # one plain sentence, written for a model


def facts_for(registry: Any, beat: Any) -> list[Fact]:
    """Facts for one beat: the component's ``facts(params)`` after validation.

    Returns ``[]`` when the component is unknown, its params do not validate,
    it has no ``facts``, or computing them fails. Never raises: verification
    must not be able to break a run.
    """
    try:
        comp = registry.get(beat.component)
    except KeyError:
        return []
    try:
        params = comp.Params.model_validate(beat.params)
        facts = comp.facts(params)
        return list(facts)
    except Exception:
        return []


__all__ = ["Fact", "facts_for"]
