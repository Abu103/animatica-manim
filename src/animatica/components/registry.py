"""Component registry: registration, validation of storyboards, JSON schema generation."""
from __future__ import annotations

import hashlib
from pydantic import ValidationError

from animatica.components.base import API_VERSION, Component
from animatica.plugins import load_entry_points
from animatica.storyboard.models import Storyboard


class ComponentRegistry:
    def __init__(self) -> None:
        self._items: dict[str, Component] = {}

    def register(self, cls: type[Component]) -> None:
        if cls.api_version != API_VERSION:
            raise ValueError(
                f"Component {cls.name!r} has api_version {cls.api_version}; this Animatica needs api_version {API_VERSION}"
            )
        if cls.name in self._items:
            raise ValueError(f"Component {cls.name!r} is already registered")
        self._items[cls.name] = cls()

    def get(self, name: str) -> Component:
        return self._items[name]

    def names(self) -> list[str]:
        return sorted(self._items)

    def fingerprint(self) -> str:
        """sha256 hex of sorted ``name:api_version`` pairs; changes when the
        registry's components or their API versions change."""
        pairs = sorted(f"{c.name}:{c.api_version}" for c in self._items.values())
        return hashlib.sha256("\n".join(pairs).encode("utf-8")).hexdigest()

    def json_schema(self) -> dict:
        return {name: c.Params.model_json_schema() for name, c in sorted(self._items.items())}

    def validate(self, sb: Storyboard) -> list[str]:
        """Validate `sb` against the registry, returning human-readable errors.

        Each error names the scene/beat, the field, the bad value, the allowed
        values (when known), and a fixed example — written so an LLM can correct
        the storyboard on retry without guessing.
        """
        errors: list[str] = []
        for si, scene in enumerate(sb.scenes, 1):
            for bi, beat in enumerate(scene.beats, 1):
                where = f"scene {si}, beat {bi}"
                comp = self._items.get(beat.component)
                if comp is None:
                    valid = ", ".join(self.names())
                    errors.append(
                        f"{where}: unknown component {beat.component!r}. "
                        f"Valid components: {valid}. "
                        f"Example: use 'title_card' with params {{'title': 'My Title'}}."
                    )
                    continue
                try:
                    comp.Params.model_validate(beat.params)
                except ValidationError as exc:
                    for err in exc.errors():
                        field = ".".join(str(x) for x in err["loc"]) or "params"
                        msg = f"{where} ({beat.component}): field '{field}': {err['msg']}"
                        bad = err.get("input")
                        if bad is not None:
                            msg += f" (got {bad!r})"
                        ctx = err.get("ctx") or {}
                        if ctx:
                            allowed = _allowed_hint(ctx)
                            if allowed:
                                msg += f"; {allowed}"
                        example = _example_hint(field, comp)
                        if example:
                            msg += f". Example: {example}"
                        errors.append(msg)
        return errors


def _builtins() -> list[type[Component]]:
    from animatica.components.compare import Compare
    from animatica.components.timeline import Timeline
    from animatica.components.array_viz import ArrayViz
    from animatica.components.recursion_tree import RecursionTree
    from animatica.components.table import Table
    from animatica.components.number_line import NumberLine
    from animatica.components.bar_chart import BarChart
    from animatica.components.bounce_sequence import BounceSequence
    from animatica.components.code_highlight import CodeHighlight
    from animatica.components.diagram import Diagram
    from animatica.components.equation import Equation
    from animatica.components.graph import Graph
    from animatica.components.shape_morph import ShapeMorph
    from animatica.components.steps_list import StepsList
    from animatica.components.title_card import TitleCard
    return [
        Compare,
        Timeline,
        ArrayViz,
        RecursionTree,
        Table,
        NumberLine,
        TitleCard,
        Equation,
        StepsList,
        Graph,
        BarChart,
        ShapeMorph,
        Diagram,
        CodeHighlight,
        BounceSequence,
    ]


def default_registry() -> ComponentRegistry:
    reg = ComponentRegistry()
    for cls in _builtins():
        reg.register(cls)
    for cls in load_entry_points("animatica.components").values():
        reg.register(cls)
    return reg


def _allowed_hint(ctx: dict) -> str | None:
    """Turn pydantic ValidationError ctx into an 'allowed values' hint."""
    parts: list[str] = []
    if "max_length" in ctx:
        parts.append(f"at most {ctx['max_length']} items/characters")
    if "min_length" in ctx:
        parts.append(f"at least {ctx['min_length']} items/characters")
    if "ge" in ctx:
        parts.append(f">= {ctx['ge']}")
    if "le" in ctx:
        parts.append(f"<= {ctx['le']}")
    if "gt" in ctx:
        parts.append(f"> {ctx['gt']}")
    if "lt" in ctx:
        parts.append(f"< {ctx['lt']}")
    return "; allowed: " + ", ".join(parts) if parts else None


# Fixed examples per (component, field) so repair retries can copy-paste a valid value.
_EXAMPLES: dict[str, dict[str, str]] = {
    "bounce_sequence": {
        "values": "[0, 1, 1, 2, 3, 5, 8, 13]",
        "labels": '["0", "1", "2", "3", "5", "8", "13", "21"]',
        "title": "'Fibonacci Terms'",
    },
    "bar_chart": {
        "values": "[3, 5, 2, 7]",
        "labels": '["Q1", "Q2", "Q3", "Q4"]',
        "title": "'Sales by Quarter'",
    },
    "steps_list": {
        "items": '["Mix ingredients", "Bake at 350F", "Cool and serve"]',
        "title": "'How To'",
    },
    "graph": {
        "fn": "'sin(x)'",
        "x_range": "[-6.28, 6.28]",
        "y_range": "[-1.5, 1.5]",
        "label": "'sin(x)'",
        "title": "'Function Graph'",
    },
    "compare": {
        "left": '{"heading": "Option A", "bullets": ["fast", "cheap"]}',
        "right": '{"heading": "Option B", "bullets": ["slow", "premium"]}',
        "title": "'Comparison'",
    },
    "timeline": {
        "events": '[{"label": "Start", "text": "Begin here"}]',
        "title": "'Timeline'",
    },
    "table": {
        "columns": '["Item", "Value"]',
        "rows": '[["A", "1"], ["B", "2"]]',
        "title": "'Table'",
    },
    "recursion_tree": {
        "fn": "'fib'",
        "n": "4",
        "title": "'Fibonacci Call Tree'",
    },
    "number_line": {
        "start": "0",
        "end": "10",
        "title": "'Number Line'",
    },
    "shape_morph": {
        "from_shape": "'circle'",
        "to_shape": "'square'",
        "title": "'Shape Morph'",
    },
    "diagram": {
        "nodes": '["A", "B"]',
        "edges": '[["A", "B"]]',
        "title": "'Flow Diagram'",
    },
    "code_highlight": {
        "code": "'print(\"hello\")'",
        "language": "'python'",
        "lines": "[1]",
        "title": "'Code Walkthrough'",
    },
    "equation": {
        "mode": "'reveal'",
        "latex": '["a^2 + b^2 = c^2"]',
        "title": "'Pythagorean Theorem'",
    },
    "title_card": {
        "title": "'My Title'",
        "subtitle": "'A subtitle'",
    },
    "array_viz": {
        "values": "[5, 2, 8, 1]",
        "steps": '[{"highlight": [0]}, {"swap": [0, 2]}]',
        "title": "'Array Viz'",
    },
}


def _example_hint(field: str, comp: Component) -> str | None:
    """Return a valid example value for `field` on `comp`, if we have one."""
    by_field = _EXAMPLES.get(comp.name)
    if not by_field:
        return None
    # pydantic loc can be nested (e.g. ("left", "bullets")); try exact then leaf.
    if field in by_field:
        return by_field[field]
    leaf = field.split(".")[-1]
    if leaf in by_field:
        return by_field[leaf]
    return None

