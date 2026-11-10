import json
from pathlib import Path

from animatica.components.registry import default_registry
from animatica.conformance import conformance_check
from animatica.storyboard.models import load_storyboard

CONFORMANCE_DIR = Path(__file__).parent / "conformance"


# ---------------------------------------------------------------------------
# The corpus itself is rendered by the render gate, not here
# ---------------------------------------------------------------------------
#
# Rendering the whole corpus takes more than a minute, and the render gate
# does exactly that once per run and checks more than the suite could: the
# lint findings, the fallbacks, the timing and the promised durations. Doing
# it again in the suite doubled the cost of every CI run for the same
# evidence, so the corpus is rendered in one place: the gate.


def _expected() -> dict[str, dict]:
    return json.loads((CONFORMANCE_DIR / "expected.json").read_text(encoding="utf-8"))


class _Backend:
    """A backend that reports the durations it is told to report."""

    name = "fake"

    def __init__(self, durations: dict[str, list[float]] | None = None):
        self.durations = durations or {}
        self.rendered: list[str] = []

    def render(self, sb, out_dir, opts):
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "video.mp4").write_bytes(b"x")
        from animatica.backends.base import RenderResult

        # conformance_check renders into a directory named after the storyboard.
        name = f"{out_dir.name}.json"
        self.rendered.append(name)
        return RenderResult(
            video=out_dir / "video.mp4",
            durations=self.durations.get(name, [0.0]),
            warnings=[],
            stage_times={},
        )


def test_conformance_check_accepts_a_backend_that_hits_the_promised_durations(tmp_path):
    """The check passes when the backend reports what the corpus promises."""
    expected = _expected()
    backend = _Backend({name: [expected[name]["duration"]] for name in expected})

    failures = conformance_check(backend, tmp_path)

    assert failures == [], failures
    assert len(backend.rendered) == len(expected)


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
    expected = json.loads((CONFORMANCE_DIR / "expected.json").read_text(encoding="utf-8"))
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
