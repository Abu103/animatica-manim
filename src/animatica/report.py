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


def write_report(path: Path, stage_times: dict[str, float], warnings: list[str], backend: dict[str, str] | None = None) -> None:
    """Write `report.json` with `stages` and `warnings` keys, plus `backend` when given."""
    report = {"stages": dict(stage_times), "warnings": list(warnings)}
    if backend is not None:
        report["backend"] = dict(backend)
    Path(path).write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

