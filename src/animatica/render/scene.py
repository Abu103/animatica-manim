"""Storyboard-driven Manim scene: reads storyboard path + scene index from env.

The static scene never interpolates user/LLM strings; it loads storyboard.json
at runtime and plays each beat via the component registry, degrading any failed
beat to a plain text card plus a warning.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from manim import Scene

from animatica.components._draw import make_caption, prepare, text_card, warn
from animatica.components.registry import default_registry
from animatica.components.theme import get_colors
from animatica.storyboard.models import load_storyboard


class StoryboardScene(Scene):
    """Play one scene of a storyboard, index taken from ANIMATICA_SCENE_INDEX."""

    def construct(self) -> None:
        self.warnings: list[str] = []
        sb_path = Path(os.environ["ANIMATICA_STORYBOARD"])
        idx = int(os.environ.get("ANIMATICA_SCENE_INDEX", "0"))
        sb = load_storyboard(sb_path)
        if idx < 0 or idx >= len(sb.scenes):
            raise IndexError(f"scene index {idx} out of range (0-{len(sb.scenes) - 1})")
        scene = sb.scenes[idx]
        registry = default_registry()
        colors = get_colors(sb.theme)

        captions_on = os.environ.get("ANIMATICA_CAPTIONS", "1") != "0"
        floors_file = os.environ.get("ANIMATICA_BEAT_FLOORS")  # --narrate: per-beat minimum seconds
        floors = json.loads(Path(floors_file).read_text(encoding="utf-8"))[idx] if floors_file else []
        for b_idx, beat in enumerate(scene.beats):
            comp = registry.get(beat.component)
            params = comp.Params.model_validate(beat.params)
            self.caption_mobject = None
            if captions_on and beat.caption.strip():
                try:
                    prepare(self, colors)  # background + default font, before the caption is built
                    self.caption_mobject = make_caption(beat.caption.strip(), colors)
                    self.add(self.caption_mobject)
                except Exception as exc:  # captions are a nicety: never fail the beat over them
                    warn(self, f"caption skipped: {type(exc).__name__}: {exc}")
            # Narration longer than the visual: the component's Clock holds its content for the
            # difference (before its fade-out); nothing is ever sped up.
            hold = max(0.0, (floors[b_idx] if b_idx < len(floors) else 0.0) - comp.duration(params))
            self.narration_hold = hold
            try:
                comp.play(self, params, colors)
            except Exception as exc:  # degrade, never abort the video
                warn(self, f"{beat.component}: {type(exc).__name__}: {exc}")
                text_card(self, comp.fallback_text(params), colors, comp.duration(params))
                if hold > 1e-3:
                    self.wait(hold)
            finally:
                self.narration_hold = 0.0

        # Persist warnings so the out-of-process backend can collect them.
        (sb_path.parent / f"warnings_{idx}.json").write_text(
            json.dumps(self.warnings), encoding="utf-8"
        )

