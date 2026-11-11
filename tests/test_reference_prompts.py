"""The reference prompts: one prompt per registered component.

The eval harness (T16) runs these prompts through real providers and scores
what comes back, so the corpus has to cover every component the registry
knows -- a component no prompt reaches is a component the eval never
measures. The prompts also have to be unambiguous about which component
they are about: the coverage test resolves each prompt to exactly one
component, by the component's own name or by an obvious intent, and the
resolution has to be a bijection onto the registry.

The offline ``TemplateMatcher`` cannot serve this file: it knows ten
templates and the registry has twenty-one components. The matcher's own
coverage lives in ``tests/test_template.py``; this corpus is for the live
eval.
"""
from pathlib import Path

import pytest

from animatica.components.registry import default_registry

PROMPTS = [
    line.strip()
    for line in (Path(__file__).parent / "reference_prompts.txt").read_text(encoding="utf-8").splitlines()
    if line.strip() and not line.startswith("#")
]

#: How a prompt is recognised as being about a component: the component's
#: name (with underscores as spaces), or the intent that names it. The first
#: rule that matches a prompt wins, so the specific ones come first.
_RULES: list[tuple[str, str]] = [
    ("title card", "title_card"),
    ("theorem", "equation"),
    ("steps to", "steps_list"),
    ("taylor series", "graph"),
    ("bar chart", "bar_chart"),
    ("morph", "shape_morph"),
    ("nodes", "diagram"),
    ("flow", "flow"),
    ("code highlight", "code_highlight"),
    ("line by line", "code_walkthrough"),
    ("compare", "compare"),
    ("timeline", "timeline"),
    ("array", "array_viz"),
    ("call tree", "recursion_tree"),
    ("table", "table"),
    ("number line", "number_line"),
    ("matrix", "matrix"),
    ("stat callout", "stat_callout"),
    ("derive", "formula_derivation"),
    ("parametric graph", "parametric_graph"),
    ("ball", "bounce_sequence"),
]

#: What a prompt must not carry: a snippet of source code. The prompt is
#: the topic; the code is what the model is asked to write.
_CODE_MARKERS = (
    "def ",
    "return ",
    "import ",
    "print(",
    "class ",
    "lambda ",
    "function(",
    "==",
    "=>",
    "{",
    "}",
    ";",
)


def component_for(prompt: str) -> str | None:
    """The component a prompt is about, by name or by obvious intent."""
    lowered = prompt.lower()
    for needle, component in _RULES:
        if needle in lowered:
            return component
    return None


def test_reference_prompts_count():
    """One prompt per registered component, and no more."""
    assert len(PROMPTS) == len(default_registry().names())


def test_every_component_is_covered_exactly_once():
    """Every registered component is reached by one prompt, and no prompt
    reaches two components.

    A component no prompt reaches is a component the eval never measures;
    a prompt that could be read as two components measures neither.
    """
    registry = default_registry().names()
    resolved: dict[str, str] = {}
    for prompt in PROMPTS:
        component = component_for(prompt)
        assert component is not None, f"no component claims the prompt: {prompt!r}"
        assert component in registry, f"{prompt!r} claims an unknown component {component!r}"
        assert component not in resolved.values(), (
            f"two prompts are about {component!r}: {resolved[component]!r} and {prompt!r}"
        )
        resolved[component] = prompt

    missing = sorted(set(registry) - set(resolved))
    assert not missing, f"no prompt covers: {', '.join(missing)}"


def test_no_duplicate_prompts():
    """No prompt says the same thing twice."""
    lowered = [p.lower() for p in PROMPTS]
    assert len(set(lowered)) == len(lowered), "the same prompt appears twice"


def test_prompts_carry_no_code():
    """A prompt is the topic, not the code: the model writes the code."""
    for prompt in PROMPTS:
        lowered = prompt.lower()
        for marker in _CODE_MARKERS:
            assert marker not in lowered, f"{prompt!r} carries code ({marker!r})"


def test_taylor_series_and_fibonacci_prompts_are_present():
    """The two prompts the demo is built on have to be in the corpus."""
    assert "explain taylor series" in PROMPTS
    assert any("fibonacci" in p.lower() for p in PROMPTS), PROMPTS


@pytest.mark.parametrize("prompt", PROMPTS)
def test_prompt_is_a_single_short_line(prompt):
    """A prompt is one line and fits the request limit."""
    assert "\n" not in prompt
    assert len(prompt) <= 300
