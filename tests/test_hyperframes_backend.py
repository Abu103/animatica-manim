"""Tests for the HyperFrames backend: command shape, failures, warnings.

No Node is needed: the CLI call is injected. What is pinned here is the
contract with HyperFrames (arguments, working directory, output file) and the
error messages a user or an agent will actually see.
"""
import json
import subprocess
from pathlib import Path

import pytest

from animatica.backends.base import RenderOptions
from animatica.backends.hyperframes.backend import (
    CLI_ENV,
    HYPERFRAMES_VERSION,
    HyperFramesBackend,
)
from animatica.backends.hyperframes.compose import content_hash
from animatica.backends.hyperframes.plan import PlanError
from animatica.storyboard.models import Storyboard

GALLERY = Path(__file__).resolve().parent.parent / "docs" / "gallery"


class RecordingRunner:
    """Stand-in for the CLI: records the call and optionally writes the video."""

    def __init__(self, produce_video: bool = True, error: Exception | None = None) -> None:
        self.calls: list[tuple[list[str], Path]] = []
        self.produce_video = produce_video
        self.error = error

    def __call__(self, cmd: list[str], cwd: Path) -> None:
        self.calls.append((list(cmd), Path(cwd)))
        if self.error is not None:
            raise self.error
        if self.produce_video:
            Path(cmd[cmd.index("--output") + 1]).write_bytes(b"not really an mp4")


def storyboard(data=None) -> Storyboard:
    data = data or json.loads((GALLERY / "howto.json").read_text())
    return Storyboard.model_validate(data)


@pytest.fixture
def cli_env(monkeypatch):
    monkeypatch.setenv(CLI_ENV, "/opt/hyperframes/bin/hyperframes")
    return "/opt/hyperframes/bin/hyperframes"


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


def test_render_writes_composition_and_returns_result(cli_env, tmp_path):
    runner = RecordingRunner()
    backend = HyperFramesBackend(runner=runner)

    result = backend.render(storyboard(), tmp_path / "out", RenderOptions())

    assert result.video == tmp_path / "out" / "video.mp4"
    assert result.video.exists()
    assert result.durations == [3.0, 7.0]
    assert result.warnings == []
    assert set(result.stage_times) == {"plan", "compose", "render"}

    composition = tmp_path / "out" / "index.html"
    assert composition.exists()
    assert "How to Boil an Egg" in composition.read_text(encoding="utf-8")


def test_cli_is_called_the_way_hyperframes_expects(cli_env, tmp_path):
    runner = RecordingRunner()
    HyperFramesBackend(runner=runner).render(storyboard(), tmp_path, RenderOptions())

    (cmd, cwd), = runner.calls
    assert cmd[0] == cli_env
    assert cmd[1] == "render"
    assert cmd[2:4] == ["--output", str(tmp_path / "video.mp4")]
    assert cmd[-1] == "--no-browser-gpu"
    assert cwd == tmp_path  # index.html must be the composition in the cwd


def test_composition_is_byte_identical_across_renders(cli_env, tmp_path):
    backend = HyperFramesBackend(runner=RecordingRunner())
    backend.render(storyboard(), tmp_path / "a", RenderOptions())
    backend.render(storyboard(), tmp_path / "b", RenderOptions())

    a = (tmp_path / "a" / "index.html").read_text(encoding="utf-8")
    b = (tmp_path / "b" / "index.html").read_text(encoding="utf-8")
    assert content_hash(a) == content_hash(b)


def test_no_captions_removes_the_caption_band(cli_env, tmp_path):
    runner = RecordingRunner()
    HyperFramesBackend(runner=runner).render(storyboard(), tmp_path, RenderOptions(captions=False))

    html = (tmp_path / "index.html").read_text(encoding="utf-8")
    assert 'class="line c-muted l-caption"' not in html  # no caption element is emitted
    assert "Four simple steps." not in html


# ---------------------------------------------------------------------------
# Refusals (before any subprocess work)
# ---------------------------------------------------------------------------


def test_unsupported_component_fails_before_the_cli_runs(cli_env, tmp_path):
    runner = RecordingRunner()
    backend = HyperFramesBackend(runner=runner)
    sb = storyboard({"version": "1", "title": "g", "scenes": [
        {"beats": [{"component": "graph", "params": {"fn": "sin(x)"}}]}]})

    with pytest.raises(PlanError, match="manim"):
        backend.render(sb, tmp_path, RenderOptions())
    assert runner.calls == []


def test_vertical_export_is_refused_not_ignored(cli_env, tmp_path):
    with pytest.raises(ValueError, match="vertical"):
        HyperFramesBackend(runner=RecordingRunner()).render(
            storyboard(), tmp_path, RenderOptions(vertical=True)
        )


def test_missing_cli_message_says_exactly_what_to_do(monkeypatch, tmp_path):
    monkeypatch.delenv(CLI_ENV, raising=False)
    monkeypatch.setattr("animatica.backends.hyperframes.backend.shutil.which", lambda name: None)

    with pytest.raises(RuntimeError) as excinfo:
        HyperFramesBackend(runner=RecordingRunner()).render(storyboard(), tmp_path, RenderOptions())

    message = str(excinfo.value)
    assert f"npm install -g hyperframes@{HYPERFRAMES_VERSION}" in message
    assert CLI_ENV in message
    assert "--backend manim" in message


# ---------------------------------------------------------------------------
# Failures surface real output
# ---------------------------------------------------------------------------


def test_cli_failure_shows_the_tail_of_its_output(cli_env, tmp_path):
    error = subprocess.CalledProcessError(
        1, "hyperframes", output="starting", stderr="line one\nlast line: browser not found"
    )
    with pytest.raises(RuntimeError) as excinfo:
        HyperFramesBackend(runner=RecordingRunner(error=error)).render(
            storyboard(), tmp_path, RenderOptions()
        )

    message = str(excinfo.value)
    assert "hyperframes render failed (exit 1)" in message
    assert "last line: browser not found" in message


def test_missing_output_file_is_an_error(cli_env, tmp_path):
    with pytest.raises(RuntimeError, match="produced no video.mp4"):
        HyperFramesBackend(runner=RecordingRunner(produce_video=False)).render(
            storyboard(), tmp_path, RenderOptions()
        )


# ---------------------------------------------------------------------------
# Layout problems are warnings, never silent
# ---------------------------------------------------------------------------


def test_layout_problems_become_warnings_and_still_render(cli_env, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "animatica.backends.hyperframes.backend.problems",
        lambda plan: ["scene 1, beat 1: 'A' and 'B' overlap"],
    )
    runner = RecordingRunner()
    result = HyperFramesBackend(runner=runner).render(storyboard(), tmp_path, RenderOptions())

    assert result.warnings == ["layout: scene 1, beat 1: 'A' and 'B' overlap"]
    assert runner.calls  # rendered anyway: warnings never abort a video


# ---------------------------------------------------------------------------
# Registration and capabilities
# ---------------------------------------------------------------------------


def test_backend_is_registered_and_reports_itself():
    from animatica.backends import default_backends

    backends = default_backends()
    assert "hyperframes" in backends
    backend = backends["hyperframes"]
    assert isinstance(backend, HyperFramesBackend)
    assert backend.name == "hyperframes"
    assert backend.version == HYPERFRAMES_VERSION


def test_capabilities_are_empty_without_node(monkeypatch):
    backend = HyperFramesBackend(runner=RecordingRunner())
    monkeypatch.setattr("animatica.backends.hyperframes.backend.shutil.which", lambda name: None)
    assert backend.capabilities() == []


def test_capabilities_present_with_node_and_cli(monkeypatch):
    backend = HyperFramesBackend(runner=RecordingRunner())
    monkeypatch.setattr(
        "animatica.backends.hyperframes.backend.shutil.which",
        lambda name: "/usr/bin/" + name,
    )
    assert backend.capabilities() == ["html", "css"]
