import json

import pytest

from animatica.ai.repair import generate_storyboard
from animatica.components.registry import default_registry
from animatica.eval import EvalResult, EvalSummary, run_eval, run_eval_multi, format_table, format_multi_table

GOOD = {"version": "1", "title": "T",
        "scenes": [{"beats": [{"component": "title_card", "params": {"title": "T"}, "caption": "c"}]}]}


class GoodProvider:
    name = "good"
    model = "good-model-v1"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, schema):
        self.calls += 1
        return json.dumps(GOOD)


class FlakyProvider:
    name = "flaky"
    model = "flaky-model-v2"

    def __init__(self):
        self.calls = 0

    def generate(self, prompt, schema):
        self.calls += 1
        return "nope" if self.calls == 1 else json.dumps(GOOD)


class BadProvider:
    name = "bad"
    model = "bad-model-v3"

    def generate(self, prompt, schema):
        return "nope"


# ---------------------------------------------------------------------------
# Single-provider eval: first-try vs eventual vs errors
# ---------------------------------------------------------------------------

def test_eval_scores_per_prompt():
    results = run_eval(["p1", "p2"], GoodProvider(), default_registry())
    assert len(results) == 2
    r = results[0]
    assert isinstance(r, EvalResult)
    assert r.valid_first_try is True
    assert r.eventual_success is True
    assert r.retries == 0
    assert r.warnings == []
    assert r.model == "good-model-v1"
    assert r.provider == "good"


def test_eval_reports_model_id():
    results = run_eval(["p1"], GoodProvider(), default_registry())
    assert results[0].model == "good-model-v1"


def test_eval_counts_retries_and_failures():
    results = run_eval(["p1"], FlakyProvider(), default_registry())
    assert results[0].valid_first_try is False
    assert results[0].eventual_success is True  # succeeded on retry
    assert results[0].retries == 1
    assert results[0].model == "flaky-model-v2"

    results = run_eval(["p1"], BadProvider(), default_registry(), max_retries=1)
    assert results[0].valid_first_try is False
    assert results[0].eventual_success is False  # never succeeded
    assert results[0].error is not None
    assert results[0].model == "bad-model-v3"


def test_eval_summary_table():
    results = run_eval(["p1", "p2"], GoodProvider(), default_registry())
    text = run_eval(["p1"], GoodProvider(), default_registry(), as_table=True)
    assert "prompt" in text
    assert "first" in text  # first-try column
    assert "eventual" in text  # eventual-success column


def test_eval_result_has_provider():
    results = run_eval(["p1"], GoodProvider(), default_registry())
    assert isinstance(results, list)
    assert results[0].provider == "good"
    assert results[0].model == "good-model-v1"


# ---------------------------------------------------------------------------
# Multi-provider eval
# ---------------------------------------------------------------------------

def test_eval_multi_runs_all_providers():
    summary = run_eval_multi(["p1"], [GoodProvider(), FlakyProvider()], default_registry())
    assert isinstance(summary, EvalSummary)
    assert len(summary.results) == 2
    good = [r for r in summary.results if r.provider == "good"][0]
    flaky = [r for r in summary.results if r.provider == "flaky"][0]
    assert good.valid_first_try is True
    assert good.eventual_success is True
    assert flaky.valid_first_try is False
    assert flaky.eventual_success is True  # succeeded on retry


def test_eval_multi_format_table():
    summary = run_eval_multi(["p1"], [GoodProvider(), FlakyProvider()], default_registry())
    text = format_multi_table(summary)
    assert "good" in text and "flaky" in text
    assert "VALID/Total" in text
    # retry-valid annotation should appear for flaky
    assert "retry" in text.lower()


def test_eval_multi_empty_providers():
    summary = run_eval_multi([], [], default_registry())
    assert isinstance(summary, EvalSummary)
    assert summary.total == 0


# ---------------------------------------------------------------------------
# EvalSummary computed properties
# ---------------------------------------------------------------------------

def test_eval_summary_properties():
    summary = run_eval_multi(["p1", "p2"], [GoodProvider(), BadProvider()], default_registry())
    assert summary.total == 4
    assert summary.valid_first_try_count == 2  # good provider, 2 prompts
    assert summary.eventual_success_count == 2  # good provider, 2 prompts (bad never succeeds)
    assert summary.retry_success_count == 0  # good provider always first-try
    assert summary.error_count == 2  # bad provider, 2 prompts


def test_eval_summary_retry_success_property():
    """retry_success_count counts providers that succeeded only after retries."""
    summary = run_eval_multi(["p1"], [FlakyProvider(), GoodProvider()], default_registry())
    assert summary.total == 2
    assert summary.retry_success_count == 1  # flaky succeeded on retry
    assert summary.valid_first_try_count == 1  # good provider first-try
    assert summary.eventual_success_count == 2  # both eventually succeeded


def test_eval_table_shows_retry_valid():
    """format_table mentions retry-valid when some results succeeded after retries."""
    results = run_eval(["p1"], FlakyProvider(), default_registry())
    text = format_table(results)
    assert "retry" in text.lower()
    assert "first-try valid" in text
    assert "eventual valid" in text


# --- --save-dir: keep raw outputs so a live run can become offline fixtures ----------------------
def test_save_dir_records_raw_responses_for_ok_and_failed_prompts(tmp_path):
    ok = run_eval(["good one"], FlakyProvider(), max_retries=2, save_dir=tmp_path)
    bad = run_eval(["bad one"], BadProvider(), max_retries=1, save_dir=tmp_path)
    assert ok[0].eventual_success and not bad[0].eventual_success
    files = sorted(tmp_path.glob("*.json"))
    assert len(files) == 2
    recs = {json.loads(f.read_text(encoding="utf-8"))["prompt"]: json.loads(f.read_text(encoding="utf-8")) for f in files}
    good = recs["good one"]
    assert good["ok"] and good["calls"] == 2 and good["responses"][0] == "nope"
    assert good["storyboard"]["title"] == "T"
    failed = recs["bad one"]
    assert not failed["ok"] and failed["errors"] and len(failed["responses"]) == 2


def test_save_dir_unset_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    run_eval(["x"], GoodProvider(), max_retries=0)
    assert list(tmp_path.iterdir()) == []


def test_eval_cli_accepts_save_dir(tmp_path, monkeypatch):
    from typer.testing import CliRunner
    from animatica.cli import app
    import animatica.ai.router as router
    monkeypatch.setattr(router, "get_provider", lambda *a, **k: GoodProvider())
    prompts = tmp_path / "p.txt"
    prompts.write_text("one\ntwo\n", encoding="utf-8")
    out = tmp_path / "rec"
    r = CliRunner().invoke(app, ["eval", "--prompts", str(prompts), "--max-retries", "0", "--save-dir", str(out)])
    assert r.exit_code == 0, r.output
    assert len(list(out.glob("*.json"))) == 2
