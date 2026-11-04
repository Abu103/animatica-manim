"""`animatica new-component NAME` scaffold (task card T9).

Writes the files a new component needs, following the bounce_sequence pattern:
component module, registry entry, COMPONENTS.md row, unit test, conformance JSON
+ expected.json entry. The model/agent only fills the TODOs in `play()`.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")

_COMPONENT_TEMPLATE = '''"""{class_name}: TODO one-line description of what this component draws.

Duration: TODO (seconds formula).
"""
from __future__ import annotations

from typing import ClassVar

from pydantic import BaseModel, Field

from animatica.components.base import Component
from animatica.storyboard.models import MAX_TEXT


class {class_name}(Component):
    name: ClassVar[str] = "{name}"

    class Params(BaseModel):
        title: str = Field(max_length=MAX_TEXT)
        # TODO: add params with limits (see bounce_sequence.py for validators)

    def duration(self, p: BaseModel) -> float:
        return 3.0  # TODO: seconds this beat takes; must match what play() animates

    def play(self, scene, p: BaseModel, colors) -> None:
        # TODO: draw and animate on the manim scene. If this raises, the beat
        # degrades to fallback_text() plus a warning; the video still finishes.
        raise NotImplementedError("fill in play()")

    def fallback_text(self, p: BaseModel) -> str:
        return p.title
'''

_TEST_TEMPLATE = '''import pytest

from animatica.components.{name} import {class_name}


def test_duration_positive():
    p = {class_name}.Params(title="demo")
    assert {class_name}().duration(p) > 0


def test_fallback_text():
    p = {class_name}.Params(title="demo")
    assert {class_name}().fallback_text(p) == "demo"


def test_params_reject_empty_title_too_long():
    with pytest.raises(Exception):
        {class_name}.Params(title="x" * 301)
'''

_STORYBOARD_TEMPLATE = {
    "version": "1",
    "title": "{class_name}",
    "scenes": [
        {"beats": [{"component": "{name}", "params": {"title": "Demo"}, "caption": "TODO caption"}]}
    ],
}


def class_name_for(name: str) -> str:
    return "".join(part.capitalize() for part in name.split("_"))


def scaffold_component(name: str, root: Path) -> list[Path]:
    """Create all files for component `name` under project `root`. Returns created paths."""
    if not _NAME_RE.match(name):
        raise ValueError(
            f"invalid component name {name!r}: use lowercase snake_case (letters, digits, underscores, starting with a letter)"
        )
    root = Path(root)
    comp_dir = root / "src" / "animatica" / "components"
    comp_path = comp_dir / f"{name}.py"
    if comp_path.exists():
        raise ValueError(f"component file already exists: {comp_path}")

    cls = class_name_for(name)
    created: list[Path] = []

    comp_dir.mkdir(parents=True, exist_ok=True)
    comp_path.write_text(_COMPONENT_TEMPLATE.format(name=name, class_name=cls), encoding="utf-8")
    created.append(comp_path)

    # registry entry
    reg_path = comp_dir / "registry.py"
    reg = reg_path.read_text(encoding="utf-8")
    reg = re.sub(
        r"(def _builtins\(\)[^\n]*\n)",
        rf"\1    from animatica.components.{name} import {cls}\n",
        reg,
        count=1,
    )
    reg = reg.replace("    return [\n", f"    return [\n        {cls},\n", 1)
    reg_path.write_text(reg, encoding="utf-8")
    created.append(reg_path)

    # docs row + name list
    doc_path = root / "docs" / "COMPONENTS.md"
    doc = doc_path.read_text(encoding="utf-8")
    doc = doc.replace(
        "| `bounce_sequence` |",
        f"| `{name}` | `title`, TODO | 3.0 s |\n| `bounce_sequence` |",
        1,
    )
    doc = doc.replace("- bounce_sequence\n", f"- bounce_sequence\n- {name}\n", 1)
    doc_path.write_text(doc, encoding="utf-8")
    created.append(doc_path)

    # unit test
    test_dir = root / "tests"
    test_dir.mkdir(parents=True, exist_ok=True)
    test_path = test_dir / f"test_{name}.py"
    test_path.write_text(_TEST_TEMPLATE.format(name=name, class_name=cls), encoding="utf-8")
    created.append(test_path)

    # conformance storyboard + expected.json entry
    conf_dir = root / "tests" / "conformance"
    conf_dir.mkdir(parents=True, exist_ok=True)
    sb_path = conf_dir / f"{name}.json"
    sb_text = json.dumps(_STORYBOARD_TEMPLATE).replace("{name}", name).replace("{class_name}", cls)
    sb_path.write_text(sb_text + "\n", encoding="utf-8")
    created.append(sb_path)

    exp_path = conf_dir / "expected.json"
    expected = json.loads(exp_path.read_text(encoding="utf-8")) if exp_path.exists() else {}
    expected[f"{name}.json"] = {"scenes": 1, "duration": 3.0}
    exp_path.write_text(json.dumps(expected, indent=2) + "\n", encoding="utf-8")
    created.append(exp_path)

    return created
