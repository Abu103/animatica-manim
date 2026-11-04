"""Scene-parallel rendering and ffmpeg concat demuxer."""
from __future__ import annotations

import os
import subprocess
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Callable


def default_jobs(n_scenes: int) -> int:
    return max(1, min((os.cpu_count() or 1) - 1, n_scenes))


def render_scenes_parallel(
    render_one: Callable[[int], Path], n_scenes: int, jobs: int | None = None
) -> list[Path]:
    """Render `n_scenes` scenes, returning paths in scene order.

    Runs `render_one(i)` for each scene index. With `jobs > 1` uses a process
    pool; results are reordered back into scene index order. On the first
    failure, remaining renders are cancelled and a `RuntimeError` naming the
    failing scene index is raised.
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

    with ProcessPoolExecutor(max_workers=jobs) as pool:
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


def concat_videos(clips: list[Path], dst: Path, ffmpeg: str = "ffmpeg") -> None:
    """Concatenate `clips` into `dst` with the ffmpeg concat demuxer (`-c copy`)."""
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

