import json
from pathlib import Path

import pytest

from animatica.backends.base import RenderOptions
from animatica.backends.manim_backend import ManimBackend
from animatica.components.registry import default_registry
from animatica.conformance import conformance_check
from animatica.storyboard.models import load_storyboard

CONFORMANCE_DIR = Path(__file__).parent / "conformance"


@pytest.mark.render
def test_manim_backend_passes_conformance(tmp_path):
    failures = conformance_check(ManimBackend(), tmp_path)
    assert failures == [], failures


def test_fake_backend_wrong_durations_reported(tmp_path):
    class FakeBackend:
        name = "fake"

        def render(self, sb, out_dir, opts):
            out_dir = Path(out_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "video.mp4").write_bytes(b"x")
            from animatica.backends.base import RenderResult

            return RenderResult(
                video=out_dir / "video.mp4",
                durations=[999.0],
                warnings=[],
                stage_times={},
            )

    failures = conformance_check(FakeBackend(), tmp_path)
    assert len(failures) > 0, "expected duration mismatches to be reported"


def test_conformance_expected_matches_actual_durations():
    reg = default_registry()
    expected = json.loads((CONFORMANCE_DIR / "expected.json").read_text())
    for fname, exp in expected.items():
        sb = load_storyboard(CONFORMANCE_DIR / fname)
        assert len(sb.scenes) == exp["scenes"], fname
        total = 0.0
        for scene in sb.scenes:
            for beat in scene.beats:
                comp = reg.get(beat.component)
                params = comp.Params.model_validate(beat.params)
                total += comp.duration(params)
        assert abs(total - exp["duration"]) <= 0.2, (fname, total, exp["duration"])

