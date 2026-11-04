import json

import pytest

from animatica.ai.repair import generate_storyboard
from animatica.components.registry import default_registry
from animatica.eval import EvalResult, run_eval

GOOD = {"version": "1", "title": "T",
        "scenes": [{"beats": [{"component": "title_card", "params": {"title": "T"}, "caption": "c"}]}]}


class GoodProvider:
    name = "good"
    def __init__(self): self.calls = 0
    def generate(self, prompt, schema):
        self.calls += 1
        return json.dumps(GOOD)


class FlakyProvider:
    name = "flaky"
    def __init__(self): self.calls = 0
    def generate(self, prompt, schema):
        self.calls += 1
        return "nope" if self.calls == 1 else json.dumps(GOOD)


class BadProvider:
    name = "bad"
    def generate(self, prompt, schema):
        return "nope"


def test_eval_scores_per_prompt():
    results = run_eval(["p1", "p2"], GoodProvider(), default_registry())
    assert len(results) == 2
    r = results[0]
    assert isinstance(r, EvalResult)
    assert r.valid_first_try is True and r.retries == 0 and r.warnings == []


def test_eval_counts_retries_and_failures():
    results = run_eval(["p1"], FlakyProvider(), default_registry())
    assert results[0].valid_first_try is False and results[0].retries == 1
    results = run_eval(["p1"], BadProvider(), default_registry(), max_retries=1)
    assert results[0].valid_first_try is False and results[0].error is not None


def test_eval_summary_table():
    results = run_eval(["p1", "p2"], GoodProvider(), default_registry())
    text = run_eval(["p1"], GoodProvider(), default_registry(), as_table=True)
    assert "prompt" in text and "valid" in text
