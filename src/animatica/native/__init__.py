"""Hot numeric and layout helpers. Uses the optional `animatica_native`
wheel when installed, else pure Python fallbacks."""
from __future__ import annotations

try:  # optional Rust implementation; missing wheel is never an error
    from animatica_native import sample_function  # type: ignore[import-not-found]
except ImportError:
    from animatica.native.sampling import sample_function

try:  # optional Rust implementation; missing wheel is never an error
    from animatica_native import layout_graph  # type: ignore[import-not-found]
except ImportError:
    from animatica.native.layout_fallback import layout_graph

NATIVE_SAMPLING = sample_function.__module__ != "animatica.native.sampling"
NATIVE_LAYOUT = layout_graph.__module__ != "animatica.native.layout_fallback"

__all__ = ["sample_function", "layout_graph", "NATIVE_SAMPLING", "NATIVE_LAYOUT"]

