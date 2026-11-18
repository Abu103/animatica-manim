"""N4: the hertz warning covers kHz, MHz, kilohertz and megahertz too.

signal_spectrum axes are cycles per window, not hertz in any unit. The
warning is a warn (report only) and runs on signal_spectrum beats only.
"""
from __future__ import annotations

import pytest

from animatica.components.registry import default_registry
from animatica.storyboard.models import Beat, Scene, Storyboard
from animatica.verify.claims import check_claims, unchecked_sentences


def _sb(caption="", component="signal_spectrum", params=None):
    params = params if params is not None else {
        "title": "t", "waves": [{"freq": 3, "amp": 1.0}], "show": "both",
    }
    return Storyboard(title="t", scenes=[Scene(beats=[
        Beat(component=component, params=params, caption=caption)
    ])])


@pytest.mark.parametrize("word", ["Hz", "kHz", "MHz", "GHz", "kilohertz", "megahertz", "gigahertz", "hertz"])
def test_every_hertz_spelling_warns(word):
    findings = check_claims(_sb(caption=f"the peak sits at 3 {word}"), default_registry())
    assert len(findings) == 1
    assert findings[0].severity == "warn"
    assert word.lower() in findings[0].message.lower()
    assert "cycles per window" in findings[0].message


def test_hertz_warning_does_not_leak_to_other_components():
    graph = {"fn": "sin(x)", "x_range": [0, 6.28], "y_range": [-2, 2]}
    assert check_claims(_sb(caption="the peak sits at 3 kHz", component="graph",
                            params=graph), default_registry()) == []


def test_hertz_sentence_is_not_listed_as_unchecked():
    sb = _sb(caption="the peak sits at 3 kHz")
    assert not [s for _, s in unchecked_sentences(sb, default_registry())]
