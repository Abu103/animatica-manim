"""Honest progress reporting for the ``animatica make`` pipeline.

A render is a sequence of *discrete, observable* units: one per scene, then one
per post-processing step (transcode, frame lint, captions + report). This module
counts those units and nothing else.

Deliberate limits:

* No time estimates. ``done / total`` is what has actually finished.
* ``total == 0`` means "not known yet" (storyboard generation, an opaque
  renderer). Callers show an indeterminate bar for that, not a fake percentage.
* The tracker never invents a unit: a backend that cannot see inside its own
  renderer reports one coarse unit rather than a smooth lie.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class ProgressEvent:
    """One observable step of a make run."""

    stage: str
    """Machine-ish stage id: ``storyboard``, ``render``, ``transcode``, ``lint``, ``captions``."""

    label: str
    """One human line for a status bar, e.g. ``"scene 3/5 rendered"``."""

    done: int
    """Units finished."""

    total: int
    """Units expected, or ``0`` while the amount of work is still unknown."""

    finished: bool = False
    """True for the final event of a successful run."""


ProgressFn = Callable[[ProgressEvent], None]
"""Receives every :class:`ProgressEvent`."""

BackendProgressFn = Callable[[str, int, int], None]
"""What a render backend gets: ``(label, done, total)`` on its own unit scale."""


class ProgressTracker:
    """Turns backend-local units into whole-run :class:`ProgressEvent` objects.

    The first caller to declare a scale (the render backend, via
    :meth:`backend`) fixes the total: its units plus ``post_units`` for the
    steps the pipeline runs afterwards. Later :meth:`advance` calls count those
    post-processing units.
    """

    def __init__(self, emit: ProgressFn | None, *, post_units: int = 1) -> None:
        self._emit = emit
        self._post_units = max(0, post_units)
        self._done = 0
        self._total = 0
        self._finished = False

    # -- state -----------------------------------------------------------

    @property
    def done(self) -> int:
        return self._done

    @property
    def total(self) -> int:
        return self._total

    @property
    def finished(self) -> bool:
        return self._finished

    # -- events ----------------------------------------------------------

    def announce(self, stage: str, label: str) -> None:
        """Report work that has started but whose size is not known yet."""
        self._send(stage, label)

    def backend(self, label: str, done: int, total: int) -> None:
        """Called by a render backend with its own unit scale."""
        done = max(0, done)
        total = max(0, total)
        if total:
            self._total = total + self._post_units
            self._done = min(done, total)
        self._send("render", label)

    def advance(self, stage: str, label: str) -> None:
        """Count one finished post-processing unit."""
        self._done += 1
        if self._total:
            self._done = min(self._done, self._total)
        self._send(stage, label)

    def finish(self, label: str = "done") -> None:
        if self._finished:
            return
        self._finished = True
        if self._total:
            self._done = self._total
        else:  # nothing declared a scale: report what we know, not a guess
            self._total = self._done
        self._send("done", label, finished=True)

    # -- internals -------------------------------------------------------

    def _send(self, stage: str, label: str, *, finished: bool = False) -> None:
        if self._emit is None:
            return
        self._emit(
            ProgressEvent(
                stage=stage,
                label=label,
                done=self._done,
                total=self._total,
                finished=finished,
            )
        )
