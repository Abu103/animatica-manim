"""Number grounding (design 5.2): words must agree with the numbers drawn.

Every number in a beat's caption and narration is looked up in that beat's
own params and fact values, the params and fact values of earlier beats in
the same scene, and the storyboard title. Earlier captions and narration
never ground anything, so an invented figure cannot launder its repeat.
The check is consistency, not truth: it knows what the code drew, not
whether the model's claim is correct. No Manim here.
"""
from __future__ import annotations

import re
from typing import Any

from animatica.verify import Finding
from animatica.verify.facts import facts_for, format_number, parse_number

#: A digit token: grouped thousands, decimals, and an optional %/x/k/K/M/B
#: suffix. The lookarounds keep it out of words ("3D", "2nd"), out of the
#: middle of other numbers ("234" inside "1,234", "28" in "6.28"), and out
#: of identifier arguments ("fib(0)" is a name, not a number in prose).
_DIGIT_TOKEN = re.compile(
    r"(?<![\w.,])(?<!\w\()(?P<sign>-)?(?P<digits>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d+))?"
    r"(?P<suffix>%|x|[kKMB])?(?![\w])"
)

#: Number words (design 5.2): zero to twenty plus hundred, thousand, million.
_WORD_VALUE = {
    "zero": 0.0, "one": 1.0, "two": 2.0, "three": 3.0, "four": 4.0,
    "five": 5.0, "six": 6.0, "seven": 7.0, "eight": 8.0, "nine": 9.0,
    "ten": 10.0, "eleven": 11.0, "twelve": 12.0, "thirteen": 13.0,
    "fourteen": 14.0, "fifteen": 15.0, "sixteen": 16.0, "seventeen": 17.0,
    "eighteen": 18.0, "nineteen": 19.0, "twenty": 20.0,
    "hundred": 100.0, "thousand": 1000.0, "million": 1e6,
}
_WORD_TOKEN = re.compile(r"\b(" + "|".join(_WORD_VALUE) + r")\b", re.IGNORECASE)

#: "one" and "two" are never flagged (owner decision: err toward not
#: flagging; "two peaks" is a legitimate phrase). Adjacent number tokens
#: ("three hundred", "2.5 million", "twenty-one") are skipped entirely:
#: compounds cannot be parsed reliably, and the anti-goal is over-rejecting.
_FREE_WORDS = {"one", "two"}
_MULTIPLIERS = {"k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9}
#: Magnitude phrasing: a number right after one of these words names the
#: size of a signed decrease ("fell by 4", "down 4"), so a param of -4
#: grounds it. Applied only to that number, never to numbers elsewhere.
_DECREASE_BEFORE = re.compile(
    r"\b(?:fell|fall|dropped|drop|decreased|decrease|declined|decline|slipped|down|lost|lose)"
    r"\b(?:\s+\w+ly)?(?:\s+by)?\s+$"
    r"|\b(?:a\s+)?(?:drop|decline|decrease)\s+of\s+$",
    re.IGNORECASE,
)

#: Same sentence boundary as claims.py: the unchecked list is sentence-based.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _sentence_spans(text: str) -> list[tuple[int, int, str]]:
    """(start, end, sentence) spans that match ``_SENTENCE_SPLIT.split``."""
    spans: list[tuple[int, int, str]] = []
    start = 0
    for m in _SENTENCE_SPLIT.finditer(text):
        spans.append((start, m.start(), text[start:m.start()]))
        start = m.end()
    spans.append((start, len(text), text[start:]))
    return spans


def _sentence_at(pos: int, spans: list[tuple[int, int, str]]) -> str:
    """The sentence containing character position ``pos``."""
    return next((s for a, b, s in spans if a <= pos < b), "")


def _digit_value(m: Any) -> float:
    # parse_number owns the number semantics (sign, grouped thousands,
    # decimals, %/x suffixes and k/K/M/B multipliers): do not reimplement
    # them here or grounding can drift from the facts it checks.
    shared = parse_number(m.group(0))
    if shared is not None:
        return shared
    digits = m.group("digits").replace(",", "")
    value = float(digits + ("." + m.group("frac") if m.group("frac") else ""))
    suffix = m.group("suffix")
    if suffix in _MULTIPLIERS:
        value *= _MULTIPLIERS[suffix]
    return value


def _collect(obj: Any, out: set[float]) -> None:
    """Every number reachable in a params tree or fact value, recursively."""
    if obj is None or isinstance(obj, bool):
        return
    if isinstance(obj, (int, float)):
        out.add(float(obj))
    elif isinstance(obj, str):
        for m in _DIGIT_TOKEN.finditer(obj):
            value = _digit_value(m)
            out.add(value)
            suffix = m.group("suffix")
            if suffix in _MULTIPLIERS:  # "2.5M" also grounds 2.5
                out.add(float(m.group("digits").replace(",", "")
                              + ("." + m.group("frac") if m.group("frac") else "")))
            if suffix == "%":  # "12%" also grounds 0.12
                out.add(value / 100)
    elif isinstance(obj, (list, tuple, set)):
        for item in obj:
            _collect(item, out)
    elif isinstance(obj, dict):
        for item in obj.values():
            _collect(item, out)


def _sources_for(sb: Any, scene: Any, si: int, index: int, registry: Any,
                 facts_map: dict[tuple[int, int], list] | None) -> set[float]:
    """Params and fact values of this beat and every earlier one, plus the title."""
    out: set[float] = set()
    _collect(sb.title, out)
    for bi, beat in enumerate(scene.beats[: index + 1]):
        _collect(beat.params, out)
        if facts_map is not None:
            facts = facts_map.get((si, bi), [])
        else:
            facts = facts_for(registry, beat)
        for fact in facts:
            _collect(fact.value, out)
    return out


def _grounded(value: float, decimals: int, sources: set[float], percent: bool) -> bool:
    """Equal after rounding to the decimals written in the text.

    A percent matches a source of ``v`` or ``v * 100`` ("12%" is grounded
    by 12 or by 0.12).
    """
    target = round(value, decimals)
    for source in sources:
        if round(source, decimals) == target:
            return True
        if percent and round(source * 100, decimals) == target:
            return True
    return False


def _compounded(spans: list[tuple[int, int]], i: int, text: str) -> bool:
    """True when token ``i`` sits right next to another number token.

    The gap may only be spaces or a hyphen ("three hundred", "2.5 million",
    "twenty-one"); those compounds are left unchecked rather than
    half-checked.
    """
    for j in (i - 1, i + 1):
        if not 0 <= j < len(spans):
            continue
        gap = text[spans[j][1]: spans[i][0]] if j < i else text[spans[i][1]: spans[j][0]]
        if gap and all(c in " -" for c in gap):
            return True
    return False


def scan_numbers(sb: Any, registry: Any,
                 facts_map: dict[tuple[int, int], list] | None = None,
                 skipped: set[tuple[int, int]] | None = None,
                 checked_sentences: set[tuple[int, int, str]] | None = None) -> tuple[int, list[Finding]]:
    """Numbers checked and findings, in beat order. V1e uses the count.

    ``facts_map`` carries facts computed once per beat by verify_storyboard;
    beats in ``skipped`` (facts failed or params invalid) are unchecked.
    ``checked_sentences``, when given, receives ``(scene, beat, sentence)`` for
    every number actually examined, so the report can stop calling a sentence
    "unchecked" just because no claim rule looked at it. The public return
    type is unchanged.
    """
    findings: list[tuple[int, str, int, Finding]] = []
    checked = 0
    for si, scene in enumerate(sb.scenes):
        for bi, beat in enumerate(scene.beats):
            if skipped and (si, bi) in skipped:
                continue
            sources = _sources_for(sb, scene, si, bi, registry, facts_map)
            # A beat with no numeric source of its own cannot be expected to
            # ground a number: flag it as a warn (the model had nothing to
            # agree with). A beat that does have numbers is still an error.
            own_sources: set[float] = set()
            _collect(beat.params, own_sources)
            own_facts = facts_map.get((si, bi), []) if facts_map is not None else facts_for(registry, beat)
            for fact in own_facts:
                _collect(fact.value, own_sources)
            # A component with no facts implementation at all (title_card and
            # other text-only beats) cannot supply a number, so a number in
            # its caption is a warn. A numeric component whose instance has no
            # parseable value is still an error: the claim is invented, not
            # merely ungroundable (the V1c "laundering" case).
            numeric_capable = True
            try:
                from animatica.components.base import Component  # noqa: PLC0415

                numeric_capable = type(registry.get(beat.component)).facts is not Component.facts
            except Exception:  # pragma: no cover - unknown component already skipped
                pass
            severity = "warn" if (not own_sources and not numeric_capable) else "error"
            for field in ("caption", "narration"):
                text: str = getattr(beat, field)
                if not text:
                    continue
                digits = list(_DIGIT_TOKEN.finditer(text))
                words = list(_WORD_TOKEN.finditer(text))
                spans = sorted([(m.start(), m.end()) for m in digits + words])
                sentence_spans = _sentence_spans(text)
                pending: list[tuple[int, Finding]] = []
                for m in digits:
                    if _compounded(spans, spans.index((m.start(), m.end())), text):
                        continue
                    checked += 1
                    if checked_sentences is not None:
                        checked_sentences.add((si, bi, _sentence_at(m.start(), sentence_spans)))
                    value = _digit_value(m)
                    decimals = len(m.group("frac") or "")
                    percent = m.group("suffix") == "%"
                    # A decrease phrase fixes the sign: only -value may
                    # ground it, so +4 cannot explain "fell by 4".
                    if _DECREASE_BEFORE.search(text[max(0, m.start() - 40):m.start()]):
                        if _grounded(-value, decimals, sources, percent):
                            continue
                    elif _grounded(value, decimals, sources, percent):
                        continue
                    written = m.group(0)
                    pending.append((m.start(), Finding(
                        severity, (si, bi), field,
                        f'{field} says "{written}" but no param or computed fact '
                        f"for this beat equals {format_number(value)}",
                    )))
                for m in words:
                    word = m.group(1).lower()
                    if word in _FREE_WORDS:
                        continue
                    # A word number that opens a sentence announces a count
                    # ("Three steps.", "Four simple steps.") that may refer
                    # to content later in the storyboard, which grounding
                    # cannot see: never flag it.
                    if m.start() == 0 or text[max(0, m.start() - 2):m.start()] == ". ":
                        continue
                    if _compounded(spans, spans.index((m.start(), m.end())), text):
                        continue
                    checked += 1
                    if checked_sentences is not None:
                        checked_sentences.add((si, bi, _sentence_at(m.start(), sentence_spans)))
                    value = _WORD_VALUE[word]
                    if _DECREASE_BEFORE.search(text[max(0, m.start() - 40):m.start()]):
                        if _grounded(-value, 0, sources, False):
                            continue
                    elif _grounded(value, 0, sources, False):
                        continue
                    pending.append((m.start(), Finding(
                        severity, (si, bi), field,
                        f'{field} says "{m.group(1)}" but no param or computed fact '
                        f"for this beat equals {format_number(value)}",
                    )))
                findings.extend((si, bi, start, f) for start, f in pending)
    findings.sort(key=lambda item: (item[0], item[1], item[2]))
    return checked, [f for _, _, _, f in findings]


def check_numbers(sb: Any, registry: Any) -> list[Finding]:
    """Ungrounded numbers in captions and narration (design 5.2)."""
    return scan_numbers(sb, registry)[1]


__all__ = ["check_numbers", "scan_numbers"]
