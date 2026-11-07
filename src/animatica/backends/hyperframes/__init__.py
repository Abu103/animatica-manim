"""HyperFrames render backend (experimental).

The package is split so that everything except :mod:`backend` is pure Python
with no Node, browser or ffmpeg dependency:

* :mod:`plan` turns a validated :class:`~animatica.storyboard.models.Storyboard`
  into absolute pixel geometry and a timeline (:class:`~plan.Plan`).
* :mod:`compose` renders a plan into a deterministic ``index.html``.
* :mod:`backend` shells out to the pinned HyperFrames CLI.
"""
from __future__ import annotations

from animatica.backends.hyperframes.backend import HYPERFRAMES_VERSION, HyperFramesBackend
from animatica.backends.hyperframes.compose import content_hash, render_html, write_composition
from animatica.backends.hyperframes.plan import (
    BeatPlan,
    Line,
    Plan,
    PlanError,
    Rect,
    SUPPORTED_COMPONENTS,
    plan_storyboard,
    problems,
)

__all__ = [
    "HYPERFRAMES_VERSION",
    "HyperFramesBackend",
    "BeatPlan",
    "Line",
    "Plan",
    "PlanError",
    "Rect",
    "SUPPORTED_COMPONENTS",
    "plan_storyboard",
    "problems",
    "content_hash",
    "render_html",
    "write_composition",
]
