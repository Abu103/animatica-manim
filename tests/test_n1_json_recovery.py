"""N1: recover malformed provider JSON before spending a retry.

The two fixtures below reproduce the shapes seen from nim: a scene-fill
output with a missing ``:`` at column 2155, and a repair-call output cut
inside a string at column 3083. Both shapes must be recoverable by
extract_json; only genuinely unrecoverable output may burn a retry, and
then the parse error text goes into the next prompt.
"""
from __future__ import annotations

import json

import pytest

from animatica.ai.base import extract_json
from animatica.ai.repair import generate_storyboard, repair_with_facts
from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard


def _missing_colon_at(column: int) -> str:
    # A key ("narration") lost its colon after a long string value: json
    # raises "Expecting ':' delimiter" at the reported column. Both nim
    # repros (2155 scene fill, 3083 repair call) have this shape.
    head = ('{"version":"1","title":"T","scenes":[{"beats":[{"component":"stat_callout",'
            '"params":{"value":"42","label":"x"},"caption":"')
    key = '","narration"'
    return head + "x" * (column - len(head) - len(key) - 2) + key + ' "text"}]}]}'


VALID = ('{"version":"1","title":"T","scenes":[{"beats":['
         '{"component":"stat_callout","params":{"value":"42","label":"x"},'
         '"caption":"42"}]}]}')


class _Provider:
    def __init__(self, *replies: str) -> None:
        self.replies = list(replies)
        self.prompts: list[str] = []

    @property
    def name(self) -> str:
        return "fake"

    def generate(self, prompt: str, schema: dict) -> str:
        self.prompts.append(prompt)
        return self.replies.pop(0)


def test_fixtures_have_the_reported_json_error_shapes():
    for column in (2155, 3083):
        with pytest.raises(json.JSONDecodeError) as exc:
            json.loads(_missing_colon_at(column))
        assert "Expecting ':' delimiter" in exc.value.msg
        assert exc.value.colno == column


def test_extract_json_recovers_missing_colon_shape():
    data = extract_json(_missing_colon_at(2155))
    assert data["version"] == "1"
    assert data["scenes"][0]["beats"][0]["component"] == "stat_callout"


def test_extract_json_recovers_repair_call_shape():
    data = extract_json(_missing_colon_at(3083))
    beat = data["scenes"][0]["beats"][0]
    assert beat["narration"] == "text"


def test_extract_json_still_strips_fences_and_trailing_prose():
    fenced = "Here you go:\n```json\n" + VALID + "\n```\nHope this helps."
    assert extract_json(fenced) == json.loads(VALID)


def test_recoverable_output_does_not_burn_a_retry():
    short = ('{"version":"1","title":"T","scenes":[{"beats":['
             '{"component":"stat_callout","params":{"value":"42","label":"x"},'
             '"caption":"42","narration" "spoken"}]}]}')
    with pytest.raises(json.JSONDecodeError, match="Expecting ':' delimiter"):
        json.loads(short)
    provider = _Provider("```json\n" + short + "\n```")
    sb = generate_storyboard("topic", provider, default_registry())
    assert len(provider.prompts) == 1
    assert sb.title == "T" and sb.scenes[0].beats[0].component == "stat_callout"


def test_unrecoverable_output_retries_with_the_parse_error():
    provider = _Provider("there is no json object here", VALID)
    sb = generate_storyboard("topic", provider, default_registry())
    assert len(provider.prompts) == 2
    assert "parse error" in provider.prompts[1]
    assert "no JSON object" in provider.prompts[1]
    assert sb.title == "T"


def _bad_number_storyboard() -> Storyboard:
    return Storyboard.model_validate(json.loads(
        '{"version":"1","title":"T","scenes":[{"beats":['
        '{"component":"stat_callout","params":{"value":"12%","label":"g"},'
        '"caption":"grew 40%"}]}]}'
    ))


def _fixed_storyboard() -> str:
    return ('{"version":"1","title":"T","scenes":[{"beats":['
            '{"component":"stat_callout","params":{"value":"12%","label":"g"},'
            '"caption":"grew 12%"}]}]}')


def test_repair_with_facts_retries_with_the_parse_error():
    provider = _Provider("not json at all", _fixed_storyboard())
    sb, info = repair_with_facts("topic", _bad_number_storyboard(), provider,
                                 default_registry())
    # The malformed parse attempt consumed a send-back; the next call then
    # produced the corrected caption, so two send-backs were used in total.
    assert info["sent_back"] == 2
    assert info["repair_error"] == ""
    assert sb.scenes[0].beats[0].caption == "grew 12%"
    assert "parse error" in provider.prompts[1]
