"""P3: frame lint must not sample a beat's final fade-out window."""
from animatica.components._draw import FADE_OUT
from animatica.frame_lint import _sample_times


def test_sample_times_skip_each_beats_final_fade_out():
    duration = 8.7
    beats = [(0, 0.0, 4.2), (1, 4.2, 8.7)]
    fade_windows = [(max(start, end - FADE_OUT), end) for _, start, end in beats]

    times = _sample_times(duration, 2.0, beats)

    for t in times:
        assert all(not (lo <= t < hi) for lo, hi in fade_windows), (t, fade_windows)
    # 4.0 lies in [3.8, 4.2) and 8.5 lies in [8.3, 8.7): both are fade-out.
    assert 4.0 not in times
    assert 8.5 not in times
    assert 3.5 in times
    assert 4.5 in times


def test_sample_times_without_beats_are_uniform():
    assert _sample_times(1.0, 2.0, None) == [0.0, 0.5]
