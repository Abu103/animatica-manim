"""P1: signal_spectrum frequency wording is cycles per window, not hertz."""
from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard
from animatica.verify.claims import check_claims

REGISTRY = default_registry()


def _sb(component, params, caption):
    return Storyboard.model_validate({
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{
            "component": component, "params": params, "caption": caption,
        }]}],
    })


SPECTRUM = {
    "title": "Two tones",
    "waves": [{"freq": 2, "amp": 1.0}, {"freq": 5, "amp": 0.5}],
    "show": "both",
}


def test_hertz_on_signal_spectrum_is_one_warn():
    sb = _sb("signal_spectrum", SPECTRUM, "spikes at 2 and 5 hertz")
    findings = check_claims(sb, REGISTRY)
    assert len(findings) == 1, findings
    assert findings[0].severity == "warn"
    assert findings[0].message == (
        'says "hertz" but the signal_spectrum axis is cycles per window, not hertz'
    )


def test_cycles_per_window_is_not_flagged():
    sb = _sb("signal_spectrum", SPECTRUM, "spikes at 2 and 5 cycles per window")
    assert check_claims(sb, REGISTRY) == []


def test_hertz_on_title_card_is_not_flagged():
    sb = _sb("title_card", {"title": "Intro"}, "hertz")
    assert check_claims(sb, REGISTRY) == []
