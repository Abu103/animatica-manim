import pytest

from animatica.components.theme import MIN_FONT_PX, PALETTES, contrast_ratio, get_colors
from animatica.storyboard.models import Theme


def test_contrast_extremes():
    assert contrast_ratio("#000000", "#FFFFFF") == pytest.approx(21.0)
    assert contrast_ratio("#123456", "#123456") == pytest.approx(1.0)


def test_contrast_is_symmetric():
    assert contrast_ratio("#38BDF8", "#0B0B12") == pytest.approx(contrast_ratio("#0B0B12", "#38BDF8"))


def test_required_palettes_exist():
    assert {"dark-blue", "light", "high-contrast"} <= set(PALETTES)


@pytest.mark.parametrize("name", sorted(["dark-blue", "light", "high-contrast"]))
def test_palettes_meet_wcag_aa(name):
    c = PALETTES[name]
    for fg in (c.text, c.accent, c.accent2):
        assert contrast_ratio(fg, c.background) >= 4.5, (name, fg)


def test_get_colors():
    assert get_colors(Theme(palette="light")) == PALETTES["light"]


def test_unknown_palette_lists_valid():
    with pytest.raises(ValueError) as e:
        get_colors(Theme(palette="neon"))
    assert "dark-blue" in str(e.value)


def test_min_font():
    assert MIN_FONT_PX == 32

