"""OpenRouter cloud provider (:free models by default)."""
from __future__ import annotations

from animatica.ai.base import BaseProvider, ProviderError, _openrouter_allow_paid
from animatica.config import load_key


class OpenRouterProvider(BaseProvider):
    name = "openrouter"
    default_model = "nvidia/nemotron-3.5-super-vl:free"

    def __init__(self, client=None, model=None):
        super().__init__(client=client, model=model)
        self.allow_paid = _openrouter_allow_paid()

    def generate(self, prompt: str, schema: dict) -> str:
        if not self.model.endswith(":free") and not self.allow_paid:
            raise ProviderError(
                "openrouter: model is not a :free model; set allow_paid=true in providers.toml"
            )
        key = load_key("openrouter")
        if not key:
            raise ProviderError(
                "openrouter: no API key configured; run 'animatica setup'"
            )
        headers = {"Authorization": f"Bearer {key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        resp = self._post(
            "https://openrouter.ai/api/v1/chat/completions", headers, payload
        )
        return resp.json()["choices"][0]["message"]["content"]

