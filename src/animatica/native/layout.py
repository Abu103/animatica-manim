"""Layered left-to-right graph layout for the diagram component.

Pure-Python implementation with the same native-or-fallback rule as
`sample_function`: `animatica_native.layout_graph` is used when the
optional wheel is installed, otherwise this module runs.
"""
from __future__ import annotations

from collections.abc import Callable

try:  # optional Rust implementation; missing wheel is never an error
    from animatica_native import layout_graph  # type: ignore[import-not-found]
except ImportError:  # pragma: no cover - fallback path
    from animatica.native.layout_fallback import layout_graph  # type: ignore[no-redef]

NATIVE = layout_graph.__module__ != "animatica.native.layout_fallback"

__all__ = ["layout_graph", "NATIVE"]

