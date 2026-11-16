import json
import math

import pytest
from pydantic import ValidationError

from animatica.components.unit_circle import UnitCircle


def params(**kw):
    return UnitCircle.Params.model_validate({"title": "Special angles", "angles": [30, 45, 60], **kw})


@pytest.mark.parametrize("deg,expected", [
    (0, ("1", "0")), (30, ("√3/2", "1/2")), (45, ("√2/2", "√2/2")), (60, ("1/2", "√3/2")), (90, ("0", "1")),
    (120, ("-1/2", "√3/2")), (135, ("-√2/2", "√2/2")), (150, ("-√3/2", "1/2")), (180, ("-1", "0")),
    (210, ("-√3/2", "-1/2")), (225, ("-√2/2", "-√2/2")), (240, ("-1/2", "-√3/2")), (270, ("0", "-1")),
    (300, ("1/2", "-√3/2")), (315, ("√2/2", "-√2/2")), (330, ("√3/2", "-1/2")),
])
def test_exact_cos_sin_for_every_allowed_angle(deg, expected):
    assert UnitCircle.exact_xy(deg) == expected


def test_exact_values_agree_with_the_numbers():
    val = {"1": 1, "0": 0, "1/2": 0.5, "√3/2": math.sqrt(3) / 2, "√2/2": math.sqrt(2) / 2}
    for deg in UnitCircle.ALLOWED:
        for s, f in zip(UnitCircle.exact_xy(deg), (math.cos, math.sin)):
            sign = -1 if s.startswith("-") else 1
            assert sign * val[s.lstrip("-")] == pytest.approx(f(math.radians(deg)), abs=1e-12)


@pytest.mark.parametrize("deg,label", [(0, "0"), (30, "π/6"), (45, "π/4"), (90, "π/2"), (120, "2π/3"),
                                       (180, "π"), (210, "7π/6"), (270, "3π/2"), (330, "11π/6")])
def test_radian_labels_are_reduced_fractions_of_pi(deg, label):
    assert UnitCircle.radians_label(deg) == label


def test_allowed_angles_are_multiples_of_30_or_45_below_360():
    assert UnitCircle.ALLOWED == (0, 30, 45, 60, 90, 120, 135, 150, 180, 210, 225, 240, 270, 300, 315, 330)


def test_defaults_degrees_and_duration_is_two_and_a_half_seconds_plus_0_9_per_angle():
    p = params()
    assert p.units == "degrees"
    assert UnitCircle().duration(p) == pytest.approx(2.5 + 0.9 * 3)


@pytest.mark.parametrize("angles", [[], [15], [30, 30], [0, 30, 45, 60, 90], [360], [-30], [31]])
def test_bad_angles_are_rejected(angles):
    with pytest.raises(ValidationError):
        params(angles=angles)


def test_units_must_be_known():
    with pytest.raises(ValidationError):
        params(units="gradians")


def test_fallback_text_gives_each_angle_with_its_point_in_the_chosen_units():
    assert UnitCircle().fallback_text(params(angles=[30, 120])).splitlines() == [
        "Special angles", "30°: (√3/2, 1/2)", "120°: (-1/2, √3/2)"]
    assert UnitCircle().fallback_text(params(angles=[30], units="radians")).splitlines()[1] == "π/6: (√3/2, 1/2)"


def test_schema_is_json_serialisable():
    json.dumps(UnitCircle.Params.model_json_schema())
