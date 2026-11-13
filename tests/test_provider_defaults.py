"""Provider default models must be models the provider still serves, and `eval` can pick one per provider."""
from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from typer.testing import CliRunner

from animatica import cli
from animatica.ai.groq import GroqProvider
from animatica.ai.nim import NIMProvider
from animatica.ai.openrouter import OpenRouterProvider
from animatica.ai.router import get_provider
from animatica.config import Config
from animatica.eval import EvalSummary

TOML = Path(__file__).resolve().parent.parent / "src" / "animatica" / "ai" / "providers.toml"

# Retired upstream: Groq shut llama-3.1-8b-instant down for free and developer keys on 2026-08-16
# (replacement named by Groq: openai/gpt-oss-20b); OpenRouter no longer serves this :free id.
RETIRED = {"llama-3.1-8b-instant", "meta-llama/llama-3.1-8b-instruct:free"}


@pytest.mark.parametrize(
    "name, cls", [("groq", GroqProvider), ("openrouter", OpenRouterProvider), ("nim", NIMProvider)]
)
def test_code_default_matches_providers_toml(name, cls):
    data = tomllib.loads(TOML.read_text(encoding="utf-8"))
    assert data[name]["model"] == cls.default_model


@pytest.mark.parametrize("cls", [GroqProvider, OpenRouterProvider, NIMProvider])
def test_no_default_model_is_a_retired_one(cls):
    assert cls.default_model not in RETIRED


def test_openrouter_default_is_a_free_model():
    assert OpenRouterProvider.default_model.endswith(":free")


def test_get_provider_model_override(monkeypatch):
    monkeypatch.setattr("animatica.ai.router.load_key", lambda name: "k")
    cfg = Config(cloud_allowed=True)
    assert get_provider("groq", cfg).model == GroqProvider.default_model
    assert get_provider("groq", cfg, model="openai/gpt-oss-120b").model == "openai/gpt-oss-120b"
    # a model id may itself contain ":" (OpenRouter's ":free")
    assert get_provider("openrouter", cfg, model="x/y:free").model == "x/y:free"


class _Recorder:
    def __init__(self):
        self.asked: list[tuple[str, str | None]] = []

    def get_provider(self, name, config, model=None):
        self.asked.append((name, model))
        return type("P", (), {"name": name, "model": model or "default"})()


@pytest.fixture
def rec(monkeypatch, tmp_path):
    r = _Recorder()
    monkeypatch.setattr("animatica.ai.router.get_provider", r.get_provider)
    monkeypatch.setattr("animatica.eval.run_eval_multi", lambda *a, **k: EvalSummary(results=[]))
    monkeypatch.setattr("animatica.eval.format_multi_table", lambda s: "TABLE")
    monkeypatch.setattr("animatica.eval.run_eval", lambda *a, **k: "SINGLE")
    prompts = tmp_path / "p.txt"
    prompts.write_text("one prompt\n", encoding="utf-8")
    r.prompts = str(prompts)
    return r


def test_models_accepts_provider_colon_model(rec):
    res = CliRunner().invoke(
        cli.app, ["eval", "--models", "nim,groq:openai/gpt-oss-20b,openrouter:nvidia/x:free", "--prompts", rec.prompts]
    )
    assert res.exit_code == 0, res.output
    assert rec.asked == [("nim", None), ("groq", "openai/gpt-oss-20b"), ("openrouter", "nvidia/x:free")]


def test_models_rejects_the_same_provider_twice(rec):
    res = CliRunner().invoke(cli.app, ["eval", "--models", "nim:a,nim:b", "--prompts", rec.prompts])
    assert res.exit_code == 1
    assert "twice" in res.output


def test_single_mode_has_a_model_flag(rec):
    res = CliRunner().invoke(cli.app, ["eval", "--provider", "groq", "--model", "openai/gpt-oss-120b", "--prompts", rec.prompts])
    assert res.exit_code == 0, res.output
    assert rec.asked == [("groq", "openai/gpt-oss-120b")]


def test_unknown_provider_is_a_clean_error_not_a_traceback(monkeypatch, tmp_path):
    prompts = tmp_path / "p.txt"
    prompts.write_text("one prompt\n", encoding="utf-8")
    res = CliRunner().invoke(cli.app, ["eval", "--models", "nope:x", "--prompts", str(prompts)])
    assert res.exit_code == 1
    assert "unknown provider" in res.output
