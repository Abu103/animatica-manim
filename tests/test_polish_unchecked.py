"""P2: a checked number must not leave its sentence in the unchecked list."""
from pathlib import Path

from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard, load_storyboard
from animatica.verify import verify_storyboard
from animatica.verify.numbers import scan_numbers

FIXTURE = (Path(__file__).resolve().parent / "fixtures" / "verify"
           / "fourier_signal_spectrum_2026_11_18.json")


def test_grounded_numbers_are_not_listed_as_unchecked():
    sb = load_storyboard(FIXTURE)
    result = verify_storyboard(sb, default_registry())
    assert result.checked == 4
    assert result.by_severity["error"] == 0
    assert "The spectrum shows spikes at 2 and 5 hertz." not in result.unchecked
    assert "Key ideas to remember." in result.unchecked


def test_grounded_number_sentence_is_not_unchecked_without_a_claim_rule():
    # No claim rule looks at this sentence; numbers.py checks its 12%. It must
    # therefore not be listed as unchecked.
    sb = Storyboard.model_validate({
        "version": "1", "title": "T",
        "scenes": [{"beats": [{
            "component": "stat_callout",
            "params": {"value": "12%", "label": "growth"},
            "caption": "grew 12%",
        }]}],
    })
    result = verify_storyboard(sb, default_registry())
    assert result.checked == 1
    assert "grew 12%" not in result.unchecked


def test_scan_numbers_public_return_type_is_unchanged():
    sb = load_storyboard(FIXTURE)
    result = scan_numbers(sb, default_registry())
    assert isinstance(result, tuple) and len(result) == 2
