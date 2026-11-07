"""A searchable drop-down for the TUI: pick a value, or type to filter it.

Textual's built-in ``Select`` needs arrow keys through a long list. This widget
behaves the way people expect an ``npx``-style prompt to behave: focus it, start
typing, the list narrows to what matches, Enter takes the highlighted entry.

It is deliberately small and self-contained so the studio can use it for every
closed set of choices (quality, theme, provider, orientation) and tests can
drive it without a terminal.
"""
from __future__ import annotations

from typing import Iterable, Sequence

from textual.app import ComposeResult
from textual.containers import Container
from textual.message import Message
from textual.widgets import Input, OptionList

#: How many matches stay visible at once.
MAX_VISIBLE = 6


def matches(query: str, label: str, value: str = "") -> bool:
    """True when *query* plausibly matches the choice.

    Substring first (what people expect), then a subsequence fallback so that
    "hipc" still finds "High Contrast" and "or" finds "OpenRouter".
    """
    if not query:
        return True
    q = query.strip().lower()
    haystacks = (label.lower(), value.lower())
    if any(q in h for h in haystacks):
        return True
    for hay in haystacks:
        it = iter(hay)
        if all(ch in it for ch in q):
            return True
    return False


def filter_options(
    options: Sequence[tuple[str, str]], query: str
) -> list[tuple[str, str]]:
    """Options matching *query*, in their original order."""
    return [(label, value) for label, value in options if matches(query, label, value)]


class _SearchInput(Input):
    """Input that reports focus changes to its picker (focus events do not bubble)."""

    def on_focus(self) -> None:
        parent = self.parent
        if isinstance(parent, FilterSelect):
            parent._open(self.value)

    def on_blur(self) -> None:
        parent = self.parent
        if isinstance(parent, FilterSelect):
            parent._close()


class FilterSelect(Container):
    """``Input`` + filtered ``OptionList``; ``value`` holds the chosen option."""

    # The inner Input takes focus, so typing filters without an extra click.
    can_focus = False

    DEFAULT_CSS = """
    FilterSelect { height: auto; }
    FilterSelect > #fs-list { display: none; max-height: 8; border: round $accent; }
    FilterSelect.open > #fs-list { display: block; }
    """

    class Changed(Message):
        """Posted when the user commits a different value."""

        def __init__(self, filter_select: "FilterSelect", value: str) -> None:
            super().__init__()
            self.filter_select = filter_select
            self.value = value

        @property
        def control(self) -> "FilterSelect":
            return self.filter_select

    def __init__(
        self,
        options: Iterable[tuple[str, str]] = (),
        value: str | None = None,
        *,
        id: str | None = None,
        classes: str | None = None,
        placeholder: str = "type to filter",
    ) -> None:
        super().__init__(id=id, classes=classes)
        self._options: list[tuple[str, str]] = list(options)
        self._value: str | None = value
        self._filtered: list[tuple[str, str]] = list(self._options)
        self._placeholder = placeholder
        # Input.Changed is queued, so programmatic edits are counted: the matching
        # event must not re-open the list we just closed.
        self._ignore_changes = 0

    # -- public API -------------------------------------------------------

    @property
    def value(self) -> str | None:
        return self._value

    @value.setter
    def value(self, new: str | None) -> None:
        self._value = new
        self._refresh_label()

    def label_for(self, value: str | None) -> str:
        for label, candidate in self._options:
            if candidate == value:
                return label
        return ""

    def set_options(self, options: Iterable[tuple[str, str]], value: str | None = None) -> None:
        self._options = list(options)
        self._value = value if value is not None else self._value
        self._filtered = list(self._options)
        self._refresh_label()
        self._render_list()

    # -- layout -----------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield _SearchInput(placeholder=self._placeholder, id="fs-input")
        yield OptionList(id="fs-list")

    def on_mount(self) -> None:
        # the list is driven by the input's arrows, never focused itself
        self._list().can_focus = False
        self._refresh_label()
        self._render_list()

    # -- internals --------------------------------------------------------

    def _input(self) -> Input:
        return self.query_one("#fs-input", Input)

    def _list(self) -> OptionList:
        return self.query_one("#fs-list", OptionList)

    def _refresh_label(self) -> None:
        label = self.label_for(self._value)
        try:
            box = self._input()
        except Exception:  # not mounted yet
            return
        box.placeholder = f"{label}  ·  {self._placeholder}" if label else self._placeholder
        if box.value:
            self._ignore_changes += 1
            box.value = ""

    def _render_list(self) -> None:
        try:
            options = self._list()
        except Exception:  # not mounted yet
            return
        options.clear_options()
        options.add_options([label for label, _ in self._filtered[:MAX_VISIBLE]])
        if self._filtered:
            current = next(
                (i for i, (_, v) in enumerate(self._filtered[:MAX_VISIBLE]) if v == self._value), 0
            )
            options.highlighted = current

    def _open(self, query: str = "") -> None:
        self._filtered = filter_options(self._options, query)
        self._render_list()
        self.add_class("open")

    def _close(self) -> None:
        self.remove_class("open")
        self._filtered = list(self._options)

    def _commit(self, index: int | None) -> None:
        if index is None or not (0 <= index < len(self._filtered[:MAX_VISIBLE])):
            return
        chosen = self._filtered[:MAX_VISIBLE][index][1]
        changed = chosen != self._value
        self._value = chosen
        self._refresh_label()
        self._close()
        if changed:
            self.post_message(self.Changed(self, chosen))

    def _move(self, delta: int) -> None:
        visible = self._list()
        if not self._filtered:
            return
        count = min(len(self._filtered), MAX_VISIBLE)
        current = visible.highlighted if visible.highlighted is not None else 0
        visible.highlighted = max(0, min(count - 1, current + delta))

    # -- events -----------------------------------------------------------

    def on_input_changed(self, event: Input.Changed) -> None:
        if self._ignore_changes:
            self._ignore_changes -= 1
            return
        self._open(event.value)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        event.stop()
        self._commit(self._list().highlighted)

    def on_click(self, event: object) -> None:
        self._input().focus()
        self._open(self._input().value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        event.stop()
        self._commit(event.option_index)

    def on_key(self, event: object) -> None:
        key = getattr(event, "key", "")
        if not self.has_class("open"):
            return
        if key == "down":
            event.stop()
            self._move(1)
        elif key == "up":
            event.stop()
            self._move(-1)
        elif key == "escape":
            event.stop()
            self._close()
            self._refresh_label()
        elif key in ("tab",):
            self._close()
