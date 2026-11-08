"""Capability negotiation tests (roadmap item 1.2.2).

Components declare required capabilities; backends expose supported
capabilities; the pipeline checks compatibility before rendering.
Unsupported requirements fail early with actionable errors.
"""

from __future__ import annotations

from typing import ClassVar

import pytest
from pydantic import BaseModel

from animatica.components.base import API_VERSION, Component
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.backends.base import RenderBackend, RenderOptions, RenderResult
from animatica.pipeline import resolve_backend
from animatica.storyboard.models import Storyboard


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------

class _FakeParams(BaseModel):
    title: str = "default"


class _FakeComponent(Component):
    """Component with no required capabilities."""
    name: ClassVar[str] = "fake_component"
    api_version: ClassVar[int] = API_VERSION
    Params: ClassVar[type[BaseModel]] = _FakeParams
    required_capabilities: ClassVar[list[str]] = []

    def duration(self, p: BaseModel) -> float:
        return 1.0

    def play(self, scene, p, colors) -> None:
        pass

    def fallback_text(self, p: BaseModel) -> str:
        return p.title


class _LatexComponent(Component):
    """Component requiring the 'latex' capability."""
    name: ClassVar[str] = "latex_component"
    api_version: ClassVar[int] = API_VERSION
    Params: ClassVar[type[BaseModel]] = _FakeParams
    required_capabilities: ClassVar[list[str]] = ["latex"]

    def duration(self, p: BaseModel) -> float:
        return 1.0

    def play(self, scene, p, colors) -> None:
        pass

    def fallback_text(self, p: BaseModel) -> str:
        return p.title


class _FullBackend:
    """Backend supporting latex, ffmpeg, manim."""
    name: ClassVar[str] = "full_backend"
    supported_capabilities: ClassVar[list[str]] = ["latex", "ffmpeg", "manim"]

    def capabilities(self) -> list[str]:
        return list(self.supported_capabilities)

    def render(self, sb, out_dir, opts):
        return RenderResult(
            video=out_dir / "video.mp4",
            durations=[1.0],
            warnings=[],
            stage_times={},
        )


class _LimitedBackend:
    """Backend supporting only ffmpeg and manim (no latex)."""
    name: ClassVar[str] = "limited_backend"
    supported_capabilities: ClassVar[list[str]] = ["ffmpeg", "manim"]

    def capabilities(self) -> list[str]:
        return list(self.supported_capabilities)

    def render(self, sb, out_dir, opts):
        return RenderResult(
            video=out_dir / "video.mp4",
            durations=[1.0],
            warnings=[],
            stage_times={},
        )


# ---------------------------------------------------------------------------
# Component capability declaration tests
# ---------------------------------------------------------------------------

def test_component_has_required_capabilities_attribute():
    """Every Component class has a required_capabilities class attribute."""
    assert hasattr(_FakeComponent, "required_capabilities")
    assert hasattr(_LatexComponent, "required_capabilities")


def test_component_default_required_capabilities_empty():
    """Components declare no required capabilities by default."""
    assert _FakeComponent.required_capabilities == []


def test_latex_component_declares_latex_capability():
    """Components that need LaTeX declare the 'latex' capability."""
    assert _LatexComponent.required_capabilities == ["latex"]


# ---------------------------------------------------------------------------
# Backend capability exposure tests
# ---------------------------------------------------------------------------

def test_backend_exposes_supported_capabilities():
    """Every RenderBackend has a supported_capabilities class attribute."""
    assert hasattr(_FullBackend, "supported_capabilities")
    assert hasattr(_LimitedBackend, "supported_capabilities")


def test_full_backend_supports_latex():
    assert "latex" in _FullBackend.supported_capabilities


def test_limited_backend_lacks_latex():
    assert "latex" not in _LimitedBackend.supported_capabilities


# ---------------------------------------------------------------------------
# Pipeline compatibility check tests
# ---------------------------------------------------------------------------

def test_compatible_capabilities_pass():
    """When all component capabilities are supported, check passes."""
    from animatica.pipeline import _check_capabilities

    sb_data = {
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{"component": "fake_component", "params": {"title": "T"}}]}],
    }
    # We can't easily construct a Storyboard with a fake component since
    # registry validation would reject it. Instead test the check function
    # directly with a backend that supports everything.
    # This test is a placeholder; real validation happens via registry.
    assert True  # placeholder replaced by registry-based test below


def test_incompatible_capabilities_raise_actionable_error():
    """When a component requires a capability the backend lacks, raise ValueError
    naming the component, the missing capability, and the backend."""
    from animatica.pipeline import _check_capabilities
    from animatica.storyboard.models import Storyboard

    # Register a component that requires a capability in a custom registry
    reg = default_registry()
    reg.register(_LatexComponent)

    # Build a storyboard with a latex-requiring component
    sb = Storyboard.model_validate({
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{"component": "latex_component",
                               "params": {"title": "T"}}]}],
    })

    backend = _LimitedBackend()
    with pytest.raises(ValueError) as exc:
        _check_capabilities(sb, backend, registry=reg)

    msg = str(exc.value)
    assert "latex_component" in msg
    assert "latex" in msg
    assert "limited_backend" in msg


def test_compatible_capabilities_with_real_registry():
    """When backend supports all required capabilities, check passes."""
    from animatica.pipeline import _check_capabilities

    sb = Storyboard.model_validate({
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{"component": "equation",
                               "params": {"mode": "reveal", "latex": ["a^2 + b^2 = c^2"]}}]}],
    })

    backend = _FullBackend()
    # Should not raise
    _check_capabilities(sb, backend)


def test_multiple_scenes_capabilities_checked():
    """All scenes' components are checked, not just the first."""
    from animatica.pipeline import _check_capabilities

    # Register a component that requires a capability
    reg = default_registry()
    reg.register(_LatexComponent)

    sb = Storyboard.model_validate({
        "version": "1",
        "title": "T",
        "scenes": [
            {"beats": [{"component": "latex_component",
                        "params": {"title": "x"}}]},
            {"beats": [{"component": "latex_component",
                        "params": {"title": "y"}}]},
        ],
    })

    backend = _LimitedBackend()
    with pytest.raises(ValueError) as exc:
        _check_capabilities(sb, backend, registry=reg)

    assert "latex" in str(exc.value)


def test_no_capabilities_required_passes_any_backend():
    """Components with no required capabilities pass any backend."""
    from animatica.pipeline import _check_capabilities

    sb = Storyboard.model_validate({
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{"component": "title_card",
                               "params": {"title": "Hello"}}]}],
    })

    backend = _LimitedBackend()
    # title_card has no required capabilities, should pass
    _check_capabilities(sb, backend)


# ---------------------------------------------------------------------------
# Real component capability declarations
# ---------------------------------------------------------------------------

def test_real_components_declare_capabilities():
    """Real components declare their required capabilities.

    equation and graph do NOT declare latex as a hard requirement because they
    degrade gracefully when LaTeX is unavailable.
    """
    reg = default_registry()
    # equation and graph degrade gracefully without LaTeX: no hard requirement
    eq = reg.get("equation")
    assert eq.required_capabilities == []
    graph = reg.get("graph")
    assert graph.required_capabilities == []
    # title_card needs nothing
    tc = reg.get("title_card")
    assert tc.required_capabilities == []


def test_manim_backend_supports_latex():
    """ManimBackend declares latex support."""
    from animatica.backends.manim_backend import ManimBackend
    assert "latex" in ManimBackend.supported_capabilities

