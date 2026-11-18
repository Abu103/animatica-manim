"""P4: the signal_spectrum time axis label cannot touch the drawn curve."""
from animatica.components.signal_spectrum import SignalSpectrum, _data, _time_panel
from animatica.components.theme import PALETTES


def test_time_label_is_below_the_curves_full_extent():
    params = SignalSpectrum.Params.model_validate({
        "title": "Two tones",
        "waves": [{"freq": 2, "amp": 1.0}, {"freq": 5, "amp": 0.5}],
        "show": "both",
    })
    _panel, curve, static = _time_panel(_data(params), PALETTES["dark-blue"])
    axis, label = static
    assert label.get_top()[1] <= curve.get_bottom()[1], (
        f"label top {label.get_top()[1]} overlaps curve bottom {curve.get_bottom()[1]}"
    )
    # The label still belongs to the time panel and stays next to its axis.
    assert abs(label.get_center()[0] - axis.get_right()[0]) < label.width
