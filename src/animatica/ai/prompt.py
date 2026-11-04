"""Builds the instruction prompt sent to AI providers.

Providers only receive a single prompt string, so everything the model needs
(output format, component catalog, limits, an example) lives here.
"""
from __future__ import annotations

import json

from animatica.components.registry import ComponentRegistry
from animatica.storyboard.models import MAX_BEATS, MAX_SCENES, MAX_TEXT

_HINTS = {
    "title_card": "opening/closing title with optional subtitle",
    "equation": "LaTeX equation(s); mode 'reveal' shows them, 'transform' morphs one into the next",
    "steps_list": "numbered list of short steps or bullet points",
    "graph": "plot of y = fn(x); fn is a plain expression like sin(x) or x**2 (no LaTeX, no 'y =')",
    "bar_chart": "bar chart; labels and values must have the same length",
    "shape_morph": "one shape transforming into another",
    "diagram": "boxes (nodes) joined by arrows (edges)",
    "code_highlight": "code snippet with optional highlighted lines",
    "bounce_sequence": "a ball hops along a number sequence, one pad per term (pad height = value); "
                       "use it whenever the request mentions a ball, bouncing or hopping over terms "
                       "(Fibonacci, powers of 2, squares...). values are the terms in order, up to 20; ONE scene holds the whole sequence, never split it",
}

_EXAMPLE = {
    "version": "1",
    "title": "Pythagorean Theorem",
    "scenes": [
        {"beats": [{"component": "title_card", "params": {"title": "Pythagorean Theorem"},
                    "caption": "A rule for right triangles."}]},
        {"beats": [{"component": "equation",
                    "params": {"mode": "reveal", "latex": ["a^2 + b^2 = c^2"]},
                    "caption": "The squares of the legs add up to the square of the hypotenuse."}]},
    ],
}


def _catalog(registry: ComponentRegistry) -> str:
    lines = []
    for name, schema in registry.json_schema().items():
        hint = _HINTS.get(name, "")
        schema = {k: v for k, v in schema.items() if k not in ("title", "description")}
        lines.append(f"- {name}: {hint}\n  params schema: {json.dumps(schema, separators=(',', ':'))}")
    return "\n".join(lines)


def build_prompt(request: str, registry: ComponentRegistry, errors: list[str] | None = None) -> str:
    """Return the full prompt: instructions + catalog + example + request (+ repair errors)."""
    parts = [
        "You turn a topic into a short explainer-video storyboard.",
        "Reply with ONE JSON object and nothing else: no markdown fences, no commentary.",
        "",
        "Shape:",
        '{"version":"1","title":"...","scenes":[{"beats":[{"component":"<name>","params":{...},"caption":"..."}]}]}',
        "",
        "Rules:",
        f"- 1 to {MAX_SCENES} scenes; each scene has 1 to {MAX_BEATS} beats.",
        f"- Every text value is at most {MAX_TEXT} characters.",
        '- "version" must be the string "1". Do not add keys other than version, title, scenes, '
        "and (per beat) component, params, caption.",
        "- Use ONLY the components below, with exactly the params their schema allows.",
        "- Start with a title_card and prefer 3-6 scenes that build the idea step by step.",
        "- Put a one-sentence plain-language caption on each beat. Captions are shown on screen, so they must "
        "describe only what that beat's component actually draws; never mention a ball, arrows or any object "
        "unless the component shows it (only bounce_sequence has a ball).",
        "- Do not use steps_list or diagram just to repeat what another scene already shows; each scene should add something new.",
        "- Scene order: title_card first, then the definition/equation, then the demo (bounce_sequence, graph, ...), then at most one short summary. Never end with a chart that repeats the demo.",
        "- For equations use plain LaTeX that compiles on its own (no \\usepackage, no $ signs, no text-mode commands).",
        "",
        "Components:",
        _catalog(registry),
        "",
        "Example output:",
        json.dumps(_EXAMPLE, separators=(",", ":")),
        "",
        f"Topic to explain: {request}",
    ]
    if errors:
        parts += [
            "",
            "Your previous reply was rejected. Fix these problems and reply with the corrected JSON object only.",
            "Errors:",
            *errors[:6],
        ]
    return "\n".join(parts)



_OUTLINE_SHAPE = (
    '{"version":"1","title":"...","scenes":[{"beats":[{"component":"<name>","intent":"one line"}]}]}'
)


def build_outline_prompt(request: str, registry: ComponentRegistry, errors: list[str] | None = None) -> str:
    """Stage 1: ask for a scene outline only (component + intent per beat). Tiny JSON."""
    parts = [
        "You plan a short explainer-video storyboard. Reply with ONE JSON object and nothing else.",
        "",
        "Shape:",
        _OUTLINE_SHAPE,
        "",
        "Rules:",
        f"- 1 to {MAX_SCENES} scenes; each scene has 1 to {MAX_BEATS} beats.",
        '- "version" must be the string "1". No params yet -- only component and intent per beat.',
        "- Use ONLY these components: " + ", ".join(sorted(registry.json_schema())),
        "- Start with title_card, then definition/equation, then the demo, then at most one summary.",
        "- One bounce_sequence holds the whole sequence; never split a sequence across scenes.",
        "",
        f"Topic to explain: {request}",
    ]
    if errors:
        parts += ["", "Your previous reply was rejected. Fix these problems and reply with the corrected JSON object only.", "Errors:", *errors[:6]]
    return "\n".join(parts)


def build_fill_prompt(request: str, registry: ComponentRegistry, outline_scene: dict, errors: list[str] | None = None) -> str:
    """Stage 2: fill params for ONE scene. Short output, validated and retried alone."""
    parts = [
        "Fill in the params for ONE scene of an explainer-video storyboard. Reply with ONE JSON object and nothing else.",
        "",
        "Shape:",
        '{"version":"1","title":"...","scenes":[{"beats":[{"component":"<name>","params":{...},"caption":"..."}]}]}',
        "",
        "Rules:",
        f"- Every text value is at most {MAX_TEXT} characters.",
        "- Use exactly the components below with exactly the params their schema allows.",
        "- One-sentence caption per beat; it must describe only what the component draws.",
        "",
        "Components:",
        _catalog(registry),
        "",
        "Scene to fill (component + intent per beat):",
        json.dumps(outline_scene, separators=(",", ":")),
        "",
        f"Topic to explain: {request}",
    ]
    if errors:
        parts += ["", "Your previous reply was rejected. Fix these problems and reply with the corrected JSON object only.", "Errors:", *errors[:6]]
    return "\n".join(parts)
