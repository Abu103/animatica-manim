import importlib.util
import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(scope="session", autouse=True)
def _own_text_cache():
    """Give this process its own Manim text cache.

    Manim caches the SVG of every text it renders, under
    ``<media_dir>/texts``, keyed by the text and the style -- but not by the
    process. Two test workers that render the same string at the same time
    write the same file, and one of them can read it half written: the text
    comes out with the wrong size and the geometry tests fail at random.

    The cache lives under the repository's own ``media`` directory, which is
    ignored by git, and is removed when the session ends.
    """
    try:
        from manim import config
    except Exception:  # pragma: no cover - manim is not installed
        yield
        return

    root = Path(__file__).resolve().parent.parent / "media"
    worker = os.environ.get("PYTEST_XDIST_WORKER", "main")
    own = root / f"pytest-texts-{worker}-{os.getpid()}"
    own.mkdir(parents=True, exist_ok=True)
    previous = config.media_dir
    config.media_dir = own
    try:
        yield
    finally:
        config.media_dir = previous
        shutil.rmtree(own, ignore_errors=True)


def _render_env_ok() -> bool:
    # The CLI puts a TinyTeX install on PATH for itself; a bare pytest process has
    # to do the same, otherwise Windows CI skips tests it could actually run.
    try:
        import os

        from animatica.doctor import ensure_tex_on_path, tinytex_bin_dirs

        ensure_tex_on_path()
        if shutil.which("latex") and not shutil.which("dvisvgm"):
            # tlmgr sometimes drops dvisvgm outside bin/<arch>; find it and use it.
            for bindir in tinytex_bin_dirs():
                for hit in bindir.parents[1].rglob("dvisvgm*"):
                    if hit.is_file():
                        os.environ["PATH"] = str(hit.parent) + os.pathsep + os.environ["PATH"]
                        break
                if shutil.which("dvisvgm"):
                    break
    except Exception:  # pragma: no cover - doctor is optional here
        pass
    return (importlib.util.find_spec("manim") is not None
            and shutil.which("latex") is not None and shutil.which("dvisvgm") is not None
            and (shutil.which("ffmpeg") is not None or importlib.util.find_spec("imageio_ffmpeg") is not None))


def pytest_collection_modifyitems(config, items):
    if _render_env_ok():
        return
    skip = pytest.mark.skip(reason="needs manim + latex + dvisvgm + ffmpeg (system or imageio-ffmpeg)")
    for item in items:
        if "render" in item.keywords:
            item.add_marker(skip)


@pytest.fixture
def tiny_video(tmp_path):
    """A real 2-second mp4, made with the ffmpeg binary the project already ships.

    Tests that need actual pixels used to depend on a checked-in gallery video,
    which made them fail (not skip) on a fresh clone.
    """
    import subprocess

    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:  # pragma: no cover - system ffmpeg only
        exe = shutil.which("ffmpeg")
    if not exe:
        pytest.skip("no ffmpeg available to build a test video")
    out = tmp_path / "clip.mp4"
    subprocess.run(
        [exe, "-y", "-f", "lavfi", "-i", "testsrc=size=160x90:rate=15:duration=2",
         "-pix_fmt", "yuv420p", "-loglevel", "error", str(out)],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    assert out.is_file() and out.stat().st_size > 0
    return out


@pytest.fixture(autouse=True)
def _isolated_config(tmp_path, monkeypatch):
    """Tests never read or write the developer's real ~/.config/animatica."""
    monkeypatch.setenv("ANIMATICA_CONFIG_DIR", str(tmp_path / "animatica-config"))


@pytest.fixture
def run_component(tmp_path):
    """Run one component on a real manim Scene (480p15, no movie written). Returns (scene, warnings)."""
    def _run(component, params, colors=None):
        from manim import Scene, tempconfig
        from animatica.components.theme import PALETTES
        colors = colors or PALETTES["dark-blue"]
        warnings: list[str] = []

        class S(Scene):
            def construct(self):
                self.warnings = warnings
                component.play(self, params, colors)

        with tempconfig({"quality": "low_quality", "frame_rate": 15, "write_to_movie": False,
                         "dry_run": True, "disable_caching": True, "media_dir": str(tmp_path / "media"),
                         "verbosity": "ERROR", "progress_bar": "none"}):
            s = S()
            s.render()
        return s, warnings
    return _run


@pytest.fixture
def registry():
    from animatica.components.registry import default_registry
    return default_registry()

