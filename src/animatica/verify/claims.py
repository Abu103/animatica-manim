"""Claim checks (design 5.3): the domain rule and a small pattern table.

The table is one list at the top of this file so the owner can read it. A
pattern runs only on a beat whose component produced the fact kind it
checks -- unknown phrasing is not checked, not guessed. No Manim here.
"""
from __future__ import annotations

import re
from typing import Any

from animatica.verify import Finding
from animatica.verify.facts import facts_for

#: Domain rule (5.3): only a spectrum-capable component may use this wording.
_DOMAIN_PATTERN = re.compile(
    r"frequency domain|frequency spectrum|\bspectrum\b|spectral|power spectrum",
    re.IGNORECASE,
)

#: The pattern table. Each row: (regex, component gate or None for "any
#: component that produced the row's fact kind", fact kind, severity).
#: - Peak counting sees only kind-"peak" facts (signal_spectrum, V3); a
#:   graph's time-domain maxima are kind-"extremum" and never feed it.
#: - "largest" is checked on bar_chart only when a bar label is named in the
#:   same sentence.
#: - "sorted" on array_viz warns when the final array is not sorted.
_PATTERNS: list[tuple[re.Pattern[str], str | None, str, str]] = [
    (re.compile(r"\b(\d+|two|three|four|five)\s+peaks?\b", re.IGNORECASE),
     None, "peak", "error"),
    (re.compile(r"\b(?:largest|biggest|highest|tallest)\b", re.IGNORECASE),
     "bar_chart", "extremum", "error"),
    (re.compile(r"\bsorted\b", re.IGNORECASE),
     "array_viz", "sorted", "warn"),
]
_COUNT_WORDS = {"two": 2, "three": 3, "four": 4, "five": 5}
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _fields(beat: Any) -> list[tuple[str, str]]:
    return [(field, getattr(beat, field)) for field in ("caption", "narration")
            if getattr(beat, field)]


def _frequency_capable(registry: Any) -> bool:
    return any(registry.get(name).domain == "frequency" for name in registry.names())


def check_claims(sb: Any, registry: Any,
                 facts_map: dict[tuple[int, int], list] | None = None,
                 skipped: set[tuple[int, int]] | None = None) -> list[Finding]:
    """Domain-rule and pattern-claim findings (design 5.3), in beat order."""
    return scan_claims(sb, registry, facts_map, skipped)[1]


def scan_claims(sb: Any, registry: Any,
                facts_map: dict[tuple[int, int], list] | None = None,
                skipped: set[tuple[int, int]] | None = None) -> tuple[int, list[Finding]]:
    """Matches examined and findings, in beat order. V1e uses the count."""
    findings: list[tuple[int, int, int, int, Finding]] = []
    checked = 0
    frequency_capable = _frequency_capable(registry)
    tail = ("use signal_spectrum" if frequency_capable
            else "no component currently draws a frequency spectrum")
    for si, scene in enumerate(sb.scenes):
        for bi, beat in enumerate(scene.beats):
            if skipped and (si, bi) in skipped:
                continue
            try:
                comp = registry.get(beat.component)
            except KeyError:
                continue
            if facts_map is not None:
                facts = facts_map.get((si, bi), [])
            else:
                facts = facts_for(registry, beat)
            pending: list[tuple[int, int, Finding]] = []
            if comp.domain == "plain axes":
                for field, text in _fields(beat):
                    for m in _DOMAIN_PATTERN.finditer(text):
                        checked += 1
                        pending.append((0, m.start(), Finding(
                            "error", (si, bi), field,
                            f'{field} says "{m.group(0)}" but {beat.component} '
                            f"draws plain axes, {tail}",
                        )))
            for regex, gate, kind, severity in _PATTERNS:
                if gate is not None and beat.component != gate:
                    continue
                for field, text in _fields(beat):
                    for m in regex.finditer(text):
                        finding = _check_pattern(m, severity, kind, facts,
                                                 (si, bi), field, regex)
                        if finding is not None or _pattern_actually_checked(kind, facts, m):
                            checked += 1
                        if finding is not None:
                            pending.append((1, m.start(), finding))
            findings.extend((si, bi, *item) for item in pending)
    findings.sort(key=lambda item: item[:4])
    return checked, [item[4] for item in findings]


def _pattern_actually_checked(kind: str, facts: list[Any], m: re.Match[str]) -> bool:
    """Whether the match was examined (vs left unchecked), for the checked count."""
    if kind == "peak":
        return any(f.kind == "peak" for f in facts)
    if kind == "extremum":
        labels = [f.value[0] for f in facts if f.kind == "value"]
        sentence = _sentence_of(m)
        return any(re.search(rf"\b{re.escape(label)}\b", sentence) for label in labels)
    if kind == "sorted":
        return any(f.kind == "sorted" for f in facts)
    return False


def _check_pattern(m: re.Match[str], severity: str, kind: str,
                   facts: list[Any], beat: tuple[int, int], field: str,
                   regex: re.Pattern[str]) -> Finding | None:
    """The claim behind one regex match, or None when it holds or cannot be checked."""
    if kind == "peak":
        peak_facts = [f for f in facts if f.kind == "peak"]
        if not peak_facts:  # the pattern only runs when peak facts exist
            return None
        word = m.group(1).lower()
        claimed = _COUNT_WORDS.get(word, float(word) if word.isdigit() else 0)
        computed = len(peak_facts)
        if claimed == computed:
            return None
        return Finding(severity, beat, field,
                       f'{field} says "{m.group(0)}" but the code computed '
                       f"{computed} peaks")
    if kind == "extremum":  # bar_chart: named labels only, in the same sentence
        sentence = _sentence_of(m)
        labels = [f.value[0] for f in facts if f.kind == "value"]
        largest = next((f.value[0] for f in facts
                        if f.kind == "extremum" and "largest" in f.text), None)
        if largest is None:
            return None
        named = [label for label in labels
                 if re.search(rf"\b{re.escape(label)}\b", sentence)]
        if not named or largest in named:
            return None
        return Finding(severity, beat, field,
                       f"{field} says the largest bar is {named[0]} "
                       f"but the largest bar is {largest}")
    if kind == "sorted":
        fact = next((f for f in facts if f.kind == "sorted"), None)
        if fact is None or fact.value is not False:
            return None
        return Finding(severity, beat, field,
                       f'{field} says "{m.group(0)}" but the final array is '
                       "not sorted in ascending order")
    return None


def _sentence_of(m: re.Match[str]) -> str:
    """The sentence a match sits in: the text between sentence boundaries."""
    text = m.string
    start = max(text.rfind(".", 0, m.start()), text.rfind("!", 0, m.start()),
                text.rfind("?", 0, m.start()))
    end = next((i for i in range(m.end(), len(text)) if text[i] in ".!?"), len(text))
    return text[start + 1:end]


def unchecked_sentences(sb: Any, registry: Any,
                        facts_map: dict[tuple[int, int], list] | None = None,
                        skipped: set[tuple[int, int]] | None = None) -> list[tuple[Any, str]]:
    """Caption/narration sentences that no rule above looked at.

    V1e reports the count only. Beats in ``skipped`` (facts failed or params
    invalid) were not checked at all: their sentences are unchecked too.
    """
    out: list[tuple[Any, str]] = []
    for si, scene in enumerate(sb.scenes):
        for bi, beat in enumerate(scene.beats):
            try:
                comp = registry.get(beat.component)
            except KeyError:
                comp = None
            if facts_map is not None:
                facts = facts_map.get((si, bi), [])
            else:
                facts = facts_for(registry, beat)
            has_peak_facts = any(f.kind == "peak" for f in facts)
            for field, text in _fields(beat):
                if skipped and (si, bi) in skipped:
                    out.append((beat, text))
                    continue
                for sentence in _SENTENCE_SPLIT.split(text):
                    if not sentence:
                        continue
                    if comp is not None and _looked_at(sentence, beat.component, comp,
                                                       facts, has_peak_facts):
                        continue
                    out.append((beat, sentence))
    return out


def _looked_at(sentence: str, component: str, comp: Any,
               facts: list[Any], has_peak_facts: bool) -> bool:
    if comp.domain == "plain axes" and _DOMAIN_PATTERN.search(sentence):
        return True
    for regex, gate, kind, _severity in _PATTERNS:
        if gate is not None and component != gate:
            continue
        m = regex.search(sentence)
        if m is None:
            continue
        if kind == "peak":
            return has_peak_facts
        if kind == "extremum":
            labels = [f.value[0] for f in facts if f.kind == "value"]
            return any(re.search(rf"\b{re.escape(label)}\b", sentence)
                       for label in labels)
        return True  # sorted: the rule looks at the sentence either way
    return False


__all__ = ["check_claims", "scan_claims", "unchecked_sentences"]
