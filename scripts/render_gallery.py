#!/usr/bin/env python3
"""Render every storyboard in ``docs/gallery`` for real and report how each one went (T18).

For each ``docs/gallery/*.json`` this runs

    animatica make --from <file> -o out/gallery/<name> --quality preview

then reads the ``report.json`` the pipeline wrote and records: ok or FAIL, the warnings
(verbatim), and the wall-clock seconds. It prints a table, writes it to
``out/gallery/RESULTS.md``, and with ``--write-doc`` also pastes it, with the date, commit and
machine, into the results block of ``docs/GALLERY.md``.

A render counts as FAIL when ``animatica make`` exits non-zero, writes no ``report.json``, or
reports a component that fell back to a text card. Warnings alone do not fail a render; they are
listed so nobody has to guess what a clean run looks like.

Exit code is 0 only when every storyboard rendered. MP4s stay in ``out/`` (git-ignored); attach
them to a release by hand.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import platform
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

REPO_ROOT = Path(__file__).resolve().parent.parent
GALLERY_DIR = REPO_ROOT / "docs" / "gallery"
OUT_DIR = REPO_ROOT / "out" / "gallery"
DOC_PATH = REPO_ROOT / "docs" / "GALLERY.md"

START_MARK = "<!-- gallery-results:start -->"
END_MARK = "<!-- gallery-results:end -->"


@dataclass
class GalleryResult:
    name: str
    ok: bool
    seconds: float
    warnings: list[str] = field(default_factory=list)
    problem: str = ""  # why it failed, when it did


#: (storyboard path, output dir) -> (exit code, combined stdout+stderr)
Runner = Callable[[Path, Path], "tuple[int, str]"]


def storyboard_paths(gallery: Path = GALLERY_DIR) -> list[Path]:
    return sorted(gallery.glob("*.json"))


def run_make(storyboard: Path, out_dir: Path) -> tuple[int, str]:
    cmd = [
        sys.executable, "-m", "animatica", "make",
        "--from", str(storyboard),
        "-o", str(out_dir),
        "--quality", "preview",
        "--no-progress",
    ]
    proc = subprocess.run(
        cmd, cwd=REPO_ROOT, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def _read_report(out_dir: Path) -> dict | None:
    path = out_dir / "report.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def render_one(storyboard: Path, out_root: Path, runner: Runner = run_make) -> GalleryResult:
    name = storyboard.stem
    out_dir = out_root / name
    started = time.perf_counter()
    code, output = runner(storyboard, out_dir)
    seconds = time.perf_counter() - started

    if code != 0:
        tail = " ".join(output.strip().splitlines()[-1:]) if output.strip() else ""
        return GalleryResult(name, False, seconds, problem=f"animatica make exited {code}. {tail}".strip())
    report = _read_report(out_dir)
    if report is None:
        return GalleryResult(name, False, seconds, problem="no readable report.json was written")
    warnings = [str(w) for w in report.get("warnings", [])]
    fallbacks = [str(f) for f in report.get("fallbacks", [])]
    if fallbacks:
        return GalleryResult(
            name, False, seconds, warnings, problem="a component fell back to a text card: " + "; ".join(fallbacks)
        )
    return GalleryResult(name, True, seconds, warnings)


def format_results(results: list[GalleryResult]) -> str:
    """The results table, then every warning and failure reason verbatim."""
    lines = ["| storyboard | result | warnings | seconds |", "|---|---|---|---|"]
    for r in results:
        lines.append(f"| `{r.name}` | {'ok' if r.ok else 'FAIL'} | {len(r.warnings)} | {r.seconds:.1f} |")
    failed = sum(1 for r in results if not r.ok)
    lines.append("")
    lines.append(f"{len(results) - failed}/{len(results)} rendered, {failed} failed.")
    detail = [r for r in results if r.warnings or r.problem]
    if detail:
        lines.append("")
        lines.append("Warnings and failures, verbatim:")
        for r in detail:
            lines.append("")
            lines.append(f"`{r.name}`:")
            lines.append("")
            lines.append("```")
            if r.problem:
                lines.append(f"FAIL: {r.problem}")
            lines.extend(r.warnings)
            lines.append("```")
    return "\n".join(lines)


def _git_sha() -> str:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        )
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def run_header(now: _dt.datetime | None = None) -> str:
    now = now or _dt.datetime.now()
    try:
        import manim  # noqa: PLC0415

        manim_version = manim.__version__
    except Exception:  # pragma: no cover - environment dependent
        manim_version = "not importable"
    return "\n".join([
        "| | |",
        "|---|---|",
        f"| Date | {now:%Y-%m-%d %H:%M} (local time, the machine below) |",
        f"| Commit | `{_git_sha()}` |",
        f"| Machine | {platform.system()} {platform.release()}, Python {platform.python_version()}, Manim {manim_version} |",
        "| Command | `animatica make --from <file> -o out/gallery/<name> --quality preview` |",
    ])


def update_doc(doc_text: str, block: str) -> str:
    """Replace what sits between the two result markers; fail loudly if they are missing."""
    start = doc_text.find(START_MARK)
    end = doc_text.find(END_MARK)
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"the doc needs {START_MARK} and {END_MARK} around its results")
    return doc_text[: start + len(START_MARK)] + "\n\n" + block.strip("\n") + "\n\n" + doc_text[end:]


def main(argv: list[str] | None = None, runner: Runner = run_make) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--gallery", type=Path, default=GALLERY_DIR, help="folder of storyboards (default docs/gallery)")
    parser.add_argument("--out", type=Path, default=OUT_DIR, help="where renders go (default out/gallery)")
    parser.add_argument("--write-doc", action="store_true", help="paste the results into docs/GALLERY.md")
    parser.add_argument("--doc", type=Path, default=DOC_PATH, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    storyboards = storyboard_paths(args.gallery)
    if not storyboards:
        print(f"FAIL: no storyboards found in {args.gallery}")
        return 1

    results: list[GalleryResult] = []
    for sb in storyboards:
        print(f"rendering {sb.stem} ...", flush=True)
        result = render_one(sb, args.out, runner)
        print(f"  {'ok' if result.ok else 'FAIL'}  {result.seconds:.1f}s  {len(result.warnings)} warning(s)", flush=True)
        results.append(result)

    table = format_results(results)
    block = run_header() + "\n\n" + table
    print("\n" + block)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "RESULTS.md").write_text(block + "\n", encoding="utf-8")
    if args.write_doc:
        args.doc.write_text(update_doc(args.doc.read_text(encoding="utf-8"), block), encoding="utf-8")
        print(f"results written into {args.doc}")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
