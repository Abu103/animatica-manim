"""Ollama local provider (no API key required)."""
from __future__ import annotations

from animatica.ai.base import BaseProvider, ProviderError


class OllamaProvider(BaseProvider):
    name = "ollama"
    needs_key = False
    default_model = "llama3.1"

    def generate(self, prompt: str, schema: dict) -> str:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "format": "json",
        }
        resp = self._post("http://localhost:11434/api/generate", {}, payload)
        try:
            return resp.json()["response"]
        except (KeyError, ValueError) as exc:
            raise ProviderError(f"ollama: bad response ({exc})") from exc

