"""V1e: verify wired into the pipeline -- warnings, report block, CLI flags.

Facts are computed once per beat per run (override 5): verify_storyboard
caches them and hands the map to both checks. A beat whose facts() raised
or whose params did not validate counts as unchecked, never passed.
"""
from __future__ import annotations

import json
from typing import ClassVar

from pydantic import BaseModel
from typer.testing import CliRunner

from animatica.cli import app
from animatica.components.base import Component
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.pipeline import make_video
from animatica.storyboard.models import Beat, Scene, Storyboard
from animatica.verify import verify_storyboard
from animatica.verify.facts import Fact


class _CountingFacts(Component):
    """Counts its own facts() calls: the once-per-beat override needs evidence."""

    name: ClassVar[str] = "counting_facts"

    class Params(BaseModel):
        pass

    def __init__(self) -> None:
        self.calls = 0

    def duration(self, p: BaseModel) -> float:
        return 1.0

    def play(self, scene, p, colors) -> None:
        raise NotImplementedError

    def fallback_text(self, p: BaseModel) -> str:
        return ""

    def facts(self, p: BaseModel) -> list[Fact]:
        self.calls += 1
        return [Fact("value", "x", 5.0, "the value is 5")]


class _BrokenFacts(Component):
    name: ClassVar[str] = "broken_facts"
    domain: ClassVar[str] = "plain axes"

    class Params(BaseModel):
        pass

    def duration(self, p: BaseModel) -> float:
        return 1.0

    def play(self, scene, p, colors) -> None:
        raise NotImplementedError

    def fallback_text(self, p: BaseModel) -> str:
        return ""

    def facts(self, p: BaseModel) -> list[Fact]:
        raise RuntimeError("boom")


def _sb(*beats):
    return Storyboard(title="t", scenes=[Scene(beats=list(beats))])


def _bad_storyboard(tmp_path):
    """A --from storyboard with one invented figure in its caption."""
    data = {
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{
            "component": "stat_callout",
            "params": {"value": "12%", "label": "growth"},
            "caption": "grew 40%",
        }]}],
    }
    path = tmp_path / "sb.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_verify_storyboard_finds_and_counts():
    sb = _sb(Beat(component="stat_callout",
                  params={"value": "12%", "label": "growth"}, caption="grew 40%"))
    result = verify_storyboard(sb, default_registry())
    assert len(result.findings) == 1
    assert result.findings[0].severity == "error"
    assert result.by_severity == {"error": 1, "warn": 0}
    assert result.checked >= 1  # the number 40 was looked at


def test_verify_storyboard_is_idempotent():
    sb = _sb(Beat(component="stat_callout",
                  params={"value": "12%", "label": "growth"}, caption="grew 40%"))
    first = verify_storyboard(sb, default_registry())
    second = verify_storyboard(sb, default_registry())
    assert first.findings == second.findings
    assert first.checked == second.checked
    assert first.unchecked == second.unchecked


def test_facts_are_computed_once_per_beat():
    reg = ComponentRegistry()
    reg.register(_CountingFacts)
    sb = _sb(
        Beat(component="counting_facts", params={}, caption="a"),
        Beat(component="counting_facts", params={}, caption="b"),
    )
    verify_storyboard(sb, reg)
    assert reg.get("counting_facts").calls == 2, "facts must be cached, not recomputed"


def test_facts_failure_counts_as_unchecked_not_passed():
    reg = ComponentRegistry()
    reg.register(_BrokenFacts)
    sb = _sb(Beat(component="broken_facts", params={}, caption="says 40"))
    result = verify_storyboard(sb, reg)
    assert result.findings == [], "an unchecked beat must not produce findings"
    assert result.checked == 0, "nothing was checked on the broken beat"
    assert any("says 40" in s for s in result.unchecked)


def test_invalid_params_count_as_unchecked():
    sb = _sb(Beat(component="stat_callout",
                  params={"value": "x" * 400, "label": "growth"}, caption="grew 40%"))
    result = verify_storyboard(sb, default_registry())
    assert result.findings == []
    assert result.checked == 0
    assert any("grew 40%" in s for s in result.unchecked)


def test_make_video_verifies_and_reports(tmp_path):
    sb_path = _bad_storyboard(tmp_path)
    result = make_video(storyboard_path=sb_path, out_dir=tmp_path, preview=True)
    assert any(w.startswith("verify: scene 0 beat 0 caption") for w in result.warnings)
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    verification = report["verification"]
    assert verification["failed"] == 1
    assert verification["passed"] == verification["checked"] - verification["failed"]
    assert verification["fixed"] == 0 and verification["sent_back"] == 0
    assert isinstance(verification["unchecked"], list)


def test_make_video_no_verify_writes_no_block(tmp_path):
    sb_path = _bad_storyboard(tmp_path)
    result = make_video(storyboard_path=sb_path, out_dir=tmp_path, preview=True, verify=False)
    assert not [w for w in result.warnings if w.startswith("verify:")]
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert "verification" not in report


def test_warn_only_is_not_a_failure_and_does_not_trigger_strict(tmp_path):
    # array_viz [3, 1, 2] with "the array is sorted" is a warn, not an error:
    # warn-only findings are shown in the report but never block a strict run.
    data = {
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{
            "component": "array_viz",
            "params": {"title": "t", "values": [3, 1, 2]},
            "caption": "the array is sorted",
        }]}],
    }
    sb_path = tmp_path / "warn.json"
    sb_path.write_text(json.dumps(data), encoding="utf-8")
    out = tmp_path / "warn-out"
    result = make_video(storyboard_path=sb_path, out_dir=out,
                        preview=True, strict=True)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["verification"]["failed"] == 0
    assert report["verification"]["warned"] == 1
    assert any("verify:" in w and "not sorted" in w for w in result.warnings)


def test_domain_rule_runs_even_when_facts_fail():
    reg = ComponentRegistry()
    reg.register(_BrokenFacts)
    sb = _sb(Beat(component="broken_facts", params={}, caption="the frequency domain"))
    result = verify_storyboard(sb, reg)
    # The domain rule needs no facts, so a facts-failure beat can still be
    # caught on its domain wording; its numbers stay unchecked.
    assert any(f.severity == "error" and "frequency domain" in f.message
               for f in result.findings)
    assert any("broken_facts" in s for s in result.unchecked)


def test_strict_exits_nonzero_after_writing_the_report(tmp_path):
    sb_path = _bad_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        app, ["make", "--from", str(sb_path), "--strict", "--preview", "-o", str(tmp_path)]
    )
    assert result.exit_code != 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["verification"]["failed"] == 1


def test_cli_flags_exist_and_default_on(tmp_path):
    sb_path = _bad_storyboard(tmp_path)
    runner = CliRunner()
    result = runner.invoke(app, ["make", "--from", str(sb_path), "--preview",
                                 "-o", str(tmp_path / "plain")])
    assert result.exit_code == 0, result.output
    report = json.loads((tmp_path / "plain" / "report.json").read_text(encoding="utf-8"))
    assert report["verification"]["failed"] == 1


def test_verify_strict_error_names_the_failure():
    from animatica.verify import VerifyStrictError

    sb = _sb(Beat(component="stat_callout",
                  params={"value": "12%", "label": "growth"}, caption="grew 40%"))
    result = verify_storyboard(sb, default_registry())
    message = str(VerifyStrictError(result))
    assert "1" in message and "error" in message
    for word in ("true", "correct", "verified facts"):
        assert word not in message.lower()
