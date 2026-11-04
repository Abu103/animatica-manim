"""Component registry: registration, validation of storyboards, JSON schema generation."""
from __future__ import annotations

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

    def json_schema(self) -> dict:
        return {name: c.Params.model_json_schema() for name, c in sorted(self._items.items())}

    def validate(self, sb: Storyboard) -> list[str]:
        errors: list[str] = []
        for si, scene in enumerate(sb.scenes, 1):
            for bi, beat in enumerate(scene.beats, 1):
                where = f"scene {si}, beat {bi}"
                comp = self._items.get(beat.component)
                if comp is None:
                    errors.append(f"{where}: unknown component {beat.component!r}. Valid components: {', '.join(self.names())}")
                    continue
                try:
                    comp.Params.model_validate(beat.params)
                except ValidationError as exc:
                    for err in exc.errors():
                        field = ".".join(str(x) for x in err["loc"]) or "params"
                        errors.append(f"{where} ({beat.component}): field '{field}': {err['msg']}")
        return errors


def _builtins() -> list[type[Component]]:
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

