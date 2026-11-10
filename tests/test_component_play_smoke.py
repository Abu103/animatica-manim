"""Smoke test: every registered component's play() runs without raising.

A component can be registered, validate its params and still crash at render
time on a trivial input -- a missing manim import, a wrong attribute name.
Those crashes only surfaced in a real render, where the beat silently
degrades to a text card (see ``scene.py``) and the report shows a fallback.

This test calls ``play()`` directly with a minimal fake scene, so a crash
fails loudly in the unit suite instead of quietly degrading a video.

The registry examples (``animatica.components.registry._EXAMPLES``) supply
valid params for most components; the ones without an example get a
hand-written minimum here.
"""
from __future__ import annotations

import ast

import pytest

from animatica.components.registry import _EXAMPLES, default_registry
from geometry import RecordingScene as _FakeScene

# Minimum valid params for components the registry has no example for.
_EXTRA_EXAMPLES: dict[str, dict] = {
    "code_walkthrough": {"title": "Snippet", "code": "print('hello')", "language": "python", "lines": [1]},
    "flow": {"title": "Flow", "nodes": ["a", "b"], "edges": [[0, 1]]},
    "formula_derivation": {"title": "Derivation", "steps": ["start", "finish"]},
    "matrix": {"title": "Matrix", "values": [[1, 2], [3, 4]]},
    "parametric_graph": {"title": "Curve", "x_expr": "t", "y_expr": "t**2"},
    "stat_callout": {"value": "42", "label": "answers"},
}

# Overrides for components whose registry example is too small to reach every
# branch of play(). ``timeline`` alternates labels above/below the line, so a
# single-event example only ever exercises the "above" branch.
_EXAMPLE_OVERRIDES: dict[str, dict] = {
    "timeline": {
        "title": "Timeline",
        "events": [
            {"label": "Start", "text": "Begin here"},
            {"label": "Next", "text": "Then this"},
        ],
    },
}


def _example_params(name: str) -> dict:
    """Decode a registry example into real params.

    The registry examples are written for an LLM to read, so each value is a
    quoted literal (``'Timeline'``, ``'["a", "b"]'``) rather than a real
    object. ``ast.literal_eval`` decodes both plain strings and JSON-ish
    lists/dicts without executing anything.
    """
    raw = _EXAMPLES.get(name)
    if raw is None:
        return dict(_EXTRA_EXAMPLES[name])
    decoded = {k: ast.literal_eval(v) if isinstance(v, str) else v for k, v in raw.items()}
    decoded.update(_EXAMPLE_OVERRIDES.get(name, {}))
    return decoded


@pytest.mark.parametrize("name", default_registry().names())
def test_component_play_does_not_raise(name: str):
    """play() must not raise for a component's documented minimum input."""
    from animatica.components.theme import PALETTES

    registry = default_registry()
    comp = registry.get(name)
    params = comp.Params.model_validate(_example_params(name))
    scene = _FakeScene()

    comp.play(scene, params, PALETTES["dark-blue"])
