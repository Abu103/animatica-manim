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
    assert info["sent_back"] == 2
    assert info["repair_error"] == ""
    assert sb.scenes[0].beats[0].caption == "grew 12%"
    assert "parse error" in provider.prompts[1]


def test_trailing_prose_with_another_object_is_ignored():
    assert extract_json('{"a": 1} here is another dict {"b": 2}') == {"a": 1}


def test_recovery_does_not_corrupt_string_arrays():
    text = '{"a": ["x","y"], "b" "z"}'
    with pytest.raises(json.JSONDecodeError, match="Expecting ':' delimiter"):
        json.loads(text)
    assert extract_json(text) == {"a": ["x", "y"], "b": "z"}


def test_provider_error_stops_repair_retries():
    class Exploding:
        name = "exploding"
        calls = 0

        def generate(self, prompt, schema):
            self.calls += 1
            raise RuntimeError("provider offline")

    provider = Exploding()
    _, info = repair_with_facts("topic", _bad_number_storyboard(), provider,
                                default_registry())
    assert provider.calls == 1
    assert "provider offline" in info["repair_error"]
    assert info["sent_back"] == 0


def test_parse_error_is_not_repeated_after_a_parsed_reply():
    invalid_component = (
        '{"version":"1","title":"T","scenes":[{"beats":['
        '{"component":"stat_callout","params":{"value":"12%","label":"g"},'
        '"caption":"grew 40%"},'
        '{"component":"nope","params":{}}]}]}'
    )

    class Provider:
        name = "fake"
        calls = 0
        prompts: list[str] = []

        def generate(self, prompt, schema):
            self.prompts.append(prompt)
            self.calls += 1
            return ["no json at all", invalid_component, _fixed_storyboard()][self.calls - 1]

    provider = Provider()
    repair_with_facts("topic", _bad_number_storyboard(), provider,
                      default_registry(), max_verify_retries=3)
    assert provider.calls == 3
    assert "parse error" in provider.prompts[1]
    assert "parse error" not in provider.prompts[2]
