#!/usr/bin/env python3
"""Render a storyboard through the real HyperFrames CLI and check the pixels.

This is the visual acceptance step the backend never had: Node + Chrome + the
pinned `hyperframes` CLI, a storyboard using only the components the composition
understands, and assertions on the decoded frames rather than on the exit code.

Run it where Chrome exists (a dev laptop, or the `hyperframes` CI job):

    npm install -g hyperframes@0.9.19
    python scripts/ci_hyperframes.py

Exit code is 0 only when a video with real, moving content came out.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

STORYBOARD = {
    "version": "1",
    "title": "HyperFrames acceptance",
    "scenes": [
        {
            "beats": [
                {
                    "component": "title_card",
                    "params": {"title": "Rendered by a browser"},
                    "caption": "The HyperFrames backend composes HTML and CSS.",
                }
            ]
        },
        {
            "beats": [
                {
                    "component": "equation",
                    "params": {"latex": ["a^2 + b^2 = c^2"], "mode": "reveal"},
                    "caption": "Math is laid out up front, in Python.",
                }
            ]
        },
        {
            "beats": [
                {
                    "component": "steps_list",
                    "params": {"items": ["Plan in Python", "Compose HTML", "Render in Chrome"]},
                    "caption": "Layout and timing never live in the renderer.",
                }
            ]
        },
    ],
}


def note(title: str, message: str) -> None:
    print(f"--- {title}: {message}")
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::notice title={title}::{message}")


def fail(message: str) -> int:
    print(f"FAILED: {message}", file=sys.stderr)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(f"::error title=hyperframes acceptance::{message}")
    return 1


def probe_environment() -> str | None:
    """Return an error message when the machine cannot run the CLI at all."""
    if not shutil.which("node"):
        return "node is not installed"
    if not (shutil.which("hyperframes") or shutil.which("npx")):
        return "the hyperframes CLI is not installed (npm install -g hyperframes)"
    chrome = (
        os.environ.get("PUPPETEER_EXECUTABLE_PATH")
        or shutil.which("google-chrome")
        or shutil.which("chromium")
        or shutil.which("chrome")
    )
    if not chrome:
        return "no Chrome/Chromium found (set PUPPETEER_EXECUTABLE_PATH)"
    os.environ.setdefault("PUPPETEER_EXECUTABLE_PATH", chrome)
    print(f"chrome: {chrome}")
    return None


def frames_report(video: Path) -> tuple[int, float, int]:
    """(frame count, average non-background fraction, distinct frame count)."""
    import av
    import numpy as np

    container = av.open(str(video))
    stream = container.streams.video[0]
    fractions: list[float] = []
    signatures: set[bytes] = set()
    for frame in container.decode(stream):
        small = frame.to_ndarray(format="rgb24")[::8, ::8]
        background = small[0, 0].astype(int)
        distance = np.abs(small.astype(int) - background).sum(axis=2)
        fractions.append(float((distance > 24).mean()))
        signatures.add(small.tobytes())
    if not fractions:
        return 0, 0.0, 0
    return len(fractions), sum(fractions) / len(fractions), len(signatures)


def main() -> int:
    trouble = probe_environment()
    if trouble:
        return fail(trouble)

    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        storyboard = work / "storyboard.json"
        storyboard.write_text(json.dumps(STORYBOARD, indent=2), encoding="utf-8")
        out = work / "out"

        cmd = [
            sys.executable,
            "-m",
            "animatica",
            "make",
            "--from",
            str(storyboard),
            "--backend",
            "hyperframes",
            "--jobs",
            "1",
            "-o",
            str(out),
        ]
        print(f"$ {' '.join(cmd)}")
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
        tail = (proc.stdout + proc.stderr).strip().splitlines()[-6:]
        for line in tail:
            print(f"  | {line}")
        if proc.returncode != 0:
            return fail(f"make exited {proc.returncode}: {tail[-1] if tail else 'no output'}")

        video = out / "video.mp4"
        if not video.is_file():
            return fail(f"no video was produced (looked for {video})")
        size = video.stat().st_size
        if size < 20_000:
            return fail(f"video is suspiciously small ({size} bytes)")

        count, non_background, distinct = frames_report(video)
        note("hyperframes render", f"{video.name} {size} bytes, {count} frames")
        note(
            "pixels",
            f"{non_background:.1%} of each frame is content, {distinct} distinct frames",
        )
        if count < 10:
            return fail(f"only {count} frames decoded")
        if non_background < 0.01:
            return fail(f"frames are essentially empty ({non_background:.2%} content)")
        if distinct < 5:
            return fail(f"only {distinct} distinct frames: the video barely moves")
        print(f"\nOK: {out}/video.mp4 {size} bytes, {count} frames, {non_background:.1%} content")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
