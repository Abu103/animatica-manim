"""The searchable picker behind the TUI's closed-choice fields."""
from __future__ import annotations

import pytest

from animatica.tui_picker import FilterSelect, filter_options, matches

CHOICES = [
    ("Preview 480p", "preview"),
    ("Standard 720p", "standard"),
    ("High 1080p", "high"),
]


def test_matches_is_case_insensitive_substring():
    assert matches("prev", "Preview 480p", "preview")
    assert matches("480", "Preview 480p", "preview")
    assert matches("PREVIEW", "Preview 480p", "preview")


def test_matches_falls_back_to_subsequence():
    # no contiguous "hp" in the label, but H…P appears in order
    assert matches("hg", "High 1080p", "high")
    assert not matches("zzz", "High 1080p", "high")


def test_matches_matches_on_value_too():
    assert matches("stand", "Standard 720p", "standard")


def test_empty_query_keeps_everything():
    assert filter_options(CHOICES, "") == CHOICES


def test_filter_keeps_original_order():
    got = filter_options(CHOICES, "80")
    labels = [label for label, _ in got]
    assert labels == ["Preview 480p", "High 1080p"]


def test_filter_can_match_nothing():
    assert filter_options(CHOICES, "qqqq") == []


# --------------------------------------------------------------------------- #
# widget behaviour, driven headlessly through a tiny app
# --------------------------------------------------------------------------- #

pytest.importorskip("textual")


def _app(options=CHOICES, value="preview"):
    from textual.app import App, ComposeResult

    from animatica.tui_picker import FilterSelect

    class PickerApp(App):
        def __init__(self) -> None:
            super().__init__()
            self.events: list[str] = []

        def compose(self) -> ComposeResult:
            yield FilterSelect(options, value, id="pick")

        def on_filter_select_changed(self, event: FilterSelect.Changed) -> None:
            self.events.append(event.value)

    return PickerApp()


async def test_picker_shows_the_current_choice():
    app = _app()
    async with app.run_test() as pilot:
        picker = app.query_one("#pick", FilterSelect)
        assert picker.value == "preview"
        assert picker.label_for("preview") == "Preview 480p"
        assert "Preview 480p" in picker._input().placeholder
        await pilot.pause()
        # focused on mount, so the choices are already visible
        assert picker.has_class("open")


async def test_typing_filters_the_visible_options():
    app = _app()
    async with app.run_test() as pilot:
        picker = app.query_one("#pick", FilterSelect)
        picker._input().focus()
        await pilot.pause()
        assert picker.has_class("open")
        await pilot.press("h", "i", "g")
        await pilot.pause()
        assert [label for label, _ in picker._filtered] == ["High 1080p"]


async def test_enter_takes_the_highlighted_match():
    app = _app()
    async with app.run_test() as pilot:
        picker = app.query_one("#pick", FilterSelect)
        picker._input().focus()
        await pilot.pause()
        await pilot.press("s", "t", "a")  # -> Standard 720p
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        assert picker.value == "standard"
        assert app.events == ["standard"]
        assert not picker.has_class("open")


async def test_arrow_keys_walk_the_matches():
    app = _app()
    async with app.run_test() as pilot:
        picker = app.query_one("#pick", FilterSelect)
        picker._input().focus()
        await pilot.pause()
        await pilot.press("down", "enter")
        await pilot.pause()
        assert picker.value == "standard"


async def test_escape_closes_without_changing_the_value():
    app = _app()
    async with app.run_test() as pilot:
        picker = app.query_one("#pick", FilterSelect)
        picker._input().focus()
        await pilot.pause()
        await pilot.press("h", "i", "g", "escape")
        await pilot.pause()
        assert picker.value == "preview"
        assert not picker.has_class("open")


async def test_setting_the_same_value_does_not_post_a_change():
    app = _app()
    async with app.run_test() as pilot:
        picker = app.query_one("#pick", FilterSelect)
        picker._input().focus()
        await pilot.pause()
        await pilot.press("enter")  # highlighted option is the current one
        await pilot.pause()
        assert picker.value == "preview"
        assert app.events == []
