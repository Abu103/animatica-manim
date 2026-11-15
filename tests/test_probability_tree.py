import json

import pytest
from pydantic import ValidationError

from animatica.components.probability_tree import ProbabilityTree

COIN_TWICE = {
    "title": "Two coin flips",
    "branches": [
        {"label": "Heads", "p": 0.5, "children": [{"label": "Heads", "p": 0.5}, {"label": "Tails", "p": 0.5}]},
        {"label": "Tails", "p": 0.5, "children": [{"label": "Heads", "p": 0.5}, {"label": "Tails", "p": 0.5}]},
    ],
}


def test_valid_two_level_tree_and_default_root():
    p = ProbabilityTree.Params.model_validate(COIN_TWICE)
    assert p.root == "Start" and len(p.branches) == 2


def test_duration_is_two_seconds_plus_half_a_second_per_node():
    p = ProbabilityTree.Params.model_validate(COIN_TWICE)
    assert ProbabilityTree().duration(p) == pytest.approx(2.0 + 0.5 * 6)


def test_one_level_tree_is_valid():
    p = ProbabilityTree.Params.model_validate({"title": "t", "branches": [{"label": "A", "p": 0.3}, {"label": "B", "p": 0.7}]})
    assert ProbabilityTree().duration(p) == pytest.approx(3.0)


@pytest.mark.parametrize("bad", [
    [{"label": "A", "p": 0.5}, {"label": "B", "p": 0.4}],           # sums to 0.9
    [{"label": "A", "p": 1.2}],                                       # p > 1
    [{"label": "A", "p": 0.0}, {"label": "B", "p": 1.0}],            # p == 0
    [],                                                                # no branches
    [{"label": "A", "p": 0.25}] * 4 + [{"label": "B", "p": 0.0}],     # too many
])
def test_bad_top_level_branches_are_rejected(bad):
    with pytest.raises(ValidationError):
        ProbabilityTree.Params.model_validate({"title": "t", "branches": bad})


def test_children_must_sum_to_one_and_the_error_names_the_branch():
    bad = {"title": "t", "branches": [{"label": "Rain", "p": 1.0, "children": [{"label": "x", "p": 0.5}, {"label": "y", "p": 0.2}]}]}
    with pytest.raises(ValidationError, match="Rain"):
        ProbabilityTree.Params.model_validate(bad)


def test_float_rounding_is_tolerated():
    ProbabilityTree.Params.model_validate({"title": "t", "branches": [{"label": a, "p": 1 / 3} for a in "ABC"]})


def test_leaf_probabilities_multiply_along_the_path():
    p = ProbabilityTree.Params.model_validate({
        "title": "t",
        "branches": [{"label": "A", "p": 0.3, "children": [{"label": "x", "p": 0.5}, {"label": "y", "p": 0.5}]},
                     {"label": "B", "p": 0.7}],
    })
    leaves = ProbabilityTree.leaves(p)
    assert [(path, round(prob, 6)) for path, prob in leaves] == [("A, x", 0.15), ("A, y", 0.15), ("B", 0.7)]
    assert sum(prob for _, prob in leaves) == pytest.approx(1.0)


def test_fallback_text_lists_every_outcome_with_its_probability():
    text = ProbabilityTree().fallback_text(ProbabilityTree.Params.model_validate(COIN_TWICE))
    assert text.startswith("Two coin flips") and text.count("0.25") == 4


def test_schema_is_json_serialisable_for_the_model_prompt():
    json.dumps(ProbabilityTree.Params.model_json_schema())


def test_label_length_is_capped_so_it_fits_a_node():
    with pytest.raises(ValidationError):
        ProbabilityTree.Params.model_validate({"title": "t", "branches": [{"label": "x" * 41, "p": 1.0}]})
