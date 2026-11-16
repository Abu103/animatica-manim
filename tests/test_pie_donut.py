import json

import pytest
from pydantic import ValidationError

from animatica.components.pie_donut import PieDonut

BROWSERS = {
    "title": "Browser share",
    "slices": [{"label": "Chrome", "value": 65}, {"label": "Safari", "value": 20}, {"label": "Other", "value": 15}],
}


def test_valid_pie_and_donut_with_center_text():
    p = PieDonut.Params.model_validate({**BROWSERS, "donut": True, "center": "2024"})
    assert p.donut and p.center == "2024"
    assert PieDonut.Params.model_validate(BROWSERS).donut is False


def test_duration_is_two_seconds_plus_half_a_second_per_slice():
    assert PieDonut().duration(PieDonut.Params.model_validate(BROWSERS)) == pytest.approx(3.5)


@pytest.mark.parametrize("slices", [
    [{"label": "A", "value": 1}],                                              # one slice
    [{"label": c, "value": 1} for c in "ABCDEFG"],                              # seven
    [{"label": "A", "value": 0}, {"label": "B", "value": 1}],                    # zero
    [{"label": "A", "value": -1}, {"label": "B", "value": 2}],                   # negative
    [{"label": "A", "value": float("nan")}, {"label": "B", "value": 1}],         # nan
    [{"label": "A", "value": float("inf")}, {"label": "B", "value": 1}],         # inf
])
def test_bad_slices_are_rejected(slices):
    with pytest.raises(ValidationError):
        PieDonut.Params.model_validate({"title": "t", "slices": slices})


def test_a_sliver_is_rejected_with_advice_to_merge_it():
    with pytest.raises(ValidationError, match="Other"):
        PieDonut.Params.model_validate({"title": "t", "slices": [{"label": "A", "value": 99}, {"label": "B", "value": 1}]})


def test_labels_must_differ():
    with pytest.raises(ValidationError, match="differ"):
        PieDonut.Params.model_validate({"title": "t", "slices": [{"label": "A", "value": 1}, {"label": "a", "value": 1}]})


def test_percentages_always_sum_to_exactly_100():
    for values in ([1, 1, 1], [65, 20, 15], [33.3, 33.3, 33.4], [1, 2, 3, 4, 5, 6], [0.5, 0.25, 0.25]):
        assert sum(PieDonut.percentages(values)) == 100


def test_percentages_use_largest_remainder_not_naive_rounding():
    assert PieDonut.percentages([1, 1, 1]) == [34, 33, 33]


def test_fallback_text_gives_every_slice_with_its_percent():
    text = PieDonut().fallback_text(PieDonut.Params.model_validate(BROWSERS))
    assert text.startswith("Browser share") and "Chrome: 65%" in text and "Other: 15%" in text


def test_center_is_ignored_text_not_an_error_on_a_plain_pie():
    PieDonut.Params.model_validate({**BROWSERS, "center": "x"})


def test_schema_is_json_serialisable():
    json.dumps(PieDonut.Params.model_json_schema())
