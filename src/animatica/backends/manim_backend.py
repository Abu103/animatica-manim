"""Manim render backend: invokes manim as a subprocess per scene, concatenates."""
from __future__ import annotations

import glob
import json
import os
import shutil
import subprocess
import sys
from typing import ClassVar
from pathlib import Path

from animatica.backends.base import RenderBackend, RenderOptions, RenderResult
from animatica.backends.scheduler import concat_videos, render_scenes_parallel
from animatica.components.registry import default_registry
from animatica.components.theme import get_colors
from animatica.paths import check_tex_safe, long_path
from animatica.report import StageTimer
from animatica.storyboard.models import Storyboard, dump_storyboard

QUALITY_FLAG = {"preview": "l", "standard": "m", "high": "h"}


def _find_mp4(media_dir: Path, prefix: str) -> Path:
    matches = glob.glob(str(media_dir / "**" / f"{prefix}.mp4"), recursive=True)
    if not matches:
        raise RuntimeError(f"manim did not produce {prefix}.mp4 under {media_dir}")
    return Path(matches[0])


class ManimBackend:
    name = "manim"
    supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]

    def capabilities(self) -> list[str]:
        """Return capabilities actually available at runtime.

        ``latex`` and ``dvisvgm`` depend on system binaries; probe them
        dynamically so the capability report reflects reality, not aspiration.
        """
        caps = list(self.supported_capabilities)
        if not shutil.which("latex"):
            caps = [c for c in caps if c != "latex"]
        if not shutil.which("dvisvgm"):
            caps = [c for c in caps if c != "dvisvgm"]
        return caps

    @property
    def version(self) -> str:
        import manim

        return manim.__version__

    def render(self, sb: Storyboard, out_dir: Path, opts: RenderOptions) -> RenderResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        out_dir = long_path(out_dir)  # RUNNER~1 -> runneradmin: TeX treats "~" as a command
        check_tex_safe(out_dir)
        timer = StageTimer()
        warnings: list[str] = []
        durations: list[float] = []

        with timer.stage("write_storyboard"):
            sb_path = out_dir / "storyboard.json"
            dump_storyboard(sb, sb_path)

        registry = default_registry()
        colors = get_colors(sb.theme)

        # Durations are pure functions of the storyboard: compute them serially so
        # the list stays in scene index order regardless of render parallelism.
        durations: list[float] = []
        for scene in sb.scenes:
            scene_dur = 0.0
            for beat in scene.beats:
                comp = registry.get(beat.component)
                params = comp.Params.model_validate(beat.params)
                scene_dur += comp.duration(params)
            durations.append(scene_dur)

        def _render_scene(i: int) -> Path:
            with timer.stage(f"render_scene_{i}"):
                env = dict(os.environ)
                env.setdefault("PYTHONUTF8", "1")  # Windows defaults to cp1252; titles/captions may be Unicode
                env["ANIMATICA_STORYBOARD"] = str(sb_path)
                env["ANIMATICA_SCENE_INDEX"] = str(i)
                env["ANIMATICA_CAPTIONS"] = "1" if opts.captions else "0"
                media_dir = out_dir / "media" / f"scene_{i}"
                media_dir.mkdir(parents=True, exist_ok=True)
                import animatica.render.scene as scene_mod  # noqa: PLC0415

                cmd = [
                    sys.executable,
                    "-m",
                    "manim",
                    "render",
                    str(scene_mod.__file__),
                    "StoryboardScene",
                    "-q",
                    QUALITY_FLAG[opts.quality],
                    "--media_dir",
                    str(media_dir),
                    "--output_file",
                    f"scene_{i}",
                    "--verbosity",
                    "ERROR",
                ]
                if opts.vertical:
                    cmd += ["-r", "1080,1920"]
                try:
                    subprocess.run(cmd, env=env, check=True, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=900)
                except subprocess.CalledProcessError as exc:
                    tail = "\n".join(((exc.stderr or "") + "\n" + (exc.stdout or "")).strip().splitlines()[-25:])
                    raise RuntimeError(f"manim failed on scene {i} (exit {exc.returncode}):\n{tail}") from exc
                return _find_mp4(media_dir, f"scene_{i}")

        scene_mp4s = render_scenes_parallel(_render_scene, len(sb.scenes), jobs=opts.jobs or 1)

        # Per-scene warnings files already have unique names (warnings_{i}.json).
        for i in range(len(sb.scenes)):
            wpath = sb_path.parent / f"warnings_{i}.json"
            if wpath.exists():
                warnings.extend(json.loads(wpath.read_text(encoding="utf-8")))
                wpath.unlink()

        with timer.stage("concat"):
            video = out_dir / "video.mp4"
            if len(scene_mp4s) == 1:
                scene_mp4s[0].replace(video)
            else:
                concat_videos(scene_mp4s, video)

        return RenderResult(
            video=video,
            durations=durations,
            warnings=warnings,
            stage_times=dict(timer.stages),
        )

