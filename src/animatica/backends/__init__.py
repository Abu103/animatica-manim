"""Backend registry: ManimBackend plus the `animatica.backends` entry-point group."""
from __future__ import annotations

from animatica.backends.base import RenderBackend, RenderOptions, RenderResult
from animatica.backends.manim_backend import ManimBackend
from animatica.plugins import load_entry_points


def default_backends() -> dict[str, RenderBackend]:
    backends: dict[str, RenderBackend] = {"manim": ManimBackend()}
    for name, cls in load_entry_points("animatica.backends").items():
        backends[name] = cls()
    return backends


__all__ = ["RenderBackend", "RenderOptions", "RenderResult", "ManimBackend", "default_backends"]

