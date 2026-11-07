"""Backend registry: ManimBackend plus the `animatica.backends` entry-point group."""
from __future__ import annotations

from animatica.backends.base import RenderBackend, RenderOptions, RenderResult
from animatica.backends.manim_backend import ManimBackend
from animatica.plugins import load_entry_points


def default_backends() -> dict[str, RenderBackend]:
    # Imported here, not at module level: the HyperFrames package pulls in the
    # plan/compose seam, which is cheap but pointless for callers that only
    # ever use manim.
    from animatica.backends.hyperframes.backend import HyperFramesBackend

    backends: dict[str, RenderBackend] = {
        "manim": ManimBackend(),
        "hyperframes": HyperFramesBackend(),
    }
    for name, cls in load_entry_points("animatica.backends").items():
        backends[name] = cls()
    return backends


__all__ = [
    "RenderBackend",
    "RenderOptions",
    "RenderResult",
    "ManimBackend",
    "default_backends",
]

