import json

from typer.testing import CliRunner

from animatica.cli import app

runner = CliRunner()


def test_list_components_json():
    r = runner.invoke(app, ["list-components"])
    assert r.exit_code == 0
    names = json.loads(r.output)
    assert "bounce_sequence" in names and "recursion_tree" in names


def test_component_schema_json():
    r = runner.invoke(app, ["component-schema", "bounce_sequence"])
    assert r.exit_code == 0
    schema = json.loads(r.output)
    assert "values" in schema["properties"]


def test_validate_storyboard_ok_and_bad(tmp_path):
    good = tmp_path / "good.json"
    good.write_text(json.dumps({"version": "1", "title": "t",
                                "scenes": [{"beats": [{"component": "title_card", "params": {"title": "x"}}]}]}))
    r = runner.invoke(app, ["validate", str(good)])
    assert r.exit_code == 0 and json.loads(r.output) == []
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"version": "1", "title": "t",
                               "scenes": [{"beats": [{"component": "nope", "params": {}}]}]}))
    r = runner.invoke(app, ["validate", str(bad)])
    assert r.exit_code == 0
    errors = json.loads(r.output)
    assert any("nope" in e for e in errors)


def test_lint_storyboard_json(tmp_path):
    sb = tmp_path / "sb.json"
    sb.write_text(json.dumps({"version": "1", "title": "t", "scenes": [
        {"beats": [{"component": "bounce_sequence", "params": {"title": "a", "values": [0, 1, 1]}, "caption": "c"}]},
        {"beats": [{"component": "bounce_sequence", "params": {"title": "b", "values": [2, 3]}, "caption": "c"}]},
    ]}))
    r = runner.invoke(app, ["lint", str(sb)])
    assert r.exit_code == 0
    out = json.loads(r.output)
    assert len(out["storyboard"]["scenes"]) == 1  # merged
    assert any("merged" in n for n in out["notes"])
