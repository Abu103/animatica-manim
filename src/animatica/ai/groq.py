"""Groq cloud provider."""
from __future__ import annotations

from animatica.ai.base import BaseProvider, ProviderError
from animatica.config import load_key


class GroqProvider(BaseProvider):
    name = "groq"
    default_model = "openai/gpt-oss-20b"

    def generate(self, prompt: str, schema: dict) -> str:
        key = load_key("groq")
        if not key:
            raise ProviderError("groq: no API key configured; run 'animatica setup'")
        headers = {"Authorization": f"Bearer {key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        resp = self._post(
            "https://api.groq.com/openai/v1/chat/completions", headers, payload
        )
        return resp.json()["choices"][0]["message"]["content"]

