"""Storyboard schema (version 1). The JSON form is the stable contract for all backends."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_SCENES = 12
MAX_BEATS = 8
MAX_TEXT = 300
SUPPORTED_VERSIONS = ("1",)


class Theme(BaseModel):
    model_config = ConfigDict(extra="forbid")
    palette: str = Field("dark-blue", max_length=MAX_TEXT)
    font: str = Field("default", max_length=MAX_TEXT)


class Beat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    component: str = Field(max_length=MAX_TEXT)
    params: dict[str, Any] = Field(default_factory=dict)
    caption: str = Field("", max_length=MAX_TEXT)


class Scene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    beats: list[Beat] = Field(min_length=1, max_length=MAX_BEATS)


class Storyboard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: Literal["1"] = "1"
    title: str = Field(max_length=MAX_TEXT)
    theme: Theme = Field(default_factory=Theme)
    scenes: list[Scene] = Field(min_length=1, max_length=MAX_SCENES)


def migrate(data: dict) -> dict:
    """Bring older storyboard dicts up to the current version. Only place versions are handled."""
    version = str(data.get("version", "1"))
    if version not in SUPPORTED_VERSIONS:
        raise ValueError(
            f"Unsupported storyboard version {version!r}; supported versions: {', '.join(SUPPORTED_VERSIONS)}"
        )
    return data


def load_storyboard(path: Path) -> Storyboard:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return Storyboard.model_validate(migrate(data))


def dump_storyboard(sb: Storyboard, path: Path) -> None:
    Path(path).write_text(sb.model_dump_json(indent=2) + "\n", encoding="utf-8")

