"""AI package: providers, templates, repair loop, storyboard cache."""
from __future__ import annotations

from animatica.ai.base import AIProvider, StoryboardGenerationError, extract_json
from animatica.ai.repair import generate_storyboard
from animatica.ai.template import TemplateMatcher
from animatica.storyboard.cache import StoryboardCache

__all__ = [
    "AIProvider",
    "StoryboardGenerationError",
    "extract_json",
    "generate_storyboard",
    "TemplateMatcher",
    "StoryboardCache",
]

