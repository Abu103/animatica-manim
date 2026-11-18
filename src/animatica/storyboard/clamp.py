"""Local length fixes for captions and narration (O2).

A provider that writes one character too many must not burn a schema
retry: cut the text at the last sentence boundary under MAX_TEXT (or at
the last space, or exactly at the cap) and record a note for the report.
Hand-written storyboards loaded with ``--from`` get the same treatment in
memory; the file on disk is never rewritten.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from animatica.storyboard.models import MAX_TEXT, Storyboard, migrate

_SENTENCE_END = re.compile(r"[.!?](?=\s|$)")


def _shorten(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    window = text[:cap]
    ends = [m.end() for m in _SENTENCE_END.finditer(window)]
    if ends:
        return window[:ends[-1]].rstrip()
    space = window.rfind(" ")
    return (window[:space] if space > 0 else window).rstrip()


def clamp_lengths(data: Any, *, scene_offset: int = 0) -> tuple[Any, list[str]]:
    """Clamp caption/narration in a raw storyboard dict; return it and notes.

    Mutates only the dict it is given. ``scene_offset`` fixes the note's
    scene number for two-stage fills, whose single-scene reply will land at
    a later index in the final storyboard. Notes are written for the report,
    e.g. ``scene 6 beat 0 narration: shortened from 412 to 296 chars``.
    """
    if not isinstance(data, dict):
        return data, []
    notes: list[str] = []
    for si, scene in enumerate(data.get("scenes") or []):
        if not isinstance(scene, dict):
            continue
        for bi, beat in enumerate(scene.get("beats") or []):
            if not isinstance(beat, dict):
                continue
            for field in ("caption", "narration"):
                value = beat.get(field)
                if not isinstance(value, str) or len(value) <= MAX_TEXT:
                    continue
                new = _shorten(value, MAX_TEXT)
                beat[field] = new
                notes.append(
                    f"scene {si + scene_offset} beat {bi} {field}: shortened from "
                    f"{len(value)} to {len(new)} chars"
                )
    return data, notes


def load_storyboard_clamped(path: str | Path) -> tuple[Storyboard, list[str]]:
    """Load a storyboard, clamping over-long text instead of rejecting it."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    data, notes = clamp_lengths(data)
    return Storyboard.model_validate(migrate(data)), notes


__all__ = ["clamp_lengths", "load_storyboard_clamped"]
