"""Entry-point plugin loading. Groups: animatica.components/providers/backends/encoders/templates."""
from __future__ import annotations

from importlib.metadata import entry_points
from typing import Any


def load_entry_points(group: str) -> dict[str, Any]:
    """Load every entry point in `group`, returning {name: loaded object}."""
    return {ep.name: ep.load() for ep in entry_points(group=group)}

