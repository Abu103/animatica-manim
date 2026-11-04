import pytest

from animatica.ai.router import get_provider
from animatica.config import Config


def test_router_auto_picks_first_configured(monkeypatch):
    from animatica.ai import groq

    monkeypatch.setattr("animatica.ai.router.load_key", lambda provider: "sk-x" if provider == "groq" else None)
    p = get_provider("auto", Config(cloud_allowed=True))
    assert isinstance(p, groq.GroqProvider)


def test_router_named_provider_returns_instance():
    from animatica.ai import ollama
    p = get_provider("ollama", Config(cloud_allowed=False))
    assert isinstance(p, ollama.OllamaProvider)


def test_router_unknown_provider_raises():
    with pytest.raises(ValueError):
        get_provider("nope", Config(cloud_allowed=True))

