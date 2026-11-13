import httpx
import pytest

from animatica.ai.base import ProviderError, RateLimited
from animatica.ai.groq import GroqProvider
from animatica.ai.nim import NIMProvider
from animatica.ai.ollama import OllamaProvider
from animatica.ai.openrouter import OpenRouterProvider
from animatica.config import Config, load_key, save_key


def _handler(status, json_body=None, headers=None):
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=json_body, headers=headers or {})
    return handle


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_groq_sends_authorization_header(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr("animatica.ai.groq.load_key", lambda provider: "sk-groq-test")
    client = _client(handler)
    p = GroqProvider(client=client)
    p.generate("prompt", {})
    assert captured["auth"] == "Bearer sk-groq-test"


def test_nim_sends_authorization_header(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr("animatica.ai.nim.load_key", lambda provider: "sk-nim-test")
    client = _client(handler)
    p = NIMProvider(client=client)
    p.generate("prompt", {})
    assert captured["auth"] == "Bearer sk-nim-test"


def test_openrouter_sends_authorization_header(monkeypatch):
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["auth"] = request.headers.get("authorization")
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    monkeypatch.setattr("animatica.ai.openrouter.load_key", lambda provider: "sk-or-test")
    client = _client(handler)
    p = OpenRouterProvider(client=client)
    p.generate("prompt", {})
    assert captured["auth"] == "Bearer sk-or-test"


def test_ollama_no_key_needed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"response": "{}"})

    client = _client(handler)
    p = OllamaProvider(client=client)
    assert p.generate("prompt", {}) == "{}"


def test_rate_limited_raises_with_retry_after(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, headers={"retry-after": "10"})

    monkeypatch.setattr("animatica.ai.groq.load_key", lambda provider: "sk-x")
    client = _client(handler)
    p = GroqProvider(client=client)
    with pytest.raises(RateLimited) as exc:
        p.generate("prompt", {})
    assert exc.value.retry_after == 10.0


def test_server_error_names_provider(monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    monkeypatch.setattr("animatica.ai.groq.load_key", lambda provider: "sk-x")
    client = _client(handler)
    p = GroqProvider(client=client)
    with pytest.raises(Exception) as exc:
        p.generate("prompt", {})
    assert "groq" in str(exc.value).lower()


def test_router_auto_no_keys_returns_none(monkeypatch):
    monkeypatch.setattr("animatica.ai.router.load_key", lambda provider: None)
    from animatica.ai.router import get_provider
    assert get_provider("auto", Config(cloud_allowed=False)) is None


def test_router_groq_refuses_without_cloud_allowed(monkeypatch):
    from animatica.ai.router import get_provider
    with pytest.raises(ValueError) as exc:
        get_provider("groq", Config(cloud_allowed=False))
    assert "setup" in str(exc.value).lower()


def test_router_openrouter_refuses_non_free_model():
    from animatica.ai.router import get_provider
    from animatica.ai.openrouter import OpenRouterProvider
    from animatica.ai.base import ProviderError
    # openrouter model in providers.toml ends in :free; force a non-free model via provider directly
    p = OpenRouterProvider(model="meta-llama/llama-3.1-8b-instruct")  # no :free
    with pytest.raises(ProviderError):
        p.generate("prompt", {})



# ---------------------------------------------------------------------------
# An HTTP 200 whose message has no text (reasoning model out of tokens, filter)
# ---------------------------------------------------------------------------

from animatica.ai.base import EmptyCompletion


def _sequence_client(bodies):
    """Client that answers each POST with the next body and counts the calls."""
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(200, json=bodies[min(len(calls) - 1, len(bodies) - 1)])

    return _client(handler), calls


NULL_BODY = {"choices": [{"finish_reason": "length", "message": {"content": None, "reasoning_content": "hmm"}}]}
OK_BODY = {"choices": [{"message": {"content": "{}"}}]}


@pytest.mark.parametrize("module,cls", [
    ("groq", GroqProvider), ("nim", NIMProvider), ("openrouter", OpenRouterProvider),
])
def test_null_content_is_retried_once(monkeypatch, module, cls):
    monkeypatch.setattr(f"animatica.ai.{module}.load_key", lambda provider: "sk-x")
    client, calls = _sequence_client([NULL_BODY, OK_BODY])
    p = cls(client=client, model="m:free") if module == "openrouter" else cls(client=client)
    assert p.generate("prompt", {}) == "{}"
    assert len(calls) == 2


@pytest.mark.parametrize("module,cls", [
    ("groq", GroqProvider), ("nim", NIMProvider), ("openrouter", OpenRouterProvider),
])
def test_null_content_twice_raises_with_the_reason(monkeypatch, module, cls):
    monkeypatch.setattr(f"animatica.ai.{module}.load_key", lambda provider: "sk-x")
    client, calls = _sequence_client([NULL_BODY])
    p = cls(client=client, model="m:free") if module == "openrouter" else cls(client=client)
    with pytest.raises(EmptyCompletion) as exc:
        p.generate("prompt", {})
    msg = str(exc.value)
    assert module in msg and "finish_reason='length'" in msg and "max_tokens" in msg
    assert len(calls) == 2


def test_empty_completion_is_a_provider_error():
    assert issubclass(EmptyCompletion, ProviderError)


def test_content_parts_list_is_joined(monkeypatch):
    body = {"choices": [{"message": {"content": [{"type": "text", "text": "{"}, {"type": "text", "text": "}"}]}}]}
    monkeypatch.setattr("animatica.ai.nim.load_key", lambda provider: "sk-x")
    client, _ = _sequence_client([body])
    assert NIMProvider(client=client).generate("prompt", {}) == "{}"


def test_missing_choices_raises_instead_of_keyerror(monkeypatch):
    monkeypatch.setattr("animatica.ai.groq.load_key", lambda provider: "sk-x")
    client, _ = _sequence_client([{"error": "overloaded"}])
    with pytest.raises(EmptyCompletion) as exc:
        GroqProvider(client=client).generate("prompt", {})
    assert "no choices" in str(exc.value)
