"""HyperFrames render backend: plan -> compose -> ``hyperframes render`` -> MP4.

This is the only module in the package that touches Node. Everything it needs
from the storyboard is already decided by :mod:`plan` and :mod:`compose`, so the
subprocess is a single, auditable call -- and the whole thing is testable with a
fake runner, no Node on the test machine.

Environment
-----------
``ANIMATICA_HYPERFRAMES``
    Absolute path to the HyperFrames CLI (or any wrapper). Takes precedence.
    Otherwise ``hyperframes`` on ``PATH`` is used, then ``npx --no-install``.

The CLI version this backend was developed against is pinned in
:data:`HYPERFRAMES_VERSION`; keep it in step with the pilot ``package.json``.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable, ClassVar

from animatica.backends.base import RenderOptions, RenderResult
from animatica.backends.hyperframes.compose import write_composition
from animatica.backends.hyperframes.plan import Plan, plan_storyboard, problems
from animatica.report import StageTimer
from animatica.storyboard.models import Storyboard

HYPERFRAMES_VERSION = "0.9.19"

#: ``runner(cmd, cwd)`` -> None, raising on failure. Injectable so the backend
#: can be tested without Node, and so a caller can supply a sandboxed runner.
Runner = Callable[[list[str], Path], None]

CLI_ENV = "ANIMATICA_HYPERFRAMES"
_RENDER_TIMEOUT = 1800


class HyperFramesBackend:
    """Renders the storyboard components the HTML composition understands."""

    name = "hyperframes"
    supported_capabilities: ClassVar[list[str]] = ["html", "css"]

    def __init__(self, runner: Runner | None = None) -> None:
        self._runner = runner or _run_cli

    @property
    def version(self) -> str:
        return HYPERFRAMES_VERSION

    def capabilities(self) -> list[str]:
        """Static capability claim, gated on Node being usable at all.

        Deliberately does not launch Node: a capability probe must stay cheap.
        Whether the pinned CLI is actually installed is answered by ``render``,
        which fails with an actionable message if it is not.
        """
        if shutil.which("node") and (shutil.which("hyperframes") or shutil.which("npx")):
            return list(self.supported_capabilities)
        return []

    # -- rendering ---------------------------------------------------------

    def render(self, sb: Storyboard, out_dir: Path, opts: RenderOptions) -> RenderResult:
        if opts.vertical:
            raise ValueError(
                "vertical (9:16) export is not implemented for the hyperframes backend yet; "
                "use --backend manim, or add a vertical variant of the composition template."
            )

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        timer = StageTimer()
        # This renderer is one opaque CLI call: report three coarse units and
        # nothing finer, rather than inventing per-scene smoothness.
        def note(label: str, done: int) -> None:
            if opts.progress is not None:
                opts.progress(label, done, 3)

        with timer.stage("plan"):
            note("planning composition", 0)
            plan = plan_storyboard(sb, captions=opts.captions)
            layout_issues = problems(plan)
            durations = self._scene_durations(plan)

        with timer.stage("compose"):
            note("writing composition", 1)
            composition = write_composition(plan, out_dir)

        video = out_dir / "video.mp4"
        cmd = self._render_command(video)
        with timer.stage("render"):
            note("hyperframes render", 2)
            try:
                self._runner(cmd, out_dir)
            except subprocess.CalledProcessError as exc:
                tail = "\n".join(
                    ((exc.stderr or "") + "\n" + (exc.stdout or "")).strip().splitlines()[-25:]
                )
                raise RuntimeError(
                    f"hyperframes render failed (exit {exc.returncode}) on {composition}:\n{tail}"
                ) from exc

        note("hyperframes render: done", 3)

        if not video.exists():
            raise RuntimeError(
                f"hyperframes reported success but produced no {video.name} in {out_dir}; "
                f"the composition is at {composition}"
            )

        return RenderResult(
            video=video,
            durations=durations,
            warnings=[f"layout: {issue}" for issue in layout_issues],
            stage_times=dict(timer.stages),
        )

    # -- helpers -----------------------------------------------------------

    def _scene_durations(self, plan: Plan) -> list[float]:
        """Per-scene seconds, in scene order (what the caption/VTT and MCP need)."""
        totals: dict[int, float] = {}
        for beat in plan.beats:
            totals[beat.scene] = totals.get(beat.scene, 0.0) + beat.duration
        return [round(totals[scene], 3) for scene in sorted(totals)]

    def _render_command(self, video: Path) -> list[str]:
        base = self._cli_base()
        return base + ["render", "--output", str(video), "--no-browser-gpu"]

    @staticmethod
    def _cli_base() -> list[str]:
        override = os.environ.get(CLI_ENV, "").strip()
        if override:
            return [override]
        found = shutil.which("hyperframes")
        if found:
            return [found]
        npx = shutil.which("npx")
        if npx:
            return [npx, "--no-install", "hyperframes"]
        raise RuntimeError(
            "the hyperframes CLI was not found, so this video cannot be rendered.\n"
            f"Fix one of:\n"
            f"  - install it:        npm install -g hyperframes@{HYPERFRAMES_VERSION}\n"
            f"  - point at it:       set {CLI_ENV}=/path/to/hyperframes\n"
            f"  - or render elsewhere: --backend manim\n"
            f"The Python side needs no Node; only the final render does."
        )


def _run_cli(cmd: list[str], cwd: Path) -> None:
    """Run the CLI with its output captured; raise CalledProcessError on failure."""
    subprocess.run(
        cmd,
        cwd=str(cwd),
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=_RENDER_TIMEOUT,
    )


def describe() -> str:
    """One-line summary used by ``--debug`` output and docs."""
    return (
        f"hyperframes {HYPERFRAMES_VERSION}: HTML/CSS composition rendered by the "
        f"pinned CLI (python {sys.version_info.major}.{sys.version_info.minor}); "
        f"set {CLI_ENV} to override the CLI path"
    )
