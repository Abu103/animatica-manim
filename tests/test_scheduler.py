import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Callable

import pytest

from animatica.backends.scheduler import (
    concat_videos,
    parse_cgroup_quota,
    pick_workers,
    render_scenes_parallel,
    system_info,
)


def _slow_first_render_one(i: int) -> Path:
    import time

    time.sleep(0.1 if i == 0 else 0.01)
    return Path(f"/tmp/ordered/scene_{i}.mp4")


def _failing_render_one(i: int) -> Path:
    if i == 2:
        raise RuntimeError("boom in scene 2")
    return Path(f"/tmp/fail/scene_{i}.mp4")


_serial_order: list[int] = []


def _serial_render_one(i: int) -> Path:
    _serial_order.append(i)
    return Path(f"/tmp/serial/scene_{i}.mp4")


def test_output_in_scene_order_even_if_later_finishes_first():
    # scene 0 renders slower than scenes 1,2 but output must stay in index order
    results = render_scenes_parallel(_slow_first_render_one, 3, jobs=2)
    assert results == [
        Path("/tmp/ordered/scene_0.mp4"),
        Path("/tmp/ordered/scene_1.mp4"),
        Path("/tmp/ordered/scene_2.mp4"),
    ]


def test_exception_surfaces_scene_index():
    with pytest.raises(RuntimeError) as exc:
        render_scenes_parallel(_failing_render_one, 4, jobs=2)
    assert "scene 2" in str(exc.value)


def test_jobs_one_runs_serially():
    _serial_order.clear()

    results = render_scenes_parallel(_serial_render_one, 3, jobs=1)
    assert _serial_order == [0, 1, 2]
    assert len(results) == 3


def test_default_jobs_clamps_to_cpu_count():
    import animatica.backends.scheduler as sched

    orig = os.cpu_count
    os.cpu_count = lambda: 2  # type: ignore[assignment]
    try:
        n = sched.render_scenes_parallel(lambda i: Path(f"/tmp/x/{i}.mp4"), 5, jobs=None)
        assert len(n) == 5
    finally:
        os.cpu_count = orig


def test_concat_videos_builds_list_args(tmp_path, monkeypatch):
    called = {}

    def fake_run(args, **kwargs):
        called["args"] = args
        called["kwargs"] = kwargs
        # pretend ffmpeg created the dst
        Path(args[-1]).touch()
        return None

    monkeypatch.setattr("animatica.backends.scheduler.subprocess.run", fake_run)

    clips = [tmp_path / "a b.mp4", tmp_path / "c.mp4"]
    for c in clips:
        c.touch()
    dst = tmp_path / "out.mp4"
    concat_videos(clips, dst, ffmpeg="ffmpeg")

    args = called["args"]
    assert isinstance(args, list)
    assert "ffmpeg" in args
    assert "-c" in args and "copy" in args
    assert str(dst) in args
    # no shell: args is a list, not a string
    assert not isinstance(args, str)
    assert dst.exists()


@pytest.mark.render
def test_two_scene_storyboard_produces_one_mp4(tmp_path):
    from animatica.backends.manim_backend import ManimBackend
    from animatica.backends.base import RenderOptions
    from animatica.storyboard.models import Storyboard

    sb = Storyboard.model_validate(
        {
            "version": "1",
            "title": "Two",
            "scenes": [
                {"beats": [{"component": "title_card", "params": {"title": "One"}}]},
                {"beats": [{"component": "title_card", "params": {"title": "Two"}}]},
            ],
        }
    )

    def render_one(i: int) -> Path:
        single = Storyboard.model_validate(
            {"version": "1", "title": "Two", "scenes": [sb.scenes[i]]}
        )
        out = tmp_path / f"scene_{i}"
        return ManimBackend().render(single, out, RenderOptions(quality="preview")).video

    results = render_scenes_parallel(render_one, 2, jobs=1)
    assert len(results) == 2
    for r in results:
        assert r.exists()


def test_concat_list_uses_absolute_posix_paths_even_for_relative_output(tmp_path, monkeypatch):
    """Regression: relative -o dir made ffmpeg look in out/out/clip.mp4 (exit -2 on Windows)."""
    monkeypatch.chdir(tmp_path)
    (tmp_path / "out").mkdir()
    seen = {}

    def fake_run(args, **kwargs):
        seen["list"] = Path(args[args.index("-i") + 1]).read_text(encoding="utf-8")
        Path(args[-1]).touch()

    monkeypatch.setattr("animatica.backends.scheduler.subprocess.run", fake_run)
    clips = [Path("out") / "it's a.mp4", Path("out") / "b.mp4"]
    concat_videos(clips, Path("out") / "video.mp4")
    lines = seen["list"].strip().splitlines()
    assert len(lines) == 2
    for line, clip in zip(lines, clips):
        path = line[len("file '"):-1].replace("'\\''", "'")
        assert Path(path).is_absolute()
        assert "\\" not in path
        assert path == clip.resolve().as_posix()
    assert "'\\''" in lines[0]  # single quote escaped per ffmpeg concat syntax


def test_concat_failure_includes_ffmpeg_stderr(tmp_path, monkeypatch):
    import subprocess

    def fake_run(args, **kwargs):
        raise subprocess.CalledProcessError(1, args, output=b"", stderr=b"No such file: x.mp4")

    monkeypatch.setattr("animatica.backends.scheduler.subprocess.run", fake_run)
    with pytest.raises(RuntimeError) as exc:
        concat_videos([tmp_path / "a.mp4"], tmp_path / "o.mp4")
    assert "No such file: x.mp4" in str(exc.value)


def test_parallel_accepts_unpicklable_closure(tmp_path):
    """A closure over local state must render fine under threads (no pickle needed)."""
    marker = object()

    def render_one(i: int) -> Path:
        assert marker is not None  # closes over local state
        return tmp_path / f"{i}.mp4"

    assert render_scenes_parallel(render_one, 3, jobs=2) == [tmp_path / f"{i}.mp4" for i in range(3)]


# ---------------------------------------------------------------------------
# pick_workers: pure rule, injected cores and memory -- no machine probing
# ---------------------------------------------------------------------------


def _env(monkeypatch, names):
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_pick_workers_two_cores_eight_gb_is_four(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    workers, limit = pick_workers("test", cpus=2, mem_gb=8.0)
    assert workers == 4
    assert limit == "cpu"


def test_pick_workers_four_cores_sixteen_gb_is_four(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    workers, limit = pick_workers("test", cpus=4, mem_gb=16.0)
    assert workers == 4
    assert limit == "cpu"


def test_pick_workers_eight_cores_sixteen_gb_is_eight(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    workers, limit = pick_workers("test", cpus=8, mem_gb=16.0)
    assert workers == 8
    assert limit == "cpu"


def test_pick_workers_sixteen_cores_eight_gb_is_five(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    workers, limit = pick_workers("test", cpus=16, mem_gb=8.0)
    assert workers == 5
    assert limit == "mem"


def test_pick_workers_thirtytwo_cores_sixtyfour_gb_is_twelve_cap(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    workers, limit = pick_workers("test", cpus=32, mem_gb=64.0)
    assert workers == 12
    assert limit == "cap"


def test_pick_workers_two_cores_two_gb_is_two_memory_forbids_four(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    workers, limit = pick_workers("test", cpus=2, mem_gb=2.0)
    assert workers == 2
    assert limit == "mem"


def test_pick_workers_uses_affinity_when_it_is_smaller_than_cpu_count(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    import animatica.backends.scheduler as sched

    orig_count = sched.os.cpu_count
    orig_affinity = sched.affinity_cpus
    sched.os.cpu_count = lambda: 64  # type: ignore[assignment]
    sched.affinity_cpus = lambda: 2
    try:
        cpus, _mem = system_info()
    finally:
        sched.os.cpu_count = orig_count
        sched.affinity_cpus = orig_affinity
    assert cpus == 2


def test_pick_workers_cgroup_quota_two_cpus(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    import animatica.backends.scheduler as sched

    orig = sched.cgroup_cpu_quota
    sched.cgroup_cpu_quota = lambda: 2.0
    try:
        workers, limit = pick_workers("test", mem_gb=64.0)
    finally:
        sched.cgroup_cpu_quota = orig
    # quota limits usable cpus to 2; 2 cpus / 64 gb -> raised to min 4, cpu
    assert workers == 4
    assert limit == "cpu"


def test_pick_workers_parse_cgroup_quota_200000_100000_is_two():
    assert parse_cgroup_quota("200000 100000") == 2.0


def test_pick_workers_env_override_wins(monkeypatch):
    monkeypatch.setenv("ANIMATICA_TEST_JOBS", "7")
    workers, limit = pick_workers("test", cpus=2, mem_gb=2.0)
    assert workers == 7
    assert limit == "env"


def test_pick_workers_garbage_env_is_ignored_with_warning(monkeypatch, capsys):
    monkeypatch.setenv("ANIMATICA_TEST_JOBS", "many")
    workers, limit = pick_workers("test", cpus=32, mem_gb=64.0)
    assert workers == 12
    assert limit == "cap"
    warning = capsys.readouterr().err
    assert "not a whole number" in warning


def test_pick_workers_mem_unknown_cpu_cap_rules_only(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    workers, limit = pick_workers("test", cpus=8, mem_gb=None)
    assert workers == 8
    assert limit == "cpu"

    workers, limit = pick_workers("test", cpus=32, mem_gb=None)
    assert workers == 12
    assert limit == "cap"


def test_pick_workers_render_keeps_its_budget(monkeypatch):
    _env(monkeypatch, ("ANIMATICA_TEST_JOBS", "ANIMATICA_RENDER_JOBS"))
    import animatica.backends.scheduler as sched

    orig_free = sched.available_memory_mb
    sched.available_memory_mb = lambda: 999999  # plenty of free memory
    try:
        workers, limit = pick_workers("render", cpus=64, mem_gb=64.0)
    finally:
        sched.available_memory_mb = orig_free
    # plenty of cores and memory, but the render pool is capped at four
    assert workers == 4
    assert limit == "cap"


def test_system_info_cpus_and_memory(monkeypatch):
    import animatica.backends.scheduler as sched

    orig_affinity = sched.affinity_cpus
    orig_quota = sched.cgroup_cpu_quota
    orig_mem = sched.total_memory_gb
    sched.affinity_cpus = lambda: 3
    sched.cgroup_cpu_quota = lambda: None
    sched.total_memory_gb = lambda: 16.0
    try:
        cpus, mem = system_info()
    finally:
        sched.affinity_cpus = orig_affinity
        sched.cgroup_cpu_quota = orig_quota
        sched.total_memory_gb = orig_mem
    assert cpus == 3
    assert mem == 16.0

