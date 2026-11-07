"""One-line terminal progress for the CLI.

No third-party dependency (the project only depends on typer) and no invented
numbers: the bar shows the same :class:`~animatica.progress.ProgressEvent` units
the TUI uses, and stays at ``--%`` until the amount of work is actually known.

Behaviour depends on the stream:

* **Interactive (TTY)** — a single line rewritten in place, with a background
  ticker so the elapsed clock keeps moving between events. The ticker only
  redraws; it never advances ``done``.
* **Redirected (not a TTY)** — one plain line per new stage label, so build logs
  stay readable and greppable.
"""
from __future__ import annotations

import shutil
import sys
import threading
import time
from typing import TextIO

from animatica.progress import ProgressEvent

BAR_CELLS = 20
"""Width of the bar itself, in terminal cells."""

FILLED = "█"
EMPTY = "░"


def format_progress_line(
    event: ProgressEvent,
    *,
    elapsed: float | None = None,
    cells: int = BAR_CELLS,
) -> str:
    """Render one progress line. Pure, deterministic, no escape codes."""
    if event.total > 0:
        done = max(0, min(event.done, event.total))
        filled = int(round(cells * done / event.total))
        bar = FILLED * filled + EMPTY * (cells - filled)
        percent = f"{100 * done // event.total:3d}%"
    else:
        # how much work? unknown. Say so instead of guessing.
        bar = EMPTY * cells
        percent = " --%"
    line = f"[{bar}] {percent}  {event.label}"
    if elapsed is not None:
        line += f" · {elapsed:.0f}s"
    return line


class TerminalProgress:
    """Callable progress reporter for :func:`animatica.pipeline.make_video`."""

    def __init__(
        self,
        stream: TextIO | None = None,
        *,
        enabled: bool | None = None,
        cells: int = BAR_CELLS,
        min_interval: float = 0.08,
        tick: float = 0.5,
    ) -> None:
        self.stream = stream if stream is not None else sys.stderr
        self.enabled = (
            enabled
            if enabled is not None
            else bool(getattr(self.stream, "isatty", lambda: False)())
        )
        self.cells = cells
        self.min_interval = min_interval
        self.tick = tick
        self._lock = threading.Lock()
        self._last: ProgressEvent | None = None
        self._start = time.monotonic()
        self._last_draw = 0.0
        self._logged: set[str] = set()
        self._stop: threading.Event | None = None
        self._closed = False

    # -- lifecycle -------------------------------------------------------

    def start(self) -> "TerminalProgress":
        if self.enabled and self.tick > 0 and self._stop is None:
            self._stop = threading.Event()
            thread = threading.Thread(target=self._tick_loop, name="progress-tick", daemon=True)
            thread.start()
        return self

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._stop is not None:
            self._stop.set()
        if self.enabled:
            self._write("\n")

    def __enter__(self) -> "TerminalProgress":
        return self.start()

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    # -- reporting -------------------------------------------------------

    def __call__(self, event: ProgressEvent) -> None:
        self.handle(event)

    def handle(self, event: ProgressEvent) -> None:
        with self._lock:
            self._last = event
        if not self.enabled:
            if event.label not in self._logged:
                self._logged.add(event.label)
                self._write_plain(event.label)
            if event.finished:
                self.close()
            return
        self._draw(force=event.finished)
        if event.finished:
            self.close()

    # -- internals -------------------------------------------------------

    def _tick_loop(self) -> None:
        assert self._stop is not None
        while not self._stop.wait(self.tick):
            if self._closed:
                return
            self._draw()

    def _draw(self, *, force: bool = False) -> None:
        with self._lock:
            event = self._last
            if event is None or self._closed:
                return
            now = time.monotonic()
            if not force and now - self._last_draw < self.min_interval:
                return
            self._last_draw = now
            line = format_progress_line(
                event, elapsed=now - self._start, cells=self.cells
            )
        self._write("\r\x1b[K" + self._elide(line))

    def _elide(self, line: str) -> str:
        width = shutil.get_terminal_size((100, 24)).columns
        if width <= 0 or len(line) < width:
            return line
        return line[: max(0, width - 1)] + "…"

    def _write(self, text: str) -> None:
        try:
            self.stream.write(text)
            self.stream.flush()
        except (ValueError, OSError):  # closed/broken stream: never crash a render
            pass

    def _write_plain(self, label: str) -> None:
        self._write(f"animatica: {label}\n")
