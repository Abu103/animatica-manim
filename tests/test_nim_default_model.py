"""NIM default model must not point at a retired model (HTTP 410 on NIM)."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

from animatica.ai.nim import NIMProvider


def test_nim_default_model_is_nemotron():
    """NIMProvider.default_model must be the currently-available NIM model."""
    assert NIMProvider.default_model == "nvidia/nemotron-3.5-super-vl-120b-a12b"


def test_providers_toml_nim_model_is_nemotron():
    """providers.toml [nim].model must match the code default."""
    toml_path = Path(__file__).resolve().parent.parent / "src" / "animatica" / "ai" / "providers.toml"
    data = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    assert data["nim"]["model"] == "nvidia/nemotron-3.5-super-vl-120b-a12b"
