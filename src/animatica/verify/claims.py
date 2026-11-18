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

#: P1: a signal_spectrum axis is cycles per window, not hertz. A word match
#: (case-insensitive) warns without blocking the run.
_HERTZ_PATTERN = re.compile(
    r"\bhertz\b|\bkilohertz\b|\bmegahertz\b|\bgigahertz\b|\bHz\b|\bkHz\b|\bMHz\b|\bGHz\b",
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

#: Param-vs-claim checks (N5). Ordinal spike claims name 1-based term
#: positions; graph labels that name cost over an identity line claim data
#: the beat does not compute.
_ORDINALS = {
    "first": 1, "second": 2, "third": 3, "fourth": 4, "fifth": 5,
    "sixth": 6, "seventh": 7, "eighth": 8, "ninth": 9, "tenth": 10,
    "eleventh": 11, "twelfth": 12, "thirteenth": 13, "fourteenth": 14,
    "fifteenth": 15, "sixteenth": 16, "seventeenth": 17, "eighteenth": 18,
    "nineteenth": 19, "twentieth": 20,
}
_ORDINAL_TOKEN = re.compile(
    r"\b(" + "|".join(_ORDINALS) + r"|\d+(?:st|nd|rd|th))\b", re.IGNORECASE)
_SPIKE_WORD = re.compile(
    r"\b(?:spike|spikes|spiked|jump|jumps|jumped|peak|peaks|surge|leap|"
    r"largest|biggest|highest)\b", re.IGNORECASE)
_COST_LABEL = re.compile(r"cost|per\s+append", re.IGNORECASE)
_IDENTITY_LINE = re.compile(
    r"^(?:y\s*=|f\s*\(\s*x\s*\)\s*=|g\s*\(\s*x\s*\)\s*=)?\s*"
    r"(?:\(?\s*x\s*\)?|(?:[01](?:\.0+)?)\s*\*\s*x|x\s*\*\s*[01](?:\.0+)?|"
    r"x\s*\+\s*0(?:\.0+)?|0(?:\.0+)?\s*\+\s*x|x\s*-\s*0(?:\.0+)?|x\s*/\s*1(?:\.0+)?)\s*$",
    re.IGNORECASE)


def _fields(beat: Any) -> list[tuple[str, str]]:
    return [(field, getattr(beat, field)) for field in ("caption", "narration")
            if getattr(beat, field)]


def _frequency_capable(registry: Any) -> bool:
    return any(registry.get(name).domain == "frequency" for name in registry.names())


def _validated_params(comp: Any, beat: Any) -> Any:
    try:
        return comp.Params.model_validate(beat.params)
    except Exception:
        return None


def _spike_indices(text: str, count: int) -> list[int]:
    """0-based positions named by a spike claim in the clause that spikes.

    Ordinals in unrelated clauses ("The first section sets up the problem;
    the eighth term spikes") are not spike claims and are ignored.
    """
    if count <= 0:
        return []
    out: list[int] = []
    for clause in re.split(r"[;.!?]", text):
        if not _SPIKE_WORD.search(clause):
            continue
        for m in _ORDINAL_TOKEN.finditer(clause):
            token = m.group(1).lower()
            digits = re.match(r"\d+", token)
            value = _ORDINALS.get(token) or (int(digits.group(0)) if digits else 0)
            if 1 <= value <= count:
                out.append(value - 1)
    return out


def _param_claims(beat: Any, comp: Any, position: tuple[int, int]) -> tuple[list[Finding], int]:
    """Warns where prose names data that the beat's params do not contain.

    Returns the findings and the number of claims actually examined, so a
    correct claim counts as checked just like a failing one.
    """
    params = _validated_params(comp, beat)
    if params is None:
        return [], 0
    findings: list[Finding] = []
    examined = 0
    if beat.component == "bounce_sequence":
        values = list(params.values)
        for field, text in _fields(beat):
            indices = _spike_indices(text, len(values))
            if not indices:
                continue
            examined += 1
            top = set(sorted(range(len(values)), key=lambda i: values[i],
                             reverse=True)[:len(indices)])
            if set(indices) != top:
                names = ", ".join(str(i + 1) for i in sorted(top))
                findings.append(Finding(
                    "warn", position, field,
                    f'{field} says "{text.strip()[:120]}" but the largest '
                    f"bounce_sequence values are at positions {names}",
                ))
    elif beat.component == "graph":
        label = str(getattr(params, "label", "") or "")
        fn = str(getattr(params, "fn", "") or "")
        if _COST_LABEL.search(label) and _IDENTITY_LINE.match(fn.strip()):
            examined += 1
            for field, _text in _fields(beat):
                findings.append(Finding(
                    "warn", position, field,
                    f'{field} label "{label}" describes cost but fn "{fn}" is a '
                    "plain identity line: no cost data is computed",
                ))
    return findings, examined


def _param_claim_looked(sentence: str, beat: Any, comp: Any) -> bool:
    """Whether a param-vs-claim rule examined this sentence."""
    params = _validated_params(comp, beat)
    if params is None:
        return False
    if beat.component == "bounce_sequence":
        return bool(_spike_indices(sentence, len(params.values)))
    if beat.component == "graph":
        label = str(getattr(params, "label", "") or "")
        fn = str(getattr(params, "fn", "") or "")
        return bool(_COST_LABEL.search(label) and _IDENTITY_LINE.match(fn.strip()))
    return False


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
            # A facts-failure beat is unchecked for facts-based patterns, but
            # the domain rule needs no facts and must still run on it.
            no_facts = bool(skipped and (si, bi) in skipped)
            try:
                comp = registry.get(beat.component)
            except KeyError:
                continue
            if facts_map is not None:
                facts = facts_map.get((si, bi), [])
            else:
                facts = facts_for(registry, beat)
            pending: list[tuple[int, int, Finding]] = []
            if beat.component == "signal_spectrum":
                for field, text in _fields(beat):
                    for m in _HERTZ_PATTERN.finditer(text):
                        pending.append((2, m.start(), Finding(
                            "warn", (si, bi), field,
                            f'says "{m.group(0)}" but the signal_spectrum axis is '
                            "cycles per window, not hertz",
                        )))
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
                if no_facts:
                    break  # patterns need facts; the domain rule above does not
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
            param_findings, param_checked = _param_claims(beat, comp, (si, bi))
            checked += param_checked
            for finding in param_findings:
                pending.append((3, 0, finding))
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
                        skipped: set[tuple[int, int]] | None = None,
                        checked_numbers: set[tuple[int, int, str]] | None = None) -> list[tuple[Any, str]]:
    """Caption/narration sentences neither a number nor a claim rule looked at.

    ``checked_numbers`` carries ``(scene, beat, sentence)`` for every number
    numbers.py examined. A sentence with a checked number is checked even when
    no claim rule matched it. Beats in ``skipped`` (facts failed or params
    invalid) were not checked by numbers at all: their sentences stay
    unchecked unless a facts-free rule (domain / hertz) looked at them.
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
                for sentence in _SENTENCE_SPLIT.split(text):
                    if not sentence:
                        continue
                    if skipped and (si, bi) in skipped:
                        # Only the domain rule could look at a facts-failure
                        # beat; its other sentences remain unchecked.
                        if ((beat.component == "signal_spectrum" and _HERTZ_PATTERN.search(sentence))
                                or (comp is not None and comp.domain == "plain axes"
                                    and _DOMAIN_PATTERN.search(sentence))):
                            continue
                        out.append((beat, sentence))
                        continue
                    if comp is not None and _looked_at(sentence, beat.component, comp,
                                                       facts, has_peak_facts):
                        continue
                    if comp is not None and _param_claim_looked(sentence, beat, comp):
                        continue
                    if checked_numbers and (si, bi, sentence) in checked_numbers:
                        continue
                    out.append((beat, sentence))
    return out


def _looked_at(sentence: str, component: str, comp: Any,
               facts: list[Any], has_peak_facts: bool) -> bool:
    if component == "signal_spectrum" and _HERTZ_PATTERN.search(sentence):
        return True
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
