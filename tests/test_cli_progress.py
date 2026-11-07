"""The CLI progress line: real units, honest unknowns, quiet when redirected."""
from __future__ import annotations

import io

import pytest
from typer.testing import CliRunner

from animatica.cli import app as cli_app
from animatica.cli_progress import BAR_CELLS, TerminalProgress, format_progress_line
from animatica.pipeline import MakeResult
from animatica.progress import ProgressEvent


def _ev(stage="render", label="scene 1/2: done", done=1, total=2, finished=False):
    return ProgressEvent(stage=stage, label=label, done=done, total=total, finished=finished)


# ---------------------------------------------------------------------------
# formatting
# ---------------------------------------------------------------------------


def test_bar_shows_the_fraction_that_actually_finished():
    line = format_progress_line(_ev(done=3, total=4, label="scene 3/4: done"), elapsed=12.4)

    assert " 75%" in line
    assert "scene 3/4: done" in line
    assert "· 12s" in line
    assert line.count("█") == BAR_CELLS * 3 // 4


def test_unknown_total_stays_unspecified():
    line = format_progress_line(_ev(total=0, done=0, label="resolving storyboard"))

    assert " --%" in line
    assert "█" not in line, "no filled cells when the amount of work is unknown"
    assert "%" in line


def test_overshoot_is_clamped_to_one_hundred():
    line = format_progress_line(_ev(done=9, total=4, label="late event"))

    assert "100%" in line
    assert line.count("█") == BAR_CELLS


def test_zero_done_renders_an_empty_bar():
    line = format_progress_line(_ev(done=0, total=3, label="scene 1/3: rendering"))

    assert "  0%" in line
    assert "█" not in line


# ---------------------------------------------------------------------------
# behaviour
# ---------------------------------------------------------------------------


def test_redirected_stream_gets_one_line_per_stage_not_a_rewritten_bar():
    stream = io.StringIO()
    reporter = TerminalProgress(stream=stream, enabled=False, tick=0)

    reporter(_ev(label="resolving storyboard", done=0, total=0))
    reporter(_ev(label="resolving storyboard", done=0, total=0))
    reporter(_ev(label="scene 1/2: rendering", done=0, total=3))
    reporter(_ev(label="scene 1/2: done", done=1, total=3))
    reporter.close()

    out = stream.getvalue()
    assert out.count("resolving storyboard") == 1, "no duplicate lines for the same stage"
    assert "\r" not in out, "carriage returns make build logs unreadable"
    assert out.count("\n") == 3
    assert out.endswith("\n")


def test_interactive_stream_rewrites_one_line_and_ends_with_newline():
    stream = io.StringIO()
    reporter = TerminalProgress(stream=stream, enabled=True, tick=0, min_interval=0)

    reporter(_ev(done=0, total=2, label="scene 1/2: rendering"))
    reporter(_ev(done=1, total=2, label="scene 1/2: done"))
    reporter(_ev(done=2, total=2, label="done: video.mp4", finished=True))

    out = stream.getvalue()
    assert out.count("\r") == 3
    assert "  0%" in out and " 50%" in out and "100%" in out
    assert out.endswith("\n")
    reporter.close()  # idempotent


def test_a_broken_stream_never_breaks_the_render():
    class Broken(io.StringIO):
        def write(self, _text):  # noqa: D102 - deliberately raises
            raise ValueError("I/O operation on closed file")

    reporter = TerminalProgress(stream=Broken(), enabled=True, tick=0, min_interval=0)
    reporter.handle(_ev(finished=True))  # must not raise
    reporter.close()


# ---------------------------------------------------------------------------
# the make command uses it
# ---------------------------------------------------------------------------


@pytest.fixture()
def fake_make(monkeypatch, tmp_path):
    events = []

    def fake_make_video(**kwargs):
        report = kwargs["on_progress"]
        report(_ev(stage="storyboard", label="resolving storyboard", done=0, total=0))
        report(_ev(label="scene 1/2: rendering", done=0, total=3))
        report(_ev(label="scene 1/2: done", done=1, total=3))
        report(_ev(label="writing captions and report", done=3, total=3))
        report(_ev(label="done: video.mp4", done=3, total=3, finished=True))
        events.append(kwargs)
        result = MakeResult(
            video=tmp_path / "video.mp4",
            storyboard=tmp_path / "storyboard.json",
            captions=tmp_path / "captions.vtt",
            report=tmp_path / "report.json",
            warnings=[],
        )
        return result

    monkeypatch.setattr("animatica.cli.make_video", fake_make_video)
    return events


def test_make_passes_a_reporter_and_keeps_output_clean(fake_make, tmp_path):
    result = CliRunner().invoke(cli_app, ["make", "explain entropy", "-o", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert fake_make, "make_video was never called"
    assert "on_progress" in fake_make[0], "the reporter must reach the pipeline"
    assert "Video:" in result.output


def test_no_progress_flag_silences_the_reporter(monkeypatch, tmp_path):
    captured = {}

    def fake_make_video(**kwargs):
        captured["reporter"] = kwargs["on_progress"]
        return MakeResult(
            video=tmp_path / "video.mp4",
            storyboard=tmp_path / "storyboard.json",
            captions=tmp_path / "captions.vtt",
            report=tmp_path / "report.json",
            warnings=[],
        )

    monkeypatch.setattr("animatica.cli.make_video", fake_make_video)

    result = CliRunner().invoke(
        cli_app, ["make", "explain entropy", "-o", str(tmp_path), "--no-progress"]
    )

    assert result.exit_code == 0, result.output
    assert captured["reporter"].enabled is False
    assert result.output.count("resolving") == 0, "no progress noise with --no-progress"
