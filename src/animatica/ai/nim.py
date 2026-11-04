"""NVIDIA NIM cloud provider."""
from __future__ import annotations

from animatica.ai.base import BaseProvider, ProviderError
from animatica.config import load_key


class NIMProvider(BaseProvider):
    name = "nim"
    default_model = "meta/llama-3.1-8b-instruct"

    def generate(self, prompt: str, schema: dict) -> str:
        key = load_key("nim")
        if not key:
            raise ProviderError("nim: no API key configured; run 'animatica setup'")
        headers = {"Authorization": f"Bearer {key}"}
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": 4096,
        }
        resp = self._post(
            "https://integrate.api.nvidia.com/v1/chat/completions", headers, payload
        )
        return resp.json()["choices"][0]["message"]["content"]

