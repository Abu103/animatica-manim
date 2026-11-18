"""Merge fixes F1/F2: sign-aware grounding and source-less number warnings."""
from animatica.components.registry import default_registry
from animatica.storyboard.models import Storyboard
from animatica.verify.numbers import check_numbers

REGISTRY = default_registry()


def _sb(component, params, caption, narration=""):
    return Storyboard.model_validate({
        "version": "1",
        "title": "T",
        "scenes": [{"beats": [{
            "component": component,
            "params": params,
            "caption": caption,
            "narration": narration,
        }]}],
    })


def test_negative_caption_number_grounds_in_signed_bar_value():
    sb = _sb("bar_chart",
             {"title": "Changes", "labels": ["A", "B"], "values": [-4, 6]},
             "A is -4 and B is 6")
    assert check_numbers(sb, REGISTRY) == []


def test_negative_caption_number_mismatch_is_a_finding():
    sb = _sb("bar_chart",
             {"title": "Changes", "labels": ["A", "B"], "values": [-4, 6]},
             "A is -5 and B is 6")
    findings = check_numbers(sb, REGISTRY)
    assert len(findings) == 1, findings
    assert "-5" in findings[0].message


def test_no_numeric_source_makes_a_number_a_warn():
    sb = _sb("title_card", {"title": "Intro"}, "Since 1903 we fly")
    findings = check_numbers(sb, REGISTRY)
    assert len(findings) == 1, findings
    assert findings[0].severity == "warn"
    assert "1903" in findings[0].message


def test_with_a_numeric_source_a_mismatch_is_still_an_error():
    sb = _sb("stat_callout", {"value": "12%", "label": "growth"}, "grew 40%")
    findings = check_numbers(sb, REGISTRY)
    assert len(findings) == 1, findings
    assert findings[0].severity == "error"
