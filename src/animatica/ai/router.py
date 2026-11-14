"""AI provider router: selects groq / openrouter / nim / ollama."""
from __future__ import annotations

from animatica.ai.groq import GroqProvider
from animatica.ai.nim import NIMProvider
from animatica.ai.ollama import OllamaProvider
from animatica.ai.openrouter import OpenRouterProvider
from animatica.config import Config, load_key

_CLOUD = ("groq", "openrouter", "nim")


def _build(name: str):
    if name == "groq":
        return GroqProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    if name == "nim":
        return NIMProvider()
    if name == "ollama":
        return OllamaProvider()
    return None


def get_provider(name: str, config: Config, model: str | None = None):
    """Return a provider for `name`, or None for `auto` when none configured.

    `model` (optional) names the model id this provider should use instead of its default, so two
    providers in one process can use two different models."""
    provider = _get_provider(name, config)
    if provider is not None and model:
        provider.model = model
    return provider


def _get_provider(name: str, config: Config):
    if name == "auto":
        for pname in _CLOUD:
            if config.cloud_allowed and load_key(pname):
                return _build(pname)
        return None
    provider = _build(name)
    if provider is None:
        raise ValueError(f"unknown provider {name!r}")
    if name in _CLOUD:
        if not config.cloud_allowed:
            raise ValueError(
                f"{name} is a cloud provider; run 'animatica setup' to enable cloud access"
            )
        if not load_key(name):
            raise ValueError(
                f"no API key configured for {name}; run 'animatica setup' to store it"
            )
    return provider

