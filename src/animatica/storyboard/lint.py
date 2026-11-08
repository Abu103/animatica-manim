"""Deterministic clean-up of model-written storyboards. No LLM, no Manim, idempotent.

Weak models split one sequence across scenes and add scenes that repeat earlier ones.
Each rule is conservative: when unsure, leave the storyboard alone and only report.
Returns (new_storyboard, notes); notes are shown to the user as warnings.
"""
from __future__ import annotations

from animatica.storyboard.models import Beat, Scene, Storyboard

MAX_MERGED_TERMS = 20
OBJECT_WORDS = ("ball", "bounc", "hop")


def _single(scene: Scene, component: str) -> Beat | None:
    return scene.beats[0] if len(scene.beats) == 1 and scene.beats[0].component == component else None


def _num(x: str) -> int | None:
    return int(x) if x.strip().lstrip("-").isdigit() else None


def _merge_sequences(scenes: list[Scene], notes: list[str]) -> list[Scene]:
    """Fold every single-beat bounce_sequence scene into the first one (one sequence = one scene)."""
    idx = [i for i, s in enumerate(scenes) if _single(s, "bounce_sequence")]
    if len(idx) < 2:
        return scenes
    first = scenes[idx[0]].beats[0]
    params = dict(first.params)
    values = list(params.get("values", []))
    labels = list(params.get("labels") or [str(i) for i in range(len(values))])
    merged = [idx[0]]
    for i in idx[1:]:
        b = scenes[i].beats[0].params
        v2 = list(b.get("values", []))
        if len(values) + len(v2) > MAX_MERGED_TERMS:
            continue
        l2 = list(b.get("labels") or [])
        if not l2:  # unlabelled continuation: number it from where the first part stopped
            last = _num(labels[-1])
            l2 = [str(last + 1 + k) for k in range(len(v2))] if last is not None else [str(len(labels) + k) for k in range(len(v2))]
        values += v2
        labels += l2
        merged.append(i)
    if len(merged) < 2:
        return scenes
    params["values"], params["labels"] = values, labels
    nums = [_num(x) for x in labels]
    if all(n is not None for n in nums) and params.get("title"):
        params["title"] = f"Terms {nums[0]} to {nums[-1]}"
    new_first = Beat(component="bounce_sequence", params=params, caption=first.caption)
    out = []
    for i, s in enumerate(scenes):
        if i == merged[0]:
            out.append(Scene(beats=[new_first]))
        elif i not in merged:
            out.append(s)
    notes.append(f"lint: merged {len(merged)} bounce_sequence scenes into one ({len(values)} terms)")
    return out


def _drop_redundant_charts(scenes: list[Scene], notes: list[str]) -> list[Scene]:
    """A bar_chart whose values all appear in an earlier bounce_sequence adds nothing new."""
    seen: set[float] = set()
    out = []
    for s in scenes:
        b = _single(s, "bar_chart")
        if b is not None and seen and set(map(float, b.params.get("values", []))) <= seen:
            notes.append("lint: dropped a bar_chart scene that only repeats the bounce_sequence values")
            continue
        for beat in s.beats:
            if beat.component == "bounce_sequence":
                seen |= {float(v) for v in beat.params.get("values", [])}
        out.append(s)
    return out or scenes


def _warn_phantom_objects(scenes: list[Scene], notes: list[str]) -> None:
    for si, s in enumerate(scenes):
        for b in s.beats:
            if b.component != "bounce_sequence" and any(w in b.caption.lower() for w in OBJECT_WORDS):
                notes.append(f"lint: scene {si} caption mentions a ball/hop but {b.component} draws none")


# Preferred narrative arc: title -> definition -> demo -> summary.
_STAGE = {
    "title_card": 0,
    "equation": 1,
    "steps_list": 1,
    "diagram": 1,
    "code_highlight": 1,
    "bounce_sequence": 2,
    "graph": 2,
    "bar_chart": 2,
    "array_viz": 2,
    "recursion_tree": 2,
    "number_line": 2,
    "table": 2,
    "shape_morph": 2,
    # compare is a two-column demo/comparison, not a summary: keep it in the
    # demo stage so it is never mistaken for the closing summary.
    "compare": 2,
}


def _scene_component_order(scenes: list[Scene], notes: list[str]) -> None:
    """Warn when scenes break the title -> definition -> demo -> summary arc.

    Weak models ignore the prompt's ordering rule, so the lint pass notes it.
    This only reports (never reorders): reordering is a semantic choice the
    user makes in the storyboard JSON.

    Single-scene storyboards have no ordering to violate, so they are left
    alone: P0 acceptance is "one scene, ... no warnings", and a lone demo
    scene must not be told to open with a title_card.

    Components that are not in the narrative arc (unknown or future
    components) are treated as neutral: they neither trigger nor suppress a
    regression warning, since we cannot know where they belong.
    """
    if len(scenes) < 2:
        return
    first_comp = scenes[0].beats[0].component if scenes[0].beats else ""
    if first_comp != "title_card":
        notes.append(
            "lint: storyboards should open with a title_card; "
            "the first scene is not one"
        )
    prev: int | None = None
    last = len(scenes) - 1
    for si, scene in enumerate(scenes, 1):
        comp = scene.beats[0].component if scene.beats else ""
        if si - 1 == last and comp == "title_card":
            stage = 3  # a closing title is the summary
        elif si - 1 == last and comp in ("steps_list", "table") and prev is not None and prev >= 2:
            # A closing steps_list or table that follows demo content is a
            # summary, not a backward step in the narrative.
            stage = 3
        else:
            stage = _STAGE.get(comp)
        if stage is None:
            continue  # unclassified: no opinion, skip regression tracking
        if prev is not None and stage < prev:
            notes.append(
                f"lint: scene {si} ({comp}) moves backward in the narrative; "
                "prefer title -> definition -> demo -> summary"
            )
        prev = stage if prev is None else max(prev, stage)


def lint_storyboard(sb: Storyboard) -> tuple[Storyboard, list[str]]:
    notes: list[str] = []
    scenes = _merge_sequences(list(sb.scenes), notes)
    scenes = _drop_redundant_charts(scenes, notes)
    _warn_phantom_objects(scenes, notes)
    _scene_component_order(scenes, notes)
    if scenes == list(sb.scenes):
        return sb, notes
    return sb.model_copy(update={"scenes": scenes}), notes

