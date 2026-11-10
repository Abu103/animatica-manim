"""Scene-parallel rendering and ffmpeg concat demuxer."""
from __future__ import annotations

import os
import subprocess
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


def render_workers() -> int:
    """How many storyboards to render at the same time.

    A render wants a core and wants memory, so the ceiling is four (what a
    four-core laptop can feed) and the free memory has to pay for every one of
    them. ``ANIMATICA_RENDER_JOBS`` overrides both.
    """
    override = os.environ.get("ANIMATICA_RENDER_JOBS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            pass

    cpus = os.cpu_count() or 1
    workers = max(1, min(_MAX_RENDER_WORKERS, cpus))

    free_mb = available_memory_mb()
    if free_mb is not None:
        workers = min(workers, max(1, free_mb // _RENDER_MEMORY_MB))
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

