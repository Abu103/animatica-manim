import importlib.util
import shutil

import pytest


def _render_env_ok() -> bool:
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

