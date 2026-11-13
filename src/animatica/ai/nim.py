"""NVIDIA NIM cloud provider."""
from __future__ import annotations

from animatica.ai.base import BaseProvider, ProviderError
from animatica.config import load_key


class NIMProvider(BaseProvider):
    name = "nim"
    default_model = "nvidia/nemotron-3.5-super-vl-120b-a12b"

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
        return self._chat_text(
            "https://integrate.api.nvidia.com/v1/chat/completions", headers, payload
        )

