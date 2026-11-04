from typing import ClassVar

import pytest
from pydantic import BaseModel

from animatica.components.base import Component
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.plugins import load_entry_points
from animatica.storyboard.models import Storyboard


class FakeParams(BaseModel):
    title: str
    count: int = 1


class Fake(Component):
    name: ClassVar[str] = "fake"
    Params: ClassVar[type[BaseModel]] = FakeParams

    def duration(self, p):
        return 1.0

    def play(self, scene, p, colors):
        pass

    def fallback_text(self, p):
        return p.title


class Future(Fake):
    name: ClassVar[str] = "future"
    api_version: ClassVar[int] = 2


def sb(*beats):
    return Storyboard.model_validate({"title": "t", "scenes": [{"beats": list(beats)}]})


def test_register_and_get():
    r = ComponentRegistry()
    r.register(Fake)
    assert r.names() == ["fake"]
    assert isinstance(r.get("fake"), Fake)


def test_validate_good_beat():
    r = ComponentRegistry()
    r.register(Fake)
    assert r.validate(sb({"component": "fake", "params": {"title": "hi"}})) == []


def test_unknown_component_lists_valid_names():
    r = ComponentRegistry()
    r.register(Fake)
    errs = r.validate(sb({"component": "nope", "params": {}}))
    assert len(errs) == 1 and "nope" in errs[0] and "fake" in errs[0]
    assert "scene 1" in errs[0] and "beat 1" in errs[0]


def test_bad_params_name_the_field():
    r = ComponentRegistry()
    r.register(Fake)
    errs = r.validate(sb({"component": "fake", "params": {"count": "many"}}))
    joined = " ".join(errs)
    assert "title" in joined and "count" in joined


def test_json_schema_has_one_entry_per_component():
    r = ComponentRegistry()
    r.register(Fake)
    schema = r.json_schema()
    assert set(schema) == {"fake"} and "title" in schema["fake"]["properties"]


def test_api_version_mismatch_rejected():
    r = ComponentRegistry()
    with pytest.raises(ValueError) as e:
        r.register(Future)
    assert "api_version" in str(e.value)


def test_duplicate_name_rejected():
    r = ComponentRegistry()
    r.register(Fake)
    with pytest.raises(ValueError):
        r.register(Fake)


def test_load_entry_points_empty_group():
    assert load_entry_points("animatica.test_no_such_group") == {}


def test_default_registry_is_a_registry():
    assert isinstance(default_registry(), ComponentRegistry)

