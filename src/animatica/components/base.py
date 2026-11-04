"""Component interface. The LLM picks components and fills params; components own layout and timing."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

from pydantic import BaseModel

if TYPE_CHECKING:  # keep Manim out of import time for non-render code paths
    from animatica.components.theme import ThemeColors

API_VERSION = 1


class Component(ABC):
    name: ClassVar[str]
    api_version: ClassVar[int] = API_VERSION
    Params: ClassVar[type[BaseModel]]

    @abstractmethod
    def duration(self, p: BaseModel) -> float:
        """Seconds this beat takes. Pure function of params (used for captions and tests)."""

    @abstractmethod
    def play(self, scene: Any, p: BaseModel, colors: "ThemeColors") -> None:
        """Draw and animate on a manim.Scene."""

    @abstractmethod
    def fallback_text(self, p: BaseModel) -> str:
        """Plain text shown in a text card if `play` fails."""

