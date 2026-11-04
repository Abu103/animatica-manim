"""Persistent storyboard cache keyed by prompt + provider + schema version."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from animatica.storyboard.models import Storyboard


class StoryboardCache:
    def __init__(self, dir: Path):
        self.dir = Path(dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    def key(self, prompt: str, provider: str, schema_version: str) -> str:
        return hashlib.sha256(
            f"{prompt}|{provider}|{schema_version}".encode()
        ).hexdigest()

    def get(self, key: str) -> Storyboard | None:
        path = self.dir / f"{key}.json"
        if not path.exists():
            return None
        return Storyboard.model_validate(json.loads(path.read_text(encoding="utf-8")))

    def put(self, key: str, sb: Storyboard) -> None:
        path = self.dir / f"{key}.json"
        path.write_text(sb.model_dump_json(indent=2) + "\n", encoding="utf-8")

