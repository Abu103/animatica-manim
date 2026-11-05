import json
import py_compile
from pathlib import Path

import pytest
from typer.testing import CliRunner

from animatica.cli import app
from animatica.scaffold import class_name_for, scaffold_component

runner = CliRunner()


def test_class_name_for():
    assert class_name_for("number_line") == "NumberLine"
    assert class_name_for("recursion_tree") == "RecursionTree"


def test_rejects_bad_names(tmp_path):
    for bad in ["NumberLine", "2cool", "with-dash", "", "has space"]:
        with pytest.raises(ValueError):
            scaffold_component(bad, tmp_path)


def test_scaffold_creates_all_files(tmp_path):
    # minimal fake project layout
    (tmp_path / "src" / "animatica" / "components").mkdir(parents=True)
    (tmp_path / "src" / "animatica" / "components" / "registry.py").write_text(
        "def _builtins():\n    return [\n    ]\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "COMPONENTS.md").write_text(
        "| `bounce_sequence` | x | 1.0 s |\n\nRegistered component names:\n- bounce_sequence\n"
    )
    (tmp_path / "tests" / "conformance").mkdir(parents=True)
    (tmp_path / "tests" / "conformance" / "expected.json").write_text("{}")

    created = scaffold_component("number_line", tmp_path)
    names = {p.name for p in created}
    assert "number_line.py" in names
    assert "test_number_line.py" in names
    assert "number_line.json" in names
    for p in created:
        assert p.exists(), p

    mod = (tmp_path / "src" / "animatica" / "components" / "number_line.py").read_text(encoding="utf-8")
    assert 'name: ClassVar[str] = "number_line"' in mod
    assert "class NumberLine(Component)" in mod
    py_compile.compile(str(tmp_path / "src" / "animatica" / "components" / "number_line.py"), doraise=True)
    py_compile.compile(str(tmp_path / "tests" / "test_number_line.py"), doraise=True)

    reg = (tmp_path / "src" / "animatica" / "components" / "registry.py").read_text(encoding="utf-8")
    assert "from animatica.components.number_line import NumberLine" in reg
    assert "NumberLine," in reg

    doc = (tmp_path / "docs" / "COMPONENTS.md").read_text(encoding="utf-8")
    assert "`number_line`" in doc and "- number_line" in doc

    expected = json.loads((tmp_path / "tests" / "conformance" / "expected.json").read_text(encoding="utf-8"))
    assert expected["number_line.json"]["scenes"] == 1

    sb = json.loads((tmp_path / "tests" / "conformance" / "number_line.json").read_text(encoding="utf-8"))
    assert sb["scenes"][0]["beats"][0]["component"] == "number_line"


def test_scaffold_refuses_existing_component(tmp_path):
    (tmp_path / "src" / "animatica" / "components").mkdir(parents=True)
    (tmp_path / "src" / "animatica" / "components" / "bounce_sequence.py").write_text("# existing\n")
    with pytest.raises(ValueError, match="already exists"):
        scaffold_component("bounce_sequence", tmp_path)


def test_cli_new_component(tmp_path):
    (tmp_path / "src" / "animatica" / "components").mkdir(parents=True)
    (tmp_path / "src" / "animatica" / "components" / "registry.py").write_text(
        "def _builtins():\n    return [\n    ]\n"
    )
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "COMPONENTS.md").write_text("Registered component names:\n")
    (tmp_path / "tests" / "conformance").mkdir(parents=True)
    (tmp_path / "tests" / "conformance" / "expected.json").write_text("{}")
    result = runner.invoke(app, ["new-component", "timeline", "--root", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert (tmp_path / "src" / "animatica" / "components" / "timeline.py").exists()
