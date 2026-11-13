"""scripts/render_gallery.py: pass/fail logic, table, and the GALLERY.md results block (no render)."""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("render_gallery", ROOT / "scripts" / "render_gallery.py")
rg = importlib.util.module_from_spec(_spec)
sys.modules["render_gallery"] = rg  # dataclasses look the module up by name
_spec.loader.exec_module(rg)


def _gallery(tmp_path: Path, names=("a", "b")) -> Path:
    g = tmp_path / "gallery"
    g.mkdir()
    for n in names:
        (g / f"{n}.json").write_text("{}", encoding="utf-8")
    return g


def _runner(report=None, code=0, write=True):
    """A fake `animatica make`: writes report.json (unless told not to) and returns an exit code."""
    def run(storyboard: Path, out_dir: Path):
        out_dir.mkdir(parents=True, exist_ok=True)
        if write:
            body = report(storyboard.stem) if callable(report) else (report or {"warnings": []})
            (out_dir / "report.json").write_text(json.dumps(body), encoding="utf-8")
        return code, "boom: it broke\n" if code else ""
    return run


def test_every_storyboard_in_the_gallery_is_rendered_and_exit_is_zero(tmp_path, capsys):
    g = _gallery(tmp_path)
    code = rg.main(["--gallery", str(g), "--out", str(tmp_path / "out")], runner=_runner())
    assert code == 0
    assert (tmp_path / "out" / "RESULTS.md").is_file()
    assert "2/2 rendered, 0 failed" in capsys.readouterr().out


def test_a_failed_render_makes_the_exit_code_non_zero(tmp_path):
    g = _gallery(tmp_path)
    assert rg.main(["--gallery", str(g), "--out", str(tmp_path / "o")], runner=_runner(code=1, write=False)) == 1


def test_a_missing_report_is_a_failure_even_when_make_exited_zero(tmp_path):
    r = rg.render_one(_gallery(tmp_path, ("a",)) / "a.json", tmp_path / "o", _runner(write=False))
    assert not r.ok and "report.json" in r.problem


def test_a_component_fallback_is_a_failure(tmp_path):
    runner = _runner({"warnings": [], "fallbacks": ["scene 1 beat 2: table fell back to text"]})
    r = rg.render_one(_gallery(tmp_path, ("a",)) / "a.json", tmp_path / "o", runner)
    assert not r.ok and "fell back" in r.problem


def test_warnings_do_not_fail_a_render_and_are_listed_verbatim(tmp_path):
    warn = "[frame-lint] [warn] safe_area: content 3px outside"
    r = rg.render_one(_gallery(tmp_path, ("a",)) / "a.json", tmp_path / "o", _runner({"warnings": [warn]}))
    assert r.ok and r.warnings == [warn]
    table = rg.format_results([r])
    assert warn in table and "| `a` | ok | 1 |" in table


def test_failure_reason_is_in_the_table(tmp_path):
    r = rg.render_one(_gallery(tmp_path, ("a",)) / "a.json", tmp_path / "o", _runner(code=3, write=False))
    table = rg.format_results([r])
    assert "FAIL" in table and "exited 3" in table and "boom: it broke" in table


def test_an_empty_gallery_fails(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    assert rg.main(["--gallery", str(empty), "--out", str(tmp_path / "o")], runner=_runner()) == 1


def test_write_doc_replaces_only_the_results_block(tmp_path):
    g = _gallery(tmp_path, ("a",))
    doc = tmp_path / "G.md"
    doc.write_text(f"intro\n\n{rg.START_MARK}\nold\n{rg.END_MARK}\n\noutro\n", encoding="utf-8")
    rg.main(["--gallery", str(g), "--out", str(tmp_path / "o"), "--write-doc", "--doc", str(doc)], runner=_runner())
    text = doc.read_text(encoding="utf-8")
    assert text.startswith("intro\n") and text.rstrip().endswith("outro")
    assert "old" not in text and "| `a` | ok | 0 |" in text and "| Commit |" in text


def test_update_doc_needs_both_markers():
    with pytest.raises(ValueError):
        rg.update_doc("no markers here", "x")


def test_the_real_gallery_doc_has_the_markers_and_lists_every_storyboard():
    doc = (ROOT / "docs" / "GALLERY.md").read_text(encoding="utf-8")
    assert rg.START_MARK in doc and rg.END_MARK in doc
    for sb in rg.storyboard_paths():
        assert f"`{sb.name}`" in doc, f"docs/GALLERY.md does not describe {sb.name}"
