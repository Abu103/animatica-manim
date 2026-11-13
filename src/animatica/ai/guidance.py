"""General generation guidance for AI-authored storyboards.

These rules are prompt-agnostic: they apply to any topic. They are meant to
be included in the instructions given to a model when it generates a
storyboard, and can also be used to lint a produced storyboard.

Rules are intentionally conservative: when unsure, leave the storyboard
alone and only report.
"""

from __future__ import annotations

import re

from animatica.storyboard.models import Storyboard

# ---------------------------------------------------------------------------
# Caption rules
# ---------------------------------------------------------------------------

CAPTION_RULES = [
    "A caption teaches the viewer what the scene shows; it never describes "
    "production mechanics (e.g. avoid 'A title card introducing X', "
    "'This scene shows a graph of Y').",
    "A caption is one sentence, plain language, appropriate for someone "
    "encountering the topic for the first time.",
    "If the scene compares two things (original vs approximation, before vs "
    "after), the caption states what is being compared and what the viewer "
    "should notice.",
]

# ---------------------------------------------------------------------------
# Visual comparison rules
# ---------------------------------------------------------------------------

COMPARISON_RULES = [
    "If the explanation compares an original function to an approximation "
    "(e.g. Taylor series vs the function it approximates), show both on the "
    "same graph using the graph component's approx_fn parameter, with a "
    "label for each curve.",
    "If the explanation compares options (A vs B, before vs after), use a "
    "bar_chart or compare component so the difference is visible, not just "
    "described in text.",
]

# ---------------------------------------------------------------------------
# Component-selection rules
# ---------------------------------------------------------------------------

COMPONENT_RULES = [
    "Prefer the fewest scenes needed to tell the story: title card, one "
    "definition beat, one demo beat, one summary beat.",
    "Use graph for functions, equation for formulas, steps_list for takeaways, "
    "title_card for the opening.",
]


def caption_teaches_not_describes(sb: Storyboard) -> list[str]:
    """Flag captions that describe production mechanics instead of teaching.

    Returns a list of (scene_index, caption, reason) tuples for captions that
    look like meta-commentary rather than explanatory content.
    """
    flags: list[str] = []
    meta_phrases = (
        "title card", "this scene", "this beat", "introducing", "shows a",
        "displays a", "renders a", "the graph", "the equation",
    )
    for si, scene in enumerate(sb.scenes, 1):
        for beat in scene.beats:
            cap = beat.caption.strip().lower()
            if not cap:
                continue
            for phrase in meta_phrases:
                if phrase in cap:
                    flags.append(
                        f"scene {si}: caption describes production mechanics "
                        f"({phrase!r}) instead of teaching the topic: "
                        f"{beat.caption!r}"
                    )
                    break
    return flags


#: Comparison language, as whole words: "the two before it" and "beforehand" are not comparisons.
_COMPARISON = re.compile(
    r"\b(compare[sd]?|comparison|versus|vs|original|approximations?|approximates?|side by side|before and after)\b"
)


def comparison_has_visual(sb: Storyboard) -> list[str]:
    """Flag storyboards that mention a comparison but show only one side.

    Looks for comparison language in captions/params and checks whether a
    graph with approx_fn, a bar_chart, or a compare component is present.
    """
    flags: list[str] = []
    for si, scene in enumerate(sb.scenes, 1):
        for beat in scene.beats:
            text = (beat.caption + " " + str(beat.params)).lower()
            if not _COMPARISON.search(text):
                continue
            # Is there a visual comparison in this or a neighboring scene?
            has_visual = any(
                b.component == "graph" and b.params.get("approx_fn", "").strip()
                for s in sb.scenes for b in s.beats
            ) or any(b.component in ("bar_chart", "compare") for s in sb.scenes for b in s.beats) or any(
                # a stat_callout draws its delta ("+12% vs last year") next to the number
                b.component == "stat_callout" and str(b.params.get("delta", "")).strip()
                for s in sb.scenes for b in s.beats
            )
            if not has_visual:
                flags.append(
                    f"scene {si}: caption mentions a comparison "
                    f"but no visual comparison (graph with approx_fn, "
                    f"bar_chart, or compare) appears in the storyboard"
                )
    return flags


def check_generation_guidance(sb: Storyboard) -> list[str]:
    """Run all guidance checks and return a list of human-readable notes.

    Notes are suggestions, not errors: a storyboard can be valid even with
    guidance notes. Use these to inform a repair pass or to show the user
    what could be improved.
    """
    notes: list[str] = []
    notes.extend(caption_teaches_not_describes(sb))
    notes.extend(comparison_has_visual(sb))
    return notes
