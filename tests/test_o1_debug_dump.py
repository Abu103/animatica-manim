"""O1: --debug dumps the raw provider reply on every parse failure.

The dump is the only way to see the real malformed shape: raw text goes to
<out_dir>/debug/<stage>_<scene>_<attempt>.txt and the 80 characters around
the reported error position are printed. Dumps happen only under --debug.
"""
from __future__ import annotations

import json

from typer.testing import CliRunner

from animatica.ai.debug_dump import dump_parse_failure
from animatica.ai.repair import generate_storyboard, generate_storyboard_two_stage, repair_with_facts
from animatica.cli import app
from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard


class _Provider:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []
        self.model = "m"

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, prompt: str, schema: dict) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0)


GOOD = ('{"version":"1","title":"T","scenes":[{"beats":['
        '{"component":"title_card","params":{"title":"B"},"caption":"hi"}]}]}')
BAD = 'prefix {"version":"1" "title":"T"}'  # Expecting ':' delimiter


def test_dump_writes_raw_and_prints_context():
    raw = "x" * 100 + "BROKEN" + "y" * 100
    error = json.JSONDecodeError("Expecting ':' delimiter", raw, 103)
    lines: list[str] = []
    dump_parse_failure(raw, out_dir="/tmp/o1", stage="fill", scene=2, attempt=3,
                       error=error, debug=True, echo=lines.append)
    assert "BROKEN" in "".join(lines)
    assert "char 103" in "".join(lines)


def test_no_dump_without_debug(tmp_path, capsys):
    dump_parse_failure(BAD, out_dir=tmp_path, stage="fill", scene=0, attempt=1,
                       error=ValueError("bad"), debug=False)
    assert not (tmp_path / "debug").exists()
    assert capsys.readouterr().out == ""


def test_single_stage_dumps_raw_reply(tmp_path, capsys):
    provider = _Provider(BAD, GOOD)
    generate_storyboard("topic", provider, default_registry(),
                        debug=True, out_dir=tmp_path)
    path = tmp_path / "debug" / "storyboard_0_1.txt"
    assert path.read_text(encoding="utf-8") == BAD
    out = capsys.readouterr().out
    assert "around char" in out and "prefix" in out


def test_two_stage_dumps_outline_and_fill(tmp_path):
    bad_outline = '{"version":"1","title":"T","scenes":[{"beats":[{"component" "x"}]}]}'
    provider = _Provider(bad_outline,
                         '{"version":"1","title":"T","scenes":[{"beats":[{"component":"title_card","intent":"i"}]}]}',
                         BAD, GOOD)
    generate_storyboard_two_stage("topic", provider, default_registry(),
                                  debug=True, out_dir=tmp_path)
    assert (tmp_path / "debug" / "outline_0_1.txt").read_text(encoding="utf-8") == bad_outline
    assert (tmp_path / "debug" / "fill_1_1.txt").read_text(encoding="utf-8") == BAD


def test_repair_dumps_raw_reply(tmp_path):
    bad = Storyboard.model_validate(json.loads(
        '{"version":"1","title":"T","scenes":[{"beats":['
        '{"component":"stat_callout","params":{"value":"12%","label":"g"},'
        '"caption":"grew 40%"}]}]}'))
    fixed = GOOD
    provider = _Provider(BAD, fixed)
    repair_with_facts("topic", bad, provider, default_registry(),
                      debug=True, out_dir=tmp_path)
    assert (tmp_path / "debug" / "repair_0_1.txt").read_text(encoding="utf-8") == BAD


def test_cli_debug_flag_reaches_the_dump(tmp_path, monkeypatch):
    import animatica.pipeline as pipeline
    from animatica.backends.base import RenderResult
    from typing import ClassVar

    class FakeBackend:
        name = "fake"
        version = "9.9"
        supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]

        def capabilities(self):
            return self.supported_capabilities

        def render(self, sb, out_dir, opts):
            video = out_dir / "video.mp4"
            video.write_bytes(b"x")
            return RenderResult(video=video, durations=[1.0], warnings=[], stage_times={})

    monkeypatch.setattr(pipeline, "default_backends", lambda: {"fake": FakeBackend()})
    provider = _Provider(BAD, GOOD)
    monkeypatch.setattr(pipeline, "get_provider", lambda name, cfg: provider)
    out = tmp_path / "out"
    result = CliRunner().invoke(
        app, ["make", "o1 topic", "--provider", "fake", "--backend", "fake",
              "--no-frame-lint", "--debug", "-o", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert (out / "debug" / "storyboard_0_1.txt").is_file()
