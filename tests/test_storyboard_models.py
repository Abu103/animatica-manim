import json

import pytest
from pydantic import ValidationError

from animatica.storyboard.models import (
    MAX_BEATS, MAX_SCENES, MAX_TEXT, Storyboard, dump_storyboard, load_storyboard, migrate,
)

GOOD = {
    "version": "1",
    "title": "Pythagorean Theorem",
    "theme": {"palette": "dark-blue", "font": "default"},
    "scenes": [{"beats": [
        {"component": "title_card", "params": {"title": "Pythagorean Theorem"},
         "caption": "A relationship between the sides of a right triangle."},
        {"component": "equation", "params": {"mode": "reveal", "latex": ["a^2 + b^2 = c^2"]},
         "caption": "The squares of the legs add up to the square of the hypotenuse."},
    ]}],
}


def beat():
    return {"component": "title_card", "params": {"title": "x"}}


def test_limits_constants():
    assert (MAX_SCENES, MAX_BEATS, MAX_TEXT) == (12, 8, 300)


def test_valid_roundtrip(tmp_path):
    sb = Storyboard.model_validate(GOOD)
    p = tmp_path / "s.json"
    dump_storyboard(sb, p)
    assert load_storyboard(p) == sb
    assert json.loads(p.read_text(encoding="utf-8"))["title"] == "Pythagorean Theorem"


def test_too_many_scenes():
    d = {**GOOD, "scenes": [{"beats": [beat()]}] * 13}
    with pytest.raises(ValidationError):
        Storyboard.model_validate(d)


def test_too_many_beats():
    d = {**GOOD, "scenes": [{"beats": [beat()] * 9}]}
    with pytest.raises(ValidationError):
        Storyboard.model_validate(d)


def test_text_too_long():
    b = {**beat(), "caption": "x" * 301}
    with pytest.raises(ValidationError):
        Storyboard.model_validate({**GOOD, "scenes": [{"beats": [b]}]})


def test_title_too_long():
    with pytest.raises(ValidationError):
        Storyboard.model_validate({**GOOD, "title": "x" * 301})


def test_migrate_unknown_version_raises():
    with pytest.raises(ValueError) as e:
        migrate({**GOOD, "version": "0"})
    assert "1" in str(e.value) and "supported" in str(e.value).lower()


def test_empty_scenes_rejected():
    with pytest.raises(ValidationError):
        Storyboard.model_validate({**GOOD, "scenes": []})


def test_empty_beats_rejected():
    with pytest.raises(ValidationError):
        Storyboard.model_validate({**GOOD, "scenes": [{"beats": []}]})

