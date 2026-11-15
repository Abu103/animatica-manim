"""B4g: `999999` was drawn as the 'infinity' of a distance array (seen in a real out-2 render)."""
import math

import pytest

from animatica.components.array_viz import ArrayViz, value_label
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Storyboard


def _sb(values, caption="", title="Distances"):
    return Storyboard.model_validate({
        "title": "t",
        "scenes": [{"beats": [{"component": "array_viz", "caption": caption,
                               "params": {"title": title, "values": values, "steps": []}}]}],
    })


def test_labels():
    assert value_label(float("inf")) == "∞"
    assert value_label(float("-inf")) == "-∞"
    assert value_label(3.0) == "3"
    assert value_label(2.5) == "2.5"


def test_params_accept_inf_and_reject_nan():
    p = ArrayViz.Params.model_validate({"title": "d", "values": [0, "inf", 4]})
    assert math.isinf(p.values[1])
    assert ArrayViz().fallback_text(p) == "d: [0, ∞, 4]"
    with pytest.raises(ValueError, match="nan"):
        ArrayViz.Params.model_validate({"title": "d", "values": [0, "nan"]})


def test_lint_turns_a_sentinel_into_inf_when_the_caption_says_infinity():
    sb, notes = lint_storyboard(_sb([0, 999999, 999999], caption="Source at 0 and all others at infinity."))
    assert sb.scenes[0].beats[0].params["values"] == [0, "inf", "inf"]
    assert any("infinity" in n and "array_viz" in n for n in notes)


def test_lint_also_reads_the_title():
    sb, _ = lint_storyboard(_sb([0, 99999], title="Start: ∞ everywhere"))
    assert sb.scenes[0].beats[0].params["values"] == [0, "inf"]


def test_lint_leaves_real_numbers_alone():
    # No mention of infinity: 999999 is just a number here.
    sb, notes = lint_storyboard(_sb([0, 999999], caption="Final distances."))
    assert sb.scenes[0].beats[0].params["values"] == [0, 999999]
    assert not any("infinity" in n for n in notes)
    # Mentions infinity but the values are ordinary: nothing to rewrite.
    sb, _ = lint_storyboard(_sb([0, 4, 7], caption="No node is at infinity any more."))
    assert sb.scenes[0].beats[0].params["values"] == [0, 4, 7]


def test_the_linted_storyboard_survives_json_and_validates():
    sb, _ = lint_storyboard(_sb([0, 999999], caption="others at infinity"))
    again = Storyboard.model_validate_json(sb.model_dump_json())
    p = ArrayViz.Params.model_validate(again.scenes[0].beats[0].params)
    assert math.isinf(p.values[1])
