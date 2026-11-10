"""The parallel render pool: many renders at once, without overloading the box.

The conformance corpus is seventeen storyboards and every one of them is a
python + manim + ffmpeg process tree. Rendering them one after another cost
more than two minutes; the pool renders them at the same time and keeps the
results in the order they were asked for.
"""
import os
import time

import pytest

from animatica.backends.scheduler import (
    available_memory_mb,
    render_workers,
    run_in_parallel,
)


def test_results_keep_the_order_of_the_items():
    """The gate prints its storyboards in a fixed order, so the pool must too."""
    def work(item: int) -> int:
        # The first item is the slowest: the order must not follow the finish.
        time.sleep(0.15 if item == 0 else 0.01)
        return item * 10

    assert run_in_parallel([0, 1, 2, 3], work, workers=4) == [0, 10, 20, 30]


def test_the_items_really_do_run_at_the_same_time():
    """Four renders that each take a quarter second must not take a second."""
    def work(item: int) -> int:
        time.sleep(0.25)
        return item

    started = time.monotonic()
    run_in_parallel([0, 1, 2, 3], work, workers=4)
    elapsed = time.monotonic() - started

    assert elapsed < 0.9, f"the renders did not overlap (took {elapsed:.2f}s)"


def test_a_failing_item_stops_the_pool():
    def work(item: int) -> int:
        if item == 2:
            raise RuntimeError("boom in item 2")
        return item

    with pytest.raises(RuntimeError) as exc:
        run_in_parallel([0, 1, 2, 3], work, workers=2)

    assert "boom in item 2" in str(exc.value)


def test_an_empty_list_is_fine():
    assert run_in_parallel([], lambda item: item) == []


def test_one_worker_runs_the_items_one_after_another():
    order: list[int] = []

    def work(item: int) -> int:
        order.append(item)
        return item

    assert run_in_parallel([0, 1, 2], work, workers=1) == [0, 1, 2]
    assert order == [0, 1, 2]


def test_the_worker_count_is_capped_by_the_cores(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 64)
    monkeypatch.delenv("ANIMATICA_RENDER_JOBS", raising=False)

    assert render_workers() <= 4


def test_the_worker_count_can_be_set_by_hand(monkeypatch):
    monkeypatch.setenv("ANIMATICA_RENDER_JOBS", "7")

    assert render_workers() == 7


def test_a_nonsense_override_falls_back_to_the_default(monkeypatch):
    monkeypatch.setenv("ANIMATICA_RENDER_JOBS", "many")

    assert 1 <= render_workers() <= 4


def test_the_worker_count_is_at_least_one(monkeypatch):
    monkeypatch.setattr(os, "cpu_count", lambda: 1)
    monkeypatch.delenv("ANIMATICA_RENDER_JOBS", raising=False)

    assert render_workers() >= 1


def test_the_free_memory_is_reported():
    """The pool needs to know how much memory is left, or it guesses."""
    free = available_memory_mb()

    if free is not None:
        assert free > 0
