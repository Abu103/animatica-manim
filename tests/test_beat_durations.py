"""T26b: a beat's duration extends to cover its narration, never shrinks for it.

docs/superpowers/specs/2026-11-14-narration-design.md section 3: the beat
holds its resting frame for the difference rather than speeding up either
side. ``_beat_durations`` takes an optional per-beat narration floor and
takes the max; with no narration (the default, ``--narrate`` not used) its
output is byte-for-byte what it always was.
"""
from __future__ import annotations

import wave

from animatica.components.registry import default_registry
from animatica.narration import wav_duration_seconds
from animatica.pipeline import _beat_durations
from animatica.storyboard.models import Beat, Scene, Storyboard


def _write_wav(path, seconds: float, rate: int = 22050) -> None:
    n_frames = int(seconds * rate)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x00" * n_frames)


def test_wav_duration_seconds_matches_frames_over_rate(tmp_path):
    wav = tmp_path / "beat.wav"
    _write_wav(wav, seconds=2.5, rate=22050)
    assert abs(wav_duration_seconds(wav) - 2.5) < 0.01


def test_wav_duration_seconds_handles_a_different_sample_rate(tmp_path):
    wav = tmp_path / "beat.wav"
    _write_wav(wav, seconds=1.0, rate=16000)
    assert abs(wav_duration_seconds(wav) - 1.0) < 0.01


def _sb(n_beats: int) -> Storyboard:
    return Storyboard(
        title="t",
        scenes=[
            Scene(beats=[Beat(component="title_card", params={"title": "hi"}, caption="hi") for _ in range(n_beats)])
        ],
    )


def test_beat_durations_unchanged_with_no_narration():
    registry = default_registry()
    sb = _sb(2)
    assert _beat_durations(sb, registry) == _beat_durations(sb, registry, narration_durations=None)


def test_beat_durations_takes_the_max_with_narration():
    registry = default_registry()
    sb = _sb(2)
    visual = _beat_durations(sb, registry)
    # Longer narration than the visual for beat 0, shorter for beat 1.
    narration_durations = [[visual[0][0] + 3.0, 0.01]]
    out = _beat_durations(sb, registry, narration_durations=narration_durations)
    assert out[0][0] == visual[0][0] + 3.0
    assert out[0][1] == visual[0][1]  # the shorter narration never shrinks the visual duration


def test_beat_durations_tolerates_a_narration_list_shorter_than_the_storyboard():
    """A beat with no corresponding narration entry (e.g. synthesis was skipped) keeps its visual duration."""
    registry = default_registry()
    sb = _sb(2)
    visual = _beat_durations(sb, registry)
    out = _beat_durations(sb, registry, narration_durations=[[]])
    assert out == visual
