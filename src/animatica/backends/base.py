"""Backend protocol, options, and result dataclasses."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar, Literal, Protocol, runtime_checkable

from animatica.progress import BackendProgressFn
from animatica.storyboard.models import Storyboard


@dataclass(frozen=True)
class RenderOptions:
    quality: Literal["preview", "standard", "high"] = "standard"
    jobs: int | None = None
    captions: bool = True  # burn each beat's caption into the video
    vertical: bool = False  # 9:16 aspect ratio for mobile/social
    beat_floors: list[list[float]] | None = None
    """Per-scene, per-beat minimum seconds (``--narrate``): a beat shorter than its
    narration holds its resting frame. ``None`` leaves every duration as it was."""
    progress: BackendProgressFn | None = None
    """Optional ``(label, done, total)`` reporter. Backends should call it for
    each unit they can actually observe, and stay silent about what they cannot.
    """


@dataclass(frozen=True)
class RenderResult:
    video: Path
    durations: list[float]
    warnings: list[str]
    stage_times: dict[str, float]


@runtime_checkable
class RenderBackend(Protocol):
    name: str
    supported_capabilities: ClassVar[list[str]]

    def capabilities(self) -> list[str]:
        """Return the capabilities this backend actually supports at runtime.

        The default implementation returns ``supported_capabilities``. Backends
        whose capabilities depend on runtime conditions (e.g. whether a system
        binary such as ``latex`` is installed) should override this method to
        probe availability dynamically.
        """
        return list(getattr(self, "supported_capabilities", []))

    def render(self, sb: Storyboard, out_dir: Path, opts: RenderOptions) -> RenderResult:  # noqa: D401
        """Render `sb` into `out_dir` using quality `opts`, return result."""

