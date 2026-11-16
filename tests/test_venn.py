import json

import pytest
from pydantic import ValidationError

from animatica.components.venn import Venn

TWO = {
    "title": "Even and prime",
    "sets": [{"label": "Even", "items": ["4", "6"]}, {"label": "Prime", "items": ["3", "5"]}],
    "shared": [{"of": [0, 1], "items": ["2"]}],
}
THREE = {
    "title": "Pets",
    "sets": [{"label": "Dogs", "items": ["Rex"]}, {"label": "Cats", "items": ["Tom"]}, {"label": "Fish", "items": ["Nemo"]}],
    "shared": [{"of": [0, 1], "items": ["a"]}, {"of": [0, 1, 2], "items": ["z"]}],
}


def test_valid_two_and_three_set_diagrams():
    assert len(Venn.Params.model_validate(TWO).sets) == 2
    assert len(Venn.Params.model_validate(THREE).sets) == 3


def test_shared_is_optional():
    Venn.Params.model_validate({"title": "t", "sets": [{"label": "A"}, {"label": "B"}]})


def test_duration_is_two_seconds_plus_per_set_and_per_shared_region():
    assert Venn().duration(Venn.Params.model_validate(TWO)) == pytest.approx(2.0 + 0.7 * 2 + 0.5 * 1)
    assert Venn().duration(Venn.Params.model_validate(THREE)) == pytest.approx(2.0 + 0.7 * 3 + 0.5 * 2)


@pytest.mark.parametrize("sets", [
    [{"label": "A"}],                                                    # one set
    [{"label": "A"}, {"label": "B"}, {"label": "C"}, {"label": "D"}],    # four sets
])
def test_two_or_three_sets_only(sets):
    with pytest.raises(ValidationError):
        Venn.Params.model_validate({"title": "t", "sets": sets})


@pytest.mark.parametrize("of", [[0], [0, 0], [0, 2], [-1, 1], [0, 1, 2]])  # 2 sets: needs exactly [0,1]; [0,1,2] out of range
def test_bad_shared_indices_are_rejected(of):
    with pytest.raises(ValidationError):
        Venn.Params.model_validate({"title": "t", "sets": [{"label": "A"}, {"label": "B"}], "shared": [{"of": of, "items": ["x"]}]})


def test_shared_region_given_twice_is_rejected_regardless_of_order():
    bad = {"title": "t", "sets": [{"label": "A"}, {"label": "B"}], "shared": [{"of": [0, 1]}, {"of": [1, 0]}]}
    with pytest.raises(ValidationError, match="twice"):
        Venn.Params.model_validate(bad)


def test_item_limits():
    for items in (["a", "b", "c", "d"], ["x" * 15]):
        with pytest.raises(ValidationError):
            Venn.Params.model_validate({"title": "t", "sets": [{"label": "A", "items": items}, {"label": "B"}]})


def test_set_labels_must_differ():
    with pytest.raises(ValidationError, match="differ"):
        Venn.Params.model_validate({"title": "t", "sets": [{"label": "A"}, {"label": "a"}]})


def test_fallback_text_names_every_region():
    text = Venn().fallback_text(Venn.Params.model_validate(THREE))
    assert "Dogs" in text and "Dogs + Cats: a" in text and "Dogs + Cats + Fish: z" in text and text.startswith("Pets")


def test_schema_is_json_serialisable():
    json.dumps(Venn.Params.model_json_schema())


def test_three_sets_leave_room_for_one_item_per_shared_region_and_two_per_set():
    sets = [{"label": "A"}, {"label": "B"}, {"label": "C"}]
    with pytest.raises(ValidationError, match="three sets"):
        Venn.Params.model_validate({"title": "t", "sets": sets, "shared": [{"of": [0, 1], "items": ["x", "y"]}]})
    with pytest.raises(ValidationError, match="three sets"):
        Venn.Params.model_validate({"title": "t", "sets": [{"label": "A", "items": ["1", "2", "3"]}, *sets[1:]]})
    Venn.Params.model_validate({"title": "t", "sets": [{"label": "A", "items": ["1", "2"]}, *sets[1:]],
                                "shared": [{"of": [0, 1, 2], "items": ["z"]}]})


def test_three_sets_shared_items_are_short_enough_for_the_crescent_they_sit_in():
    sets = [{"label": "A"}, {"label": "B"}, {"label": "C"}]
    with pytest.raises(ValidationError, match="7 characters"):
        Venn.Params.model_validate({"title": "t", "sets": sets, "shared": [{"of": [1, 2], "items": ["Whiskers"]}]})
    Venn.Params.model_validate({"title": "t", "sets": sets, "shared": [{"of": [1, 2], "items": ["Whisker"]}]})
