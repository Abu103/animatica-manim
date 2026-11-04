"""Regression tests for the 'StoryboardGenerationError on every non-template prompt' bug.

Root cause: providers only ever received the bare user request, so the model
was never told to emit storyboard JSON or which components exist.
"""
import json

import httpx
import pytest
from typer.testing import CliRunner

from animatica.ai.base import (
    ProviderError,
    RateLimited,
    StoryboardGenerationError,
)
from animatica.ai.prompt import build_prompt
from animatica.ai.repair import generate_storyboard
from animatica.cli import app
from animatica.components.registry import default_registry

GOOD = {
    "version": "1",
    "title": "Taylor",
    "scenes": [{"beats": [{"component": "title_card", "params": {"title": "Taylor"}}]}],
}


class Recorder:
    name = "rec"

    def __init__(self, replies):
        self.replies = list(replies)
        self.prompts = []

    def generate(self, prompt, schema):
        self.prompts.append(prompt)
        return self.replies.pop(0)


def test_prompt_tells_model_the_format_and_components():
    reg = default_registry()
    text = build_prompt("explain the taylor series", reg)
    assert "explain the taylor series" in text
    assert "JSON" in text  # also required by json_object response_format
    for name in reg.names():
        assert name in text
    assert '"scenes"' in text and '"beats"' in text and '"component"' in text
    assert "12" in text and "8" in text  # scene / beat limits


def test_first_provider_call_includes_instructions():
    p = Recorder(["```json\n" + json.dumps(GOOD) + "\n```"])
    generate_storyboard("explain the taylor series", p, default_registry())
    assert "title_card" in p.prompts[0]
    assert "explain the taylor series" in p.prompts[0]


def test_retry_prompt_keeps_instructions_request_and_errors():
    p = Recorder(["nonsense", json.dumps(GOOD)])
    generate_storyboard("explain the taylor series", p, default_registry())
    retry = p.prompts[1]
    assert "title_card" in retry
    assert "explain the taylor series" in retry
    assert "Errors:" in retry and "parse error" in retry


def test_error_carries_last_errors_and_provider_name():
    p = Recorder(["nope"] * 3)
    with pytest.raises(StoryboardGenerationError) as exc:
        generate_storyboard("x", p, default_registry())
    assert exc.value.errors and "parse error" in exc.value.errors[0]


def _patch_provider(monkeypatch, provider):
    monkeypatch.setattr("animatica.pipeline.get_provider", lambda name, cfg: provider)


def test_cli_shows_validation_errors_not_traceback(monkeypatch, tmp_path):
    _patch_provider(monkeypatch, Recorder(["nope"] * 3))
    r = CliRunner().invoke(app, ["make", "explain the taylor series", "-o", str(tmp_path)])
    assert r.exit_code == 1
    assert "Traceback" not in r.output
    assert "failed to generate a valid storyboard" in r.output
    assert "parse error" in r.output  # the hidden cause is now visible


class Raises:
    name = "r"

    def __init__(self, exc):
        self.exc = exc

    def generate(self, prompt, schema):
        raise self.exc


@pytest.mark.parametrize(
    "exc, needle",
    [
        (ProviderError("nim: HTTP 404: model not found"), "model not found"),
        (RateLimited(retry_after=7), "rate limited"),
    ],
)
def test_cli_provider_failures_are_friendly(monkeypatch, tmp_path, exc, needle):
    _patch_provider(monkeypatch, Raises(exc))
    r = CliRunner().invoke(app, ["make", "explain the taylor series", "-o", str(tmp_path)])
    assert r.exit_code == 1
    assert "Traceback" not in r.output
    assert needle in r.output


def test_provider_template_gives_clear_message(tmp_path):
    r = CliRunner().invoke(
        app, ["make", "explain the taylor series", "--provider", "template", "-o", str(tmp_path)]
    )
    assert r.exit_code == 1
    assert "unknown provider" not in r.output
    assert "template" in r.output.lower()


@pytest.mark.parametrize("modpath, cls", [
    ("animatica.ai.groq", "GroqProvider"),
    ("animatica.ai.nim", "NIMProvider"),
    ("animatica.ai.openrouter", "OpenRouterProvider"),
])
def test_cloud_payload_sets_max_tokens(monkeypatch, modpath, cls):
    import importlib

    mod = importlib.import_module(modpath)
    monkeypatch.setattr(f"{modpath}.load_key", lambda p: "k")
    seen = {}

    def handler(request):
        seen.update(json.loads(request.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "{}"}}]})

    prov = getattr(mod, cls)(client=httpx.Client(transport=httpx.MockTransport(handler)))
    prov.generate("p", {})
    assert seen.get("max_tokens", 0) >= 2048


def test_provider_result_is_cached(monkeypatch, tmp_path):
    prov = Recorder([json.dumps(GOOD)])
    _patch_provider(monkeypatch, prov)

    class Stop:
        def render(self, *a, **k):
            raise RuntimeError("stop before render")

    monkeypatch.setattr("animatica.pipeline.ManimBackend", Stop)
    for _ in range(2):
        r = CliRunner().invoke(app, ["make", "explain the taylor series", "-o", str(tmp_path)])
        assert "stop before render" in r.output
    assert len(prov.prompts) == 1  # second run served from cache


def test_unexpected_error_has_no_traceback(monkeypatch, tmp_path):
    _patch_provider(monkeypatch, Raises(RuntimeError("boom")))
    r = CliRunner().invoke(app, ["make", "explain the taylor series", "-o", str(tmp_path)])
    assert r.exit_code == 1 and "boom" in r.output and "--debug" in r.output


def test_setup_command_is_named_setup():
    r = CliRunner().invoke(app, ["--help"])
    assert " setup " in r.output and "setup-cmd" not in r.output


def test_http_error_names_model_and_hints_override(monkeypatch):
    monkeypatch.setattr("animatica.ai.nim.load_key", lambda p: "k")
    from animatica.ai.nim import NIMProvider

    c = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404, text="404 page not found")))
    with pytest.raises(ProviderError) as exc:
        NIMProvider(client=c).generate("p", {})
    msg = str(exc.value)
    assert NIMProvider.default_model in msg and "--model" in msg


def test_model_env_override(monkeypatch):
    from animatica.ai.nim import NIMProvider

    monkeypatch.setenv("ANIMATICA_MODEL", "meta/some-model")
    assert NIMProvider().model == "meta/some-model"


def test_cli_model_option_sets_override(monkeypatch, tmp_path):
    seen = {}

    def fake(name, cfg):
        import os
        seen["m"] = os.environ.get("ANIMATICA_MODEL")
        return Raises(ProviderError("stop"))

    monkeypatch.setenv("ANIMATICA_MODEL", "")  # registers cleanup of the CLI override
    monkeypatch.setattr("animatica.pipeline.get_provider", fake)
    CliRunner().invoke(app, ["make", "explain the taylor series", "--model", "x/y", "-o", str(tmp_path)])
    assert seen["m"] == "x/y"

