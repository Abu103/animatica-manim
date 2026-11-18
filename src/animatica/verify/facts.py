"""Facts: what a component draws, computed from its params alone.

A ``Fact`` is one checkable statement about a beat's picture. Components
build facts from the same pure data function their ``play()`` draws from, so
a fact cannot drift from the picture (design 5.1). No Manim here.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

#: One plain number: optional sign and one real currency symbol, grouped
#: thousands, decimals, an optional k/K/M/B multiplier and %/x suffix.
#: No exponents ("1e3" is rejected) and no word multipliers ("12 million").
_NUMBER = re.compile(
    r"^\s*(?P<sign>[+-])?(?P<currency>[$€£¥₹])?\s*"
    r"(?P<digits>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d+))?"
    r"(?P<mult>[kKMB])?(?P<suffix>[%x])?\s*$"
)
_MULTIPLIERS = {"k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9}


@dataclass(frozen=True)
class Fact:
    """One plain statement about a beat, for checking words against the picture."""

    kind: str  # "range" | "extremum" | "zero" | ... (see the task card)
    subject: str  # what it is about: "fn", "approx_fn", "bars", "final_state", ...
    value: object  # float | int | bool | str | tuple[float, ...]
    text: str  # one plain sentence, written for a model


def parse_number(text: Any) -> float | None:
    """Parse a headline number, or return None. Never raises.

    A percent keeps its written value ("12%" is 12.0, not 0.12). A trailing
    'x' is a multiplier marker, not a unit conversion. Exponents and word
    multipliers are not supported; V1c uses this for number grounding.
    """
    if not isinstance(text, str):
        return None
    try:
        m = _NUMBER.match(text)
        if m is None:
            return None
        digits = m.group("digits").replace(",", "")
        number = float(digits + ("." + m.group("frac") if m.group("frac") else ""))
        if m.group("sign") == "-":
            number = -number
        if m.group("mult"):
            number *= _MULTIPLIERS[m.group("mult")]
        return number
    except (ValueError, OverflowError, TypeError):  # defensive: never break a run
        return None


def format_number(v: float) -> str:
    """Plain digits for a fact's text: no scientific notation, no trailing zeros."""
    return f"{v:.6f}".rstrip("0").rstrip(".")


def try_facts(registry: Any, beat: Any) -> tuple[list[Fact], str]:
    """Facts for one beat plus an error note; the note is empty on success.

    The note says why no facts could be computed (unknown component, params
    that do not validate, or ``facts()`` raising), so verify_storyboard can
    count such a beat as unchecked instead of passed. Never raises.
    """
    try:
        comp = registry.get(beat.component)
    except KeyError:
        return [], f"unknown component {beat.component!r}"
    try:
        params = comp.Params.model_validate(beat.params)
        return list(comp.facts(params)), ""
    except Exception as exc:  # verification must not be able to break a run
        return [], f"could not compute facts: {exc}"


def facts_for(registry: Any, beat: Any) -> list[Fact]:
    """Facts for one beat: the component's ``facts(params)`` after validation.

    Returns ``[]`` when the component is unknown, its params do not validate,
    it has no ``facts``, or computing them fails. Never raises: verification
    must not be able to break a run. Use :func:`try_facts` when the reason
    matters.
    """
    return try_facts(registry, beat)[0]


__all__ = ["Fact", "facts_for", "format_number", "parse_number", "try_facts"]
