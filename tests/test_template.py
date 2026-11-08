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



def test_by_name_returns_the_named_template():
    from animatica.ai.template import TemplateMatcher

    m = TemplateMatcher()
    name, _example = m.list_templates()[0]
    storyboard = m.by_name(name)

    assert storyboard is not None
    assert storyboard.scenes
    assert default_registry().validate(storyboard) == []


def test_by_name_is_not_keyword_matching():
    """Names are not prompts: "title_card" has no whole-word boundary."""
    from animatica.ai.template import TemplateMatcher

    m = TemplateMatcher()
    assert m.match("title_card") is None
    assert m.by_name("title_card") is not None


def test_by_name_unknown_returns_none():
    from animatica.ai.template import TemplateMatcher

    assert TemplateMatcher().by_name("nope-not-a-template") is None
