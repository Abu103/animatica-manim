#!/usr/bin/env python3
"""Animatica performance benchmark.

Renders fixed storyboards multiple times and records wall time, peak memory,
and per-stage timings.  Results are written to JSON (machine-readable) and a
human-readable summary.

Usage:
    .venv/bin/python scripts/benchmark.py [--runs N] [--output DIR]

Designed for 2 GB WSL environments: uses bounded sequential runs, preview
quality by default, and no AI model calls (offline storyboards only).
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import resource
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

# Ensure the animatica package is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from animatica.pipeline import make_video  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

STORYBOARD_DIR = Path(__file__).resolve().parent / "benchmark_storyboards"

STORYBOARDS = {
    "text_scene": STORYBOARD_DIR / "text_scene.json",
    "math_scene": STORYBOARD_DIR / "math_scene.json",
    "multi_scene": STORYBOARD_DIR / "multi_scene.json",
}

DEFAULT_RUNS = 3
DEFAULT_QUALITY = "preview"

# ---------------------------------------------------------------------------
# System info
# ---------------------------------------------------------------------------


def collect_system_info() -> dict[str, Any]:
    """Collect OS, CPU, memory, Python, and Manim version info."""
    info: dict[str, Any] = {
        "os": platform.platform(),
        "processor": platform.processor(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "cpu_count": os.cpu_count(),
    }

    # Memory
    try:
        with open("/proc/meminfo") as f:
            meminfo = {}
            for line in f:
                if ":" in line:
                    key, val = line.split(":", 1)
                    meminfo[key.strip()] = val.strip()
        info["mem_total_kb"] = int(meminfo.get("MemTotal", "0").split()[0])
        info["mem_available_kb"] = int(meminfo.get("MemAvailable", "0").split()[0])
    except Exception:
        pass

    # Manim version
    try:
        import manim
        info["manim"] = manim.__version__
    except Exception:
        info["manim"] = "unknown"

    return info


# ---------------------------------------------------------------------------
# Peak memory tracking
# ---------------------------------------------------------------------------


def peak_memory_kb() -> int:
    """Return peak RSS in KB for the current process (ru_maxrss)."""
    # ru_maxrss is in KB on Linux, bytes on macOS
    ru = resource.getrusage(resource.RUSAGE_SELF)
    val = ru.ru_maxrss
    if platform.system() == "Darwin":
        val = val // 1024  # bytes -> KB
    return val


# ---------------------------------------------------------------------------
# Benchmark runner
# ---------------------------------------------------------------------------


def render_once(sb_path: Path, out_dir: Path, quality: str) -> dict[str, Any]:
    """Render a storyboard once and return timing/memory results.

    Returns a dict with wall_time_sec, peak_memory_kb, stage_times, and
    any warnings/errors.
    """
    out_dir.mkdir(parents=True, exist_ok=True)

    start_mem = peak_memory_kb()
    start_time = time.perf_counter()

    error: str | None = None
    stage_times: dict[str, float] = {}
    warnings_list: list[str] = []
    video_path: Path | None = None

    try:
        result = make_video(
            storyboard_path=sb_path,
            out_dir=out_dir,
            preview=(quality == "preview"),
            quality=quality,
            captions=True,
            frame_lint=False,
        )
        video_path = result.video
        warnings_list = list(result.warnings)
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"

    end_time = time.perf_counter()
    end_mem = peak_memory_kb()

    return {
        "wall_time_sec": end_time - start_time,
        "peak_memory_kb": max(start_mem, end_mem),
        "memory_delta_kb": max(0, end_mem - start_mem),
        "stage_times": stage_times,
        "warnings": warnings_list,
        "error": error,
        "video_path": str(video_path) if video_path else None,
        "video_exists": video_path is not None and video_path.is_file(),
        "video_size_bytes": video_path.stat().st_size if video_path and video_path.is_file() else 0,
    }


def benchmark_storyboard(
    name: str,
    sb_path: Path,
    runs: int,
    quality: str,
    output_root: Path,
) -> dict[str, Any]:
    """Run `runs` sequential renders of a storyboard and aggregate results."""
    run_results: list[dict[str, Any]] = []

    for i in range(runs):
        run_out = output_root / name / f"run_{i:02d}"
        result = render_once(sb_path, run_out, quality)
        result["run"] = i
        run_results.append(result)

    # Aggregate
    successful = [r for r in run_results if r["error"] is None and r["video_exists"]]
    wall_times = [r["wall_time_sec"] for r in successful]
    mem_peaks = [r["peak_memory_kb"] for r in successful]

    summary: dict[str, Any] = {
        "storyboard": name,
        "storyboard_path": str(sb_path),
        "runs": runs,
        "successful": len(successful),
        "failed": len(run_results) - len(successful),
        "quality": quality,
    }

    if wall_times:
        summary["wall_time_sec"] = {
            "min": min(wall_times),
            "max": max(wall_times),
            "mean": sum(wall_times) / len(wall_times),
            "values": wall_times,
        }
    if mem_peaks:
        summary["peak_memory_kb"] = {
            "min": min(mem_peaks),
            "max": max(mem_peaks),
            "mean": sum(mem_peaks) / len(mem_peaks),
            "values": mem_peaks,
        }

    summary["runs_detail"] = run_results
    return summary


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def write_json_report(results: dict[str, Any], path: Path) -> None:
    """Write machine-readable JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


def write_human_summary(results: dict[str, Any], path: Path) -> None:
    """Write a human-readable summary."""
    lines: list[str] = []
    lines.append("=" * 72)
    lines.append("ANIMATICA PERFORMANCE BENCHMARK")
    lines.append("=" * 72)
    lines.append("")

    sys_info = results["system_info"]
    lines.append("System:")
    lines.append(f"  OS:           {sys_info.get('os', 'unknown')}")
    lines.append(f"  CPU:          {sys_info.get('processor', 'unknown')} ({sys_info.get('cpu_count', '?')} cores)")
    lines.append(f"  Memory:       {sys_info.get('mem_total_kb', 0) // 1024} MB total")
    lines.append(f"  Python:       {sys_info.get('python', 'unknown')}")
    lines.append(f"  Manim:        {sys_info.get('manim', 'unknown')}")
    lines.append("")

    lines.append("Results:")
    lines.append("-" * 72)

    for name, sb_result in results["benchmarks"].items():
        lines.append("")
        lines.append(f"  {name}:")
        lines.append(f"    Runs:           {sb_result['runs']}")
        lines.append(f"    Successful:     {sb_result['successful']}")
        lines.append(f"    Failed:         {sb_result['failed']}")
        if "wall_time_sec" in sb_result:
            wt = sb_result["wall_time_sec"]
            lines.append(f"    Wall time (s):  min={wt['min']:.2f}  max={wt['max']:.2f}  mean={wt['mean']:.2f}")
        if "peak_memory_kb" in sb_result:
            mp = sb_result["peak_memory_kb"]
            lines.append(f"    Peak memory:    min={mp['min']} KB  max={mp['max']} KB  mean={mp['mean']:.0f} KB")

    lines.append("")
    lines.append("=" * 72)

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Animatica performance benchmark")
    parser.add_argument(
        "--runs",
        type=int,
        default=DEFAULT_RUNS,
        help=f"Number of sequential runs per storyboard (default: {DEFAULT_RUNS})",
    )
    parser.add_argument(
        "--quality",
        choices=["preview", "standard", "high"],
        default=DEFAULT_QUALITY,
        help=f"Render quality (default: {DEFAULT_QUALITY})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("benchmark_results"),
        help="Output directory for results (default: benchmark_results)",
    )
    args = parser.parse_args()

    print(f"Animatica Performance Benchmark")
    print(f"  Quality: {args.quality}")
    print(f"  Runs per storyboard: {args.runs}")
    print(f"  Output directory: {args.output}")
    print()

    sys_info = collect_system_info()
    benchmarks: dict[str, Any] = {}

    for name, sb_path in STORYBOARDS.items():
        if not sb_path.is_file():
            print(f"  WARNING: storyboard not found: {sb_path}, skipping")
            continue
        print(f"  Benchmarking: {name} ...")
        benchmarks[name] = benchmark_storyboard(name, sb_path, args.runs, args.quality, args.output)

    results = {
        "system_info": sys_info,
        "benchmarks": benchmarks,
    }

    output_root = args.output
    write_json_report(results, output_root / "results.json")
    write_human_summary(results, output_root / "summary.txt")

    print()
    print(f"Results written to: {output_root / 'results.json'}")
    print(f"Summary written to: {output_root / 'summary.txt'}")


if __name__ == "__main__":
    main()
