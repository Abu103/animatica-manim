import json
from pathlib import Path

from animatica.backends.base import RenderBackend, RenderOptions, RenderResult
from animatica.report import StageTimer, write_report


def test_stage_timer_records_stages_and_total():
    t = StageTimer()
    with t.stage("a"):
        pass
    with t.stage("b"):
        pass
    assert set(t.stages) == {"a", "b"}
    assert t.total == t.stages["a"] + t.stages["b"]
    assert t.total >= 0.0


def test_write_report_produces_stages_and_warnings(tmp_path):
    p = tmp_path / "report.json"
    write_report(p, {"a": 1.0, "b": 2.0}, ["w1", "w2"])
    data = json.loads(p.read_text(encoding="utf-8"))
    assert set(data) == {"stages", "warnings"}
    assert data["stages"] == {"a": 1.0, "b": 2.0}
    assert data["warnings"] == ["w1", "w2"]


def test_fake_backend_satisfies_protocol():
    class Fake:
        name = "fake"

        def render(self, sb, out_dir, opts):
            return RenderResult(
                video=Path(out_dir) / "v.mp4",
                durations=[1.0],
                warnings=[],
                stage_times={},
            )

    assert isinstance(Fake(), RenderBackend)

