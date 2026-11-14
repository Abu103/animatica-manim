"""Animatica: plain-language prompts to Manim explainer videos."""

__version__ = "0.2.0"

# Activate a bootstrap-installed cairo/pango bundle (no-op and silent when absent)
# so neither the CLI nor the TUI needs LD_LIBRARY_PATH set by hand.
from . import _nativelibs as _nativelibs

_nativelibs.ensure()
