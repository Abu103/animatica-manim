"""Every component must leave the caption its room.

The caption is burned in at the bottom of every frame. A component that lays
itself out against a fixed constant (``to_edge(DOWN, buff=1.2)``) is only
right for a one-line caption: as soon as the caption wraps to two lines it
grows upwards into the content, and no lint can see it, because the lint
leaves the caption strip out on purpose. This test is the missing check.

It plays each component with the real caption the renderer would burn in
(``make_caption``), for the registry example and for every beat of the
conformance storyboards, and demands that no text reaches into the caption
(``MIN_CLEARANCE`` units above its top edge).

Components that still violate for a *two-line* caption are listed in
``KNOWN_VIOLATORS``. The list may only shrink: a component that is listed but
no longer violates fails the test, so the entry has to be deleted with the fix.
"""
from __future__ import annotations

import glob
import json
import os

import pytest

from animatica.components._draw import make_caption
from animatica.components.registry import default_registry
from geometry import make_colors, play_component, resolution
from test_component_play_smoke import _example_params

#: How far above the caption's top edge the lowest text must stay.
MIN_CLEARANCE = 0.1

PIXELS = (1280, 720)

#: A caption that fits one line, and one that wraps to two (the usual length
#: of a caption a model writes).
CAPTIONS = {
    "one line": "A ball hops along the terms.",
    "two lines": (
        "Each new term is the sum of the two terms before it, "
        "so the sequence grows quickly."
    ),
}

#: kind of caption -> {component: why it is still allowed to violate}.
#: Nothing may be listed for "one line": that is the case every component
#: was sized for.
KNOWN_VIOLATORS: dict[str, dict[str, str]] = {
    "one line": {},
    "two lines": {
        "bar_chart": "found by this test, no issue filed yet",
        "code_walkthrough": "found by this test, no issue filed yet",
        "flow": "found by this test, no issue filed yet",
        "formula_derivation": "#29: the last derivation step runs into the caption",
        "matrix": "found by this test, no issue filed yet",
        "parametric_graph": "found by this test, no issue filed yet",
        "stat_callout": "found by this test, no issue filed yet",
        "table": "found by this test, no issue filed yet",
    },
}

_CONFORMANCE = os.path.join(os.path.dirname(__file__), "conformance")
_NOT_STORYBOARDS = {"expected.json", "gate_allowlist.json"}


def _cases() -> dict[str, list[tuple[str, dict]]]:
    """component name -> [(where the params come from, params), ...]."""
    registry = default_registry()
    cases: dict[str, list[tuple[str, dict]]] = {
        name: [("registry example", _example_params(name))] for name in registry.names()
    }
    for path in sorted(glob.glob(os.path.join(_CONFORMANCE, "*.json"))):
        base = os.path.basename(path)
        if base in _NOT_STORYBOARDS:
            continue
        with open(path, encoding="utf-8") as handle:
            storyboard = json.load(handle)
        for scene in storyboard["scenes"]:
            for index, beat in enumerate(scene["beats"]):
                cases.setdefault(beat["component"], []).append((f"{base}#{index}", beat["params"]))
    return cases


_CASES = _cases()


def _violations(name: str, caption_text: str) -> list[str]:
    """Describe every text that reaches into the caption, for one component."""
    component = default_registry().get(name)
    found: list[str] = []
    for where, params in _CASES[name]:
        validated = component.Params.model_validate(params)
        with resolution(*PIXELS):
            caption = make_caption(caption_text, make_colors())
            limit = caption.get_top()[1] + MIN_CLEARANCE
            beat = play_component(component, validated, *PIXELS, caption=caption, label=name)
            for text in beat.texts:
                if text is caption:
                    continue
                bottom = text.get_bottom()[1]
                if bottom < limit - 1e-6:
                    found.append(
                        f"{name} ({where}): {text.__class__.__name__} reaches down to y={bottom:.2f}, "
                        f"the caption's top is y={caption.get_top()[1]:.2f} "
                        f"(it must stay above y={limit:.2f})"
                    )
    return found


@pytest.mark.parametrize("kind", list(CAPTIONS))
@pytest.mark.parametrize("name", sorted(_CASES))
def test_component_leaves_the_caption_its_room(name: str, kind: str):
    violations = _violations(name, CAPTIONS[kind])
    known = KNOWN_VIOLATORS[kind]

    if name in known:
        assert violations, (
            f"{name} is listed in KNOWN_VIOLATORS[{kind!r}] ({known[name]}) but no longer "
            f"reaches into the {kind} caption: delete the entry"
        )
        return
    assert not violations, "\n".join(violations)


def test_known_violators_name_real_components():
    names = set(default_registry().names())
    for kind, listed in KNOWN_VIOLATORS.items():
        assert kind in CAPTIONS
        assert set(listed) <= names, f"unknown component(s) in KNOWN_VIOLATORS[{kind!r}]: {set(listed) - names}"
    assert not KNOWN_VIOLATORS["one line"], "the one-line caption is the case every component was sized for"
