"""Pure-Python function sampler. Same signature a future Rust `animatica_native` must provide."""
from __future__ import annotations

import math
from collections.abc import Callable

Point = tuple[float, float]
HUGE = 1e9  # |y| beyond this is treated as a singularity, never drawn


def sample_function(
    fn: Callable[[float], float],
    x_range: tuple[float, float],
    n: int,
    y_range: tuple[float, float] | None = None,
) -> list[list[Point]]:
    """Sample `fn` at `n` evenly spaced x values and return continuous segments.

    Non-finite results (NaN, inf, exceptions, |y| > 1e9) are dropped and split the curve.
    A jump larger than half the y span between neighbours also splits it (tan, 1/x at 0).
    The y span is `y_range` if given, otherwise the spread of the finite samples.
    Segments with fewer than two points are discarded.
    """
    lo, hi = float(x_range[0]), float(x_range[1])
    n = max(2, int(n))
    xs = [lo + (hi - lo) * i / (n - 1) for i in range(n)]
    xs[-1] = hi

    samples: list[tuple[float, float | None]] = []
    for x in xs:
        try:
            y = float(fn(x))
        except (ArithmeticError, ValueError, TypeError):
            y = math.nan
        samples.append((x, y if math.isfinite(y) and abs(y) <= HUGE else None))

    finite = [y for _, y in samples if y is not None]
    if not finite:
        return []
    span = (y_range[1] - y_range[0]) if y_range else (max(finite) - min(finite))
    jump = 0.5 * (span if span > 0 else 1.0)

    segments: list[list[Point]] = []
    cur: list[Point] = []

    def close() -> None:
        nonlocal cur
        if len(cur) >= 2:
            segments.append(cur)
        cur = []

    for x, y in samples:
        if y is None:
            close()
            continue
        if cur and abs(y - cur[-1][1]) > jump:
            close()
        cur.append((x, y))
    close()
    return segments

