import pytest

from animatica.ai.base import extract_json
from animatica.ai.template import TemplateMatcher
from animatica.components.registry import default_registry


def test_extract_json_fences():
    assert extract_json('```json\n{"a":1}\n```') == {"a": 1}


def test_extract_json_fences_no_lang():
    assert extract_json('```\n{"b": 2}\n```') == {"b": 2}


def test_extract_json_prose():
    assert extract_json('here: {"c": 3} end.') == {"c": 3}


def test_extract_json_none():
    with pytest.raises(ValueError):
        extract_json("no json here")


def test_template_list_has_at_least_ten():
    m = TemplateMatcher()
    assert len(m.list_templates()) >= 10


def test_each_template_example_matches_and_validates():
    m = TemplateMatcher()
    reg = default_registry()
    for name, example in m.list_templates():
        sb = m.match(example)
        assert sb is not None, name
        assert reg.validate(sb) == [], (name, reg.validate(sb))


def test_nonsense_returns_none():
    assert TemplateMatcher().match("asdfghjkl qwerty uiop") is None


def test_match_returns_registry_valid_storyboard():
    m = TemplateMatcher()
    reg = default_registry()
    sb = m.match("explain the pythagorean theorem a^2 + b^2 = c^2")
    assert sb is not None
    assert reg.validate(sb) == []


def test_keywords_match_whole_words_only():
    from animatica.ai.template import TemplateMatcher
    m = TemplateMatcher()
    assert m.match("explain how canvas rendering works") is None  # 'vs' inside 'canvas'
    assert m.match("decode base64 messages") is None                   # 'code' inside 'decode'
    assert m.match("compare cats vs dogs") is not None

