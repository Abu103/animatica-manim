"""Scene-parallel rendering and ffmpeg concat demuxer."""
from __future__ import annotations

import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Callable, Sequence, TypeVar, cast

T = TypeVar("T")
R = TypeVar("R")

#: How many megabytes of free memory one render needs before another one is
#: started. A render is a python + manim + ffmpeg process tree; measured on
#: a four-core laptop it takes about 300 MB, and 450 leaves room for the
#: rest of the machine. When memory runs out the box starts swapping and
#: every render gets slower.
_RENDER_MEMORY_MB = 450

#: The most renders to run at the same time, whatever the machine says.
_MAX_RENDER_WORKERS = 4

#: How much memory one worker of the test suite is assumed to need, in GB.
#: A pytest worker is a whole python process with its own manim, so the
#: suite runs out of memory long before it runs out of cores.
_TEST_WORKER_GB = 1.5

#: The most workers the suite may use, whatever the machine says.
_MAX_TEST_WORKERS = 12

#: The fewest workers worth running: below this the wall clock is decided
#: by the slowest test, not by the number of workers.
_MIN_WORKERS = 4

#: When the memory limit forbids the minimum, two workers still beat one.
_MIN_WORKERS_MEMORY_LIMITED = 2

#: The environment variable that overrides the worker count per kind.
_ENV_VARS = {"test": "ANIMATICA_TEST_JOBS", "render": "ANIMATICA_RENDER_JOBS"}

#: Sentinel for "not given to pick_workers": ``None`` means "the platform does
#: not know" (skip the memory limit), while this sentinel means "probe the
#: machine". Tests inject both values so no real machine probing happens.
_UNSET = object()




def default_jobs(n_scenes: int) -> int:
    return max(1, min((os.cpu_count() or 1) - 1, n_scenes))


def available_memory_mb() -> int | None:
    """Free memory in megabytes, or None when the platform does not say."""
    try:
        if os.name == "nt":
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return int(status.ullAvailPhys / (1024 * 1024))
            return None
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
    except Exception:  # pragma: no cover - the platform does not tell
        return None
    return None


def total_memory_gb() -> float | None:
    """Total RAM in gigabytes, or None when the platform does not say.

    Linux reads ``/proc/meminfo``, Windows asks ``GlobalMemoryStatusEx``
    through ctypes, macOS asks ``sysctl hw.memsize``. No new dependency: all
    three are in the kernel or the standard library.
    """
    try:
        if os.name == "nt":
            import ctypes

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return status.ullTotalPhys / (1024**3)
            return None
        if sys.platform == "darwin":
            import ctypes

            size = ctypes.c_size_t(8)
            value = ctypes.c_uint64()
            libc = ctypes.CDLL("libc.dylib")
            libc.sysctlbyname(
                b"hw.memsize", ctypes.byref(value), ctypes.byref(size), None, 0
            )
            return value.value / (1024**3)
        with open("/proc/meminfo", encoding="utf-8") as handle:
            for line in handle:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) / (1024**2)
    except Exception:  # pragma: no cover - the platform does not tell
        return None
    return None


def parse_cgroup_quota(text: str) -> float | None:
    """The CPUs a cgroup v2 ``cpu.max`` line allows, or None for no limit.

    ``"200000 100000"`` is two CPUs (quota over period); ``"max 100000"``
    means the group may use every CPU.
    """
    fields = text.split()
    if len(fields) < 2 or fields[0] == "max":
        return None
    try:
        quota = int(fields[0])
        period = int(fields[1])
    except ValueError:
        return None
    if quota <= 0 or period <= 0:
        return None
    return quota / period


def cgroup_cpu_quota() -> float | None:
    """The CPU quota the cgroup gives this process, in CPUs.

    Cgroup v2 writes ``max 100000`` or ``200000 100000`` into
    ``/sys/fs/cgroup/cpu.max``; cgroup v1 splits the same numbers over
    ``cpu.cfs_quota_us`` and ``cpu.cfs_period_us``. A container with two CPUs
    must not believe it has the host's cores.
    """
    try:
        path = Path("/sys/fs/cgroup/cpu.max")
        if path.is_file():
            return parse_cgroup_quota(path.read_text(encoding="utf-8"))
        quota_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_quota_us")
        period_path = Path("/sys/fs/cgroup/cpu/cpu.cfs_period_us")
        if quota_path.is_file() and period_path.is_file():
            return parse_cgroup_quota(
                f"{quota_path.read_text(encoding='utf-8').strip()} "
                f"{period_path.read_text(encoding='utf-8').strip()}"
            )
    except Exception:  # pragma: no cover - the platform does not tell
        return None
    return None


def affinity_cpus() -> int | None:
    """How many CPUs this process may run on, or None when unknown."""
    getter = getattr(os, "sched_getaffinity", None)
    if getter is None:
        return None
    try:
        count = len(getter(0))
    except OSError:  # pragma: no cover - the platform does not tell
        return None
    return count or None


def usable_cpus(
    affinity: int | None = None,
    quota: float | None = None,
    cpu_count: int | None = None,
) -> int:
    """The CPUs this process may really use.

    It is the smallest of what the machine has, what the affinity mask allows
    and what the cgroup quota allows: a container limited to two CPUs must
    not plan for the host's cores.
    """
    cpus = cpu_count if cpu_count else (os.cpu_count() or 1)
    if affinity:
        cpus = min(cpus, affinity)
    if quota:
        cpus = min(cpus, max(1, int(quota)))
    return max(1, cpus)


def system_info() -> tuple[int, float | None]:
    """What the machine can take: (usable CPUs, total RAM in GB).

    The memory is the total RAM, or None when the platform does not say.
    """
    cpus = usable_cpus(affinity=affinity_cpus(), quota=cgroup_cpu_quota())
    return cpus, total_memory_gb()


def _env_override(kind: str) -> int | None:
    """The worker count the environment asks for, or None.

    An invalid value is ignored with a warning: a typo must not silently run
    the suite with the wrong number of workers.
    """
    name = _ENV_VARS.get(kind)
    if not name:
        return None
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return None
    try:
        value = int(raw.strip())
    except ValueError:
        print(f"warning: ignoring {name}={raw!r}: not a whole number", file=sys.stderr)
        return None
    if value < 1:
        print(f"warning: ignoring {name}={raw!r}: must be at least 1", file=sys.stderr)
        return None
    return value


def pick_workers(
    kind: str = "test",
    cpus: int | object = _UNSET,
    mem_gb: float | object = _UNSET,
) -> tuple[int, str]:
    """How many workers to run, and what limited the answer.

    The count is the smaller of the cores and the memory: one test worker
    wants about 1.5 GB of RAM, so eight cores with eight GB of RAM feed only
    five workers. It is never below four (unless the memory forbids it) and
    never above twelve.

    ``cpus`` and ``mem_gb`` are injected so the rule can be tested without
    probing the machine; leaving them at their default asks the machine.
    ``None`` means "unknown": the memory limit is then skipped.

    Returns ``(workers, limit)`` where ``limit`` says what bound the answer:
    ``cpu``, ``mem``, ``cap`` or ``env``.
    """
    override = _env_override(kind)
    if override is not None:
        return override, "env"

    if cpus is _UNSET or mem_gb is _UNSET:
        machine_cpus, machine_mem = system_info()
        if cpus is _UNSET:
            cpus = machine_cpus
        if mem_gb is _UNSET:
            mem_gb = machine_mem

    cpus = max(1, cpus if cpus is not _UNSET and cpus is not None else 1)

    if kind == "render":
        # The render pool keeps its own budget: a render is heavier than a
        # test worker, it needs free memory (not total), and the pool has
        # always been capped at four.
        workers = cpus
        limit = "cpu"
        free_mb = available_memory_mb()
        if free_mb is not None:
            by_memory = max(1, free_mb // _RENDER_MEMORY_MB)
            if by_memory < workers:
                workers = by_memory
                limit = "mem"
        if workers > _MAX_RENDER_WORKERS:
            workers = _MAX_RENDER_WORKERS
            limit = "cap"
        return max(1, workers), limit

    memory_limit = None
    if mem_gb is not None:
        memory_limit = int(mem_gb // _TEST_WORKER_GB)

    if memory_limit is None:
        # Without memory information the cores and the cap are all we know.
        workers = min(cpus, _MAX_TEST_WORKERS)
        limit = "cap" if cpus > _MAX_TEST_WORKERS else "cpu"
        return max(1, workers), limit

    if memory_limit < _MIN_WORKERS:
        # The memory forbids the minimum; two workers still beat one.
        return max(_MIN_WORKERS_MEMORY_LIMITED, memory_limit), "mem"

    workers = min(cpus, memory_limit)
    limit = "mem" if memory_limit < cpus else "cpu"
    if workers < _MIN_WORKERS:
        workers = _MIN_WORKERS
        limit = "cpu"
    if workers > _MAX_TEST_WORKERS:
        workers = _MAX_TEST_WORKERS
        limit = "cap"
    return max(1, workers), limit


def render_workers() -> int:
    """How many storyboards to render at the same time.

    A render wants a core and wants memory, so the ceiling is four (what a
    four-core laptop can feed) and the free memory has to pay for every one of
    them. ``ANIMATICA_RENDER_JOBS`` overrides both.
    """
    workers, _ = pick_workers("render")
    return workers


def run_in_parallel(
    items: Sequence[T], work: Callable[[T], R], workers: int | None = None
) -> list[R]:
    """Run `work` over `items` at the same time; results keep the input order.

    Threads (not processes) are deliberate: every item already shells out to
    a subprocess, so a closure over local state needs no pickling.
    """
    if not items:
        return []
    if workers is None:
        workers = render_workers()
    workers = max(1, min(workers, len(items)))

    if workers == 1:
        return [work(item) for item in items]

    results: list[R | None] = [None] * len(items)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(work, item): i for i, item in enumerate(items)}
        for fut in as_completed(futures):
            index = futures[fut]
            try:
                results[index] = fut.result()
            except Exception:
                for other in futures:
                    if other is not fut:
                        other.cancel()
                raise
    # Every future was awaited, so every slot is filled.
    return cast(list[R], results)


def render_scenes_parallel(
    render_one: Callable[[int], Path], n_scenes: int, jobs: int | None = None
) -> list[Path]:
    """Render `n_scenes` scenes, returning paths in scene order.

    Runs `render_one(i)` for each scene index. With `jobs > 1` uses a thread
    pool; results are reordered back into scene index order. On the first
    failure, remaining renders are cancelled and a `RuntimeError` naming the
    failing scene index is raised.

    Threads (not processes) are deliberate: each scene already shells out to a
    manim subprocess, so a closure over local state needs no pickling and we
    avoid the `fork()` deprecation warnings that a ProcessPoolExecutor raises.
    """
    if n_scenes <= 0:
        return []
    if jobs is None:
        jobs = default_jobs(n_scenes)
    jobs = max(1, jobs)

    results: list[Path | None] = [None] * n_scenes

    if jobs == 1 or n_scenes == 1:
        for i in range(n_scenes):
            results[i] = render_one(i)
        return [r for r in results if r is not None]  # type: ignore[return-value]

    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {pool.submit(render_one, i): i for i in range(n_scenes)}
        for fut in as_completed(futures):
            idx = futures[fut]
            try:
                results[idx] = fut.result()
            except Exception as exc:
                for other in futures:
                    if other is not fut:
                        other.cancel()
                raise RuntimeError(f"scene {idx} failed: {exc}") from exc

    return [r for r in results if r is not None]  # type: ignore[return-value]


def _concat_entry(clip: Path) -> str:
    """One line of an ffmpeg concat list: absolute, forward-slash path, quotes escaped.

    The demuxer resolves relative entries against the list file's directory (not the
    cwd) and treats backslashes as escapes, so relative/Windows paths must be normalised.
    """
    posix = Path(clip).resolve().as_posix().replace("'", "'\\''")
    return f"file '{posix}'"


def concat_videos(clips: list[Path], dst: Path, ffmpeg: str | None = None) -> None:
    """Concatenate clips using explicit, system, or bundled ffmpeg, in that order."""
    if ffmpeg is None:
        from animatica.encode.probe import _default_ffmpeg

        ffmpeg = _default_ffmpeg()
    dst = Path(dst)
    list_file = dst.parent / f".concat_{dst.name}.txt"
    try:
        list_file.write_text("\n".join(_concat_entry(c) for c in clips) + "\n", encoding="utf-8")
        try:
            subprocess.run(
                [ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(dst)],
                check=True,
                capture_output=True,
            )
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or b"").decode("utf-8", "replace").strip()[-600:]
            raise RuntimeError(f"ffmpeg concat failed (exit {exc.returncode}): {detail}") from exc
    finally:
        list_file.unlink(missing_ok=True)
