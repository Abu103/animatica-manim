"""NVIDIA NIM cloud provider."""
from __future__ import annotations

import os

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
            # Reasoning tokens count against max_tokens. 4096 was spent entirely
            # on thinking for the larger (two-stage) prompts -> empty content.
            "max_tokens": 16384,
        }
        # We only need schema JSON, so thinking is off by default (NVIDIA documents
        # chat_template_kwargs.enable_thinking for the Nemotron 3 Super family).
        # ANIMATICA_NIM_THINKING=1 turns it back on for models that need it.
        if os.environ.get("ANIMATICA_NIM_THINKING", "").lower() not in ("1", "true", "yes"):
            payload["chat_template_kwargs"] = {"enable_thinking": False}
        return self._chat_text(
            "https://integrate.api.nvidia.com/v1/chat/completions", headers, payload
        )

