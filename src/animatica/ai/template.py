"""Offline template matcher: matches common prompts to storyboard templates."""
from __future__ import annotations

import re

from animatica.storyboard.models import Storyboard

_TEMPLATES: list[dict] = [
    {
        "name": "title_card",
        "example": "make a title card about hello world",
        "keywords": ["title card", "title"],
        "storyboard": {
            "version": "1",
            "title": "Hello World",
            "scenes": [{"beats": [{"component": "title_card", "params": {"title": "Hello World"}}]}],
        },
    },
    {
        "name": "equation",
        "example": "explain the pythagorean theorem a^2 + b^2 = c^2",
        "keywords": ["equation", "theorem", "formula", "pythagorean"],
        "storyboard": {
            "version": "1",
            "title": "Pythagorean Theorem",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "equation",
                            "params": {"mode": "reveal", "latex": ["a^2 + b^2 = c^2"]},
                        }
                    ]
                }
            ],
        },
    },
    {
        "name": "function_graph",
        "example": "graph of sin(x)",
        "keywords": ["graph", "plot", "function", "sin(x)"],
        "storyboard": {
            "version": "1",
            "title": "Function Graph",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "graph",
                            "params": {
                                "fn": "sin(x)",
                                "x_range": [-6.28, 6.28],
                                "y_range": [-1.5, 1.5],
                                "label": "sin(x)",
                            },
                        }
                    ]
                }
            ],
        },
    },
    {
        "name": "bar_chart",
        "example": "bar chart of sales by quarter",
        "keywords": ["bar chart", "bar graph"],
        "storyboard": {
            "version": "1",
            "title": "Sales by Quarter",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "bar_chart",
                            "params": {
                                "title": "Sales by Quarter",
                                "labels": ["Q1", "Q2", "Q3", "Q4"],
                                "values": [3, 5, 2, 7],
                            },
                        }
                    ]
                }
            ],
        },
    },
    {
        "name": "steps",
        "example": "steps to bake a cake",
        "keywords": ["steps", "how to", "tutorial"],
        "storyboard": {
            "version": "1",
            "title": "How To",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "steps_list",
                            "params": {"items": ["Mix ingredients", "Bake at 350F", "Cool and serve"]},
                        }
                    ]
                }
            ],
        },
    },
    {
        "name": "shape_morph",
        "example": "morph a circle into a square",
        "keywords": ["morph", "circle", "square"],
        "storyboard": {
            "version": "1",
            "title": "Shape Morph",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "shape_morph",
                            "params": {"from_shape": "circle", "to_shape": "square"},
                        }
                    ]
                }
            ],
        },
    },
    {
        "name": "diagram",
        "example": "flow diagram from a to b",
        "keywords": ["diagram", "flow", "nodes", "edges"],
        "storyboard": {
            "version": "1",
            "title": "Flow Diagram",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "diagram",
                            "params": {"nodes": ["A", "B"], "edges": [("A", "B")]},
                        }
                    ]
                }
            ],
        },
    },
    {
        "name": "code_walkthrough",
        "example": "walk through this python code",
        "keywords": ["code", "walkthrough", "python"],
        "storyboard": {
            "version": "1",
            "title": "Code Walkthrough",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "code_highlight",
                            "params": {"code": "print('hello')", "language": "python", "lines": [1]},
                        }
                    ]
                }
            ],
        },
    },
    {
        "name": "definition",
        "example": "definition of inertia",
        "keywords": ["definition", "define", "what is"],
        "storyboard": {
            "version": "1",
            "title": "Definition",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "title_card",
                            "params": {"title": "Definition"},
                        },
                        {
                            "component": "steps_list",
                            "params": {"items": ["A property of matter that resists changes in motion"]},
                        },
                    ]
                }
            ],
        },
    },
    {
        "name": "comparison",
        "example": "compare option A and option B",
        "keywords": ["compare", "versus", "vs"],
        "storyboard": {
            "version": "1",
            "title": "Comparison",
            "scenes": [
                {
                    "beats": [
                        {
                            "component": "bar_chart",
                            "params": {
                                "title": "Comparison",
                                "labels": ["Option A", "Option B"],
                                "values": [5, 7],
                            },
                        }
                    ]
                }
            ],
        },
    },
]


class TemplateMatcher:
    """Matches a prompt to a canned storyboard template (offline, no LLM)."""

    def list_templates(self) -> list[tuple[str, str]]:
        """Return (name, example_prompt) for every template."""
        return [(t["name"], t["example"]) for t in _TEMPLATES]

    def by_name(self, name: str) -> Storyboard | None:
        """Return the storyboard of the template called exactly `name`.

        ``match()`` is keyword-based and works on prompts, so it cannot be used
        with a template name ("title_card" has no whole-word boundary before
        the underscore). Menus that list templates use this instead.
        """
        for tmpl in _TEMPLATES:
            if tmpl["name"] == name:
                return Storyboard.model_validate(tmpl["storyboard"])
        return None

    def match(self, prompt: str) -> Storyboard | None:
        """Return a Storyboard if `prompt` matches a template, else None."""
        lowered = prompt.lower()
        for tmpl in _TEMPLATES:
            # whole words only: "vs" must not match "canvas", "code" must not match "decode"
            if any(re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", lowered) for kw in tmpl["keywords"]):
                return Storyboard.model_validate(tmpl["storyboard"])
        return None

