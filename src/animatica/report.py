"""Per-stage timing and report writing."""
from __future__ import annotations

from contextlib import contextmanager
import json
from pathlib import Path
import time


class StageTimer:
    """Records seconds spent in named stages and exposes their total."""

    def __init__(self) -> None:
        self.stages: dict[str, float] = {}

    @contextmanager
    def stage(self, name: str):
        start = time.perf_counter()
        try:
            yield
        finally:
            self.stages[name] = self.stages.get(name, 0.0) + (time.perf_counter() - start)

    @property
    def total(self) -> float:
        return sum(self.stages.values())


def write_report(path: Path, stage_times: dict[str, float], warnings: list[str], backend: dict[str, str] | None = None, scene_durations: list[float] | None = None) -> None:
    """Write `report.json` with `stages`, `warnings`, `scene_durations`, and `backend` keys.

    `scene_durations` maps scene index to the cumulative duration of that scene in
    seconds (e.g. [3.2, 4.1, 2.8] means scene 0 is 3.2s, scene 1 is 4.1s, scene 2 is
    2.8s). These are computed from component durations and are used by MCP
    `preview_frame` to map (scene_index, t) -> absolute video time.

    Existing reports (without `scene_durations`) are still readable: `preview_frame`
    reports an actionable error if durations are missing.
    """
    report = {"stages": dict(stage_times), "warnings": list(warnings), "scene_durations": list(scene_durations or [])}
    if backend is not None:
        report["backend"] = dict(backend)
    Path(path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

