"""Tests for the frame-lint module.

Uses synthetic numpy frames and an injectable ``decode`` callback so no real
video rendering or system packages are required.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from unittest.mock import MagicMock

import av
import numpy as np
import pytest

from animatica.frame_lint import (
    FrameLintConfig,
    FrameFinding,
    FrameLintResult,
    _bbox,
    _background_luma,
    _contrast_ratio,
    _grayscale,
    _linearize_channel,
    _margin_band_mask,
    _nonbg_mask,
    _relative_luminance,
    lint_result_to_warnings,
    lint_video,
)


# ---------------------------------------------------------------------------
# B4b: small content is judged per beat, and the caption is not content
# ---------------------------------------------------------------------------

CONFORMANCE_DIR = Path(__file__).resolve().parent / "conformance"


def _write_storyboard(path: Path, beats: list[dict]) -> Path:
    """Write a one-scene storyboard with the given beats."""
    path.write_text(
        json.dumps({"version": "1", "title": "T", "scenes": [{"beats": beats}]}),
        encoding="utf-8",
    )
    return path


@pytest.mark.render
def test_a_beat_that_shows_nothing_is_still_small_content(tmp_path):
    """A storyboard whose component shows nothing must still be reported.

    The burned-in caption is not content: a beat that only ever shows the
    caption is a beat that shows nothing.
    """
    from animatica.pipeline import make_video

    sb = _write_storyboard(
        tmp_path / "sb.json",
        [{"component": "title_card", "params": {"title": " "}, "caption": "Only a caption."}],
    )
    result = make_video(None, storyboard_path=sb, out_dir=tmp_path / "out", preview=True)

    assert not any(w.startswith("title_card:") for w in result.warnings), result.warnings
    assert any("small_content" in w for w in result.warnings), result.warnings


@pytest.mark.render
@pytest.mark.parametrize("name", ["compare", "timeline", "two_scene"])
def test_a_beat_that_fades_in_is_not_small_content(tmp_path, name):
    """A beat is judged on what it showed, not on its first frame.

    In the first frame of a beat only the caption is on screen; the
    content fades in after it. Judging the beat on that frame reported
    every storyboard as having almost no content.
    """
    from animatica.pipeline import make_video

    result = make_video(
        None,
        storyboard_path=CONFORMANCE_DIR / f"{name}.json",
        out_dir=tmp_path / name,
        preview=True,
    )

    assert not any("small_content" in w for w in result.warnings), result.warnings


# ---------------------------------------------------------------------------
# Helper: build a synthetic video container for lint_video
# ---------------------------------------------------------------------------

class _FakeFrame:
    """Minimal stand-in for av.video.frame.VideoFrame."""

    def __init__(self, rgb: np.ndarray, time: float):
        self._rgb = rgb
        self.time = time

    def to_ndarray(self, format: str = "rgb24") -> np.ndarray:
        assert format == "rgb24"
        return self._rgb


class _FakeStream:
    def __init__(self, width: int, height: int, duration: float, time_base=1 / 1000):
        self.type = "video"
        self.width = width
        self.height = height
        self.duration = int(duration / time_base)
        self.time_base = time_base
        self.average_rate = 30


class _FakeContainer:
    def __init__(self, frames: list[tuple[np.ndarray, float]], width: int, height: int, duration: float):
        self.frames = [(_FakeFrame(rgb, t), t) for rgb, t in frames]
        self.streams = [_FakeStream(width, height, duration)]

    def decode(self, stream):
        for f, _ in self.frames:
            yield f

    def close(self):
        pass


def _make_container(frames, width=160, height=120, duration=5.0):
    return _FakeContainer(frames, width, height, duration)


def _solid_frame(rgb, width=160, height=120):
    return np.full((height, width, 3), rgb, dtype=np.uint8)


# ---------------------------------------------------------------------------
# _grayscale
# ---------------------------------------------------------------------------

def test_grayscale_rec709():
    rgb = np.zeros((2, 2, 3), dtype=np.uint8)
    rgb[0, 0] = [255, 0, 0]    # red
    rgb[0, 1] = [0, 255, 0]    # green
    rgb[1, 0] = [0, 0, 255]    # blue
    rgb[1, 1] = [255, 255, 255]  # white
    gray = _grayscale(rgb)
    assert gray.shape == (2, 2)
    # Rec.709: R=0.2126*255=54.2, G=0.7152*255=182.4, B=0.0722*255=18.4
    assert abs(int(gray[0, 0]) - 54) <= 1
    assert abs(int(gray[0, 1]) - 182) <= 1
    assert abs(int(gray[1, 0]) - 18) <= 1
    assert abs(int(gray[1, 1]) - 255) <= 1


# ---------------------------------------------------------------------------
# _background_luma
# ---------------------------------------------------------------------------

def test_background_luma_mode():
    gray = np.full((10, 10), 40, dtype=np.uint8)
    gray[0, 0] = 200  # outlier
    assert _background_luma(gray) == 40


# ---------------------------------------------------------------------------
# _nonbg_mask
# ---------------------------------------------------------------------------

def test_nonbg_mask_detects_foreground():
    gray = np.full((5, 5), 100, dtype=np.uint8)
    gray[2, 2] = 200  # differs by 100 > BG_DIFF(25)
    mask = _nonbg_mask(gray, 100)
    assert bool(mask[2, 2])
    assert not bool(mask[0, 0])


def test_nonbg_mask_tolerance():
    gray = np.full((5, 5), 100, dtype=np.uint8)
    gray[2, 2] = 120  # differs by 20 < BG_DIFF(25)
    mask = _nonbg_mask(gray, 100)
    assert not bool(mask[2, 2])


# ---------------------------------------------------------------------------
# _bbox
# ---------------------------------------------------------------------------

def test_bbox_rectangle():
    mask = np.zeros((10, 10), dtype=bool)
    mask[2:7, 3:6] = True
    assert _bbox(mask) == (2, 3, 7, 6)


def test_bbox_none():
    assert _bbox(np.zeros((5, 5), dtype=bool)) is None


# ---------------------------------------------------------------------------
# _linearize_channel / _relative_luminance / _contrast_ratio
# ---------------------------------------------------------------------------

def test_linearize_channel_known_values():
    # sRGB 0.0 -> linear 0.0
    assert _linearize_channel(np.array([0], dtype=np.uint8))[0] == 0.0
    # sRGB 255 -> linear 1.0
    assert abs(_linearize_channel(np.array([255], dtype=np.uint8))[0] - 1.0) < 1e-6
    # sRGB 10/255 = 0.0392 < 0.03928 threshold -> linear = c/12.92
    c = 10 / 255.0
    expected = c / 12.92
    assert abs(_linearize_channel(np.array([10], dtype=np.uint8))[0] - expected) < 1e-6


def test_relative_luminance_known():
    # Pure white: 0.2126 + 0.7152 + 0.0722 = 1.0
    white = np.full((1, 1, 3), 255, dtype=np.uint8)
    assert abs(_relative_luminance(white)[0, 0] - 1.0) < 1e-6
    # Pure black: 0.0
    black = np.full((1, 1, 3), 0, dtype=np.uint8)
    assert _relative_luminance(black)[0, 0] == 0.0


def test_contrast_ratio_black_white():
    ratio = _contrast_ratio(1.0, 0.0)
    # (1 + 0.05) / (0 + 0.05) = 21.0
    assert abs(ratio - 21.0) < 1e-6


def test_contrast_ratio_same():
    ratio = _contrast_ratio(0.5, 0.5)
    assert abs(ratio - 1.0) < 1e-6


def test_contrast_ratio_wcag_example():
    # White (1.0) vs gray at luminance 0.30 -> exactly 3.0:1
    # (1.0 + 0.05) / (0.30 + 0.05) = 1.05 / 0.35 = 3.0
    ratio = _contrast_ratio(1.0, 0.30)
    assert abs(ratio - 3.0) < 1e-6


# ---------------------------------------------------------------------------
# _margin_band_mask
# ---------------------------------------------------------------------------

def test_margin_band_mask():
    mask = np.zeros((10, 10), dtype=bool)
    mask[2, 5] = True   # inside (not in margin with margin=2)
    mask[0, 5] = True   # top margin
    mask[5, 0] = True   # left margin
    band = _margin_band_mask(mask, margin_y=2, margin_x=2)
    assert not bool(band[2, 5])   # not in margin band
    assert bool(band[0, 5])    # top margin
    assert bool(band[5, 0])    # left margin


# ---------------------------------------------------------------------------
# lint_video: empty frames
# ---------------------------------------------------------------------------

def test_lint_video_empty_frame():
    frames = [(_solid_frame([40, 40, 40]), 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, empty_threshold=0.005)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert any(f.kind == "empty" and f.severity == "warning" for f in result.findings)


def test_lint_video_non_empty_frame_no_warning():
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[60:80, 40:80] = [200, 200, 200]  # a bright square = content
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert not any(f.kind == "empty" for f in result.findings)


# ---------------------------------------------------------------------------
# lint_video: edge_contact vs clipped
# ---------------------------------------------------------------------------

def test_lint_video_edge_contact_warning_not_clipped():
    # A few pixels touching the top edge -> edge_contact (warning), not clipped (error)
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[0, 78:82] = [200, 200, 200]  # 4 pixels on top edge = 2.5% of width < 50%
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    edge_contact = [f for f in result.findings if f.kind == "edge_contact"]
    clipped = [f for f in result.findings if f.kind == "clipped"]
    assert len(edge_contact) == 1 and edge_contact[0].severity == "warning"
    assert len(clipped) == 0


def test_lint_video_clipped_error_substantial_edge():
    # A full-width line at top edge -> clipped (error)
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[0, :] = [200, 200, 200]  # 100% of top edge
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    clipped = [f for f in result.findings if f.kind == "clipped"]
    assert len(clipped) == 1 and clipped[0].severity == "error"


def test_lint_video_not_clipped():
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[10:20, 70:90] = [200, 200, 200]  # content well inside
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert not any(f.kind in ("clipped", "edge_contact") for f in result.findings)


# ---------------------------------------------------------------------------
# lint_video: safe-area violation
# ---------------------------------------------------------------------------

def test_lint_video_safe_area_violation():
    # 160x120, margin 5% => margin_y=6, margin_x=8
    # A horizontal line at row 3 (inside top margin of 6) across the frame
    # => 160 non-bg pixels (0.83% > 0.1% empty threshold), in the margin band.
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[3, :] = [200, 200, 200]
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, safe_area_margin=0.05)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert any(f.kind == "safe_area" and f.severity == "warning" for f in result.findings)


def test_lint_video_safe_area_ok():
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[20:30, 70:90] = [200, 200, 200]  # inside safe area
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, safe_area_margin=0.05)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert not any(f.kind == "safe_area" for f in result.findings)


# ---------------------------------------------------------------------------
# lint_video: safe-area dedup regression
# ---------------------------------------------------------------------------

def _safe_area_frames(margin_row: int, width: int = 160, height: int = 120):
    """A frame with a horizontal line at `margin_row` (inside top margin if margin_row < 6)."""
    rgb = _solid_frame([40, 40, 40], width, height)
    rgb[margin_row, :] = [200, 200, 200]
    return rgb


def test_lint_video_safe_area_dedup_within_interval():
    # Same safe_area kind repeated at timestamps within one sample_interval
    # must be deduplicated to a single finding.
    frame = _safe_area_frames(3)  # row 3 inside top margin (5% of 120 = 6)
    frames = [
        (frame, 0.0),
        (frame, 0.4),
        (frame, 0.7),
        (frame, 0.9),
    ]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, safe_area_margin=0.05)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    safe_area = [f for f in result.findings if f.kind == "safe_area"]
    assert len(safe_area) == 1, f"expected 1 deduped safe_area, got {len(safe_area)}: {[f.timestamp for f in safe_area]}"


def test_lint_video_safe_area_separate_outside_interval():
    # Two safe_area detections separated by more than one sample_interval must both appear.
    frame = _safe_area_frames(3)
    frames = [
        (frame, 0.0),
        (frame, 2.0),  # > 1.0s apart at sample_fps=1.0
    ]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, safe_area_margin=0.05)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    safe_area = [f for f in result.findings if f.kind == "safe_area"]
    assert len(safe_area) == 2, f"expected 2 safe_area findings, got {len(safe_area)}: {[f.timestamp for f in safe_area]}"


def test_lint_video_safe_area_legitimate_warning_still_appears():
    # Content inside the margin band must still produce a safe_area warning (not suppressed).
    frame = _safe_area_frames(3)  # row 3 inside top margin
    frames = [(frame, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, safe_area_margin=0.05)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    safe_area = [f for f in result.findings if f.kind == "safe_area"]
    assert len(safe_area) == 1
    assert safe_area[0].severity == "warning"
    assert "safe-area margin" in safe_area[0].detail


# ---------------------------------------------------------------------------
# lint_video: small content
# ---------------------------------------------------------------------------

def test_lint_video_small_content():
    # 10x10 dot = 100px (0.52% > 0.1% empty threshold), bbox = 100px = 0.52%
    # < 1% small-content threshold
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[50:60, 70:80] = [200, 200, 200]
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, small_content_threshold=0.01)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert any(f.kind == "small_content" and f.severity == "warning" for f in result.findings)


def test_lint_video_normal_content_not_small():
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[40:80, 60:100] = [200, 200, 200]  # 40x40 = 1600px = 8.3% > 1% threshold
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, small_content_threshold=0.01)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert not any(f.kind == "small_content" for f in result.findings)


# ---------------------------------------------------------------------------
# lint_video: low contrast
# ---------------------------------------------------------------------------

def test_lint_video_low_contrast():
    # bg=100, fg=130: diff=30 > BG_DIFF(25) so detected, but ratio ~1.24 < 3.0
    rgb = _solid_frame([100, 100, 100], 160, 120)
    rgb[40:80, 60:100] = [130, 130, 130]
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, low_contrast_threshold=3.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert any(f.kind == "low_contrast" and f.severity == "warning" for f in result.findings)


def test_lint_video_good_contrast():
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[40:80, 60:100] = [220, 220, 220]  # high contrast
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, low_contrast_threshold=3.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert not any(f.kind == "low_contrast" for f in result.findings)


# ---------------------------------------------------------------------------
# lint_video: blank interval
# ---------------------------------------------------------------------------

def test_lint_video_blank_interval():
    content = _solid_frame([40, 40, 40], 160, 120)
    content[40:80, 60:100] = [200, 200, 200]
    blank = _solid_frame([40, 40, 40], 160, 120)
    # content at 0s, blank until 2s, content at 2s => 2s blank interval > 0.5s threshold
    frames = [
        (content, 0.0),
        (blank, 0.5),
        (blank, 1.0),
        (blank, 1.5),
        (content, 2.0),
    ]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, blank_interval_seconds=0.5)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert any(f.kind == "blank_interval" for f in result.findings)


def test_lint_video_no_blank_interval():
    content = _solid_frame([40, 40, 40], 160, 120)
    content[40:80, 60:100] = [200, 200, 200]
    frames = [(content, 0.0), (content, 1.0), (content, 2.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0, blank_interval_seconds=0.5)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert not any(f.kind == "blank_interval" for f in result.findings)


# ---------------------------------------------------------------------------
# lint_video: scene mapping
# ---------------------------------------------------------------------------

def test_lint_video_scene_index_mapping():
    # scene 0: 0-2s, scene 1: 2-5s
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[0, :] = [200, 200, 200]  # clipped at 0s => scene 0
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [2.0, 3.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    clipped = [f for f in result.findings if f.kind == "clipped"]
    assert len(clipped) == 1
    assert clipped[0].scene_index == 0


# ---------------------------------------------------------------------------
# lint_video: disabled
# ---------------------------------------------------------------------------

def test_lint_video_disabled():
    rgb = _solid_frame([40, 40, 40], 160, 120)
    rgb[0, 80] = [200, 200, 200]
    frames = [(rgb, 0.0)]
    cfg = FrameLintConfig(enabled=False)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    assert result.findings == []


# ---------------------------------------------------------------------------
# lint_video: decode failure
# ---------------------------------------------------------------------------

def test_lint_video_decode_failure():
    def boom(path):
        raise OSError("no such file")

    cfg = FrameLintConfig(enabled=True)
    result = lint_video("missing.mp4", [5.0], cfg, decode=boom)
    assert any(f.kind == "decode" and f.severity == "error" for f in result.findings)


# ---------------------------------------------------------------------------
# lint_result_to_warnings
# ---------------------------------------------------------------------------

def test_lint_result_to_warnings():
    result = FrameLintResult()
    result.findings.append(
        FrameFinding(kind="empty", severity="warning", timestamp=1.5, scene_index=0,
                     detail="nearly empty", frame_index=0)
    )
    msgs = lint_result_to_warnings(result)
    assert len(msgs) == 1
    assert "empty" in msgs[0]
    assert "scene 0" in msgs[0]
    assert "1.5s" in msgs[0]


# ---------------------------------------------------------------------------
# lint_video: normal frame produces no false warnings
# ---------------------------------------------------------------------------

def test_lint_video_normal_frame_clean():
    # Well-formed frame: background + centered high-contrast content
    rgb = _solid_frame([30, 30, 30], 160, 120)
    rgb[40:80, 60:100] = [240, 240, 240]  # centered, high contrast, decent size
    frames = [(rgb, 0.0), (rgb, 1.0), (rgb, 2.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    kinds = {f.kind for f in result.findings}
    assert kinds == set(), f"unexpected findings: {result.as_messages()}"


# ---------------------------------------------------------------------------
# lint_video: sampling reduces analysis on long videos
# ---------------------------------------------------------------------------

def test_lint_video_sampling_skips_frames():
    # With sample_fps=1.0 and 10 content frames at 0..9s, findings should be
    # bounded by dedup (not one per frame).
    content = _solid_frame([40, 40, 40], 160, 120)
    content[40:80, 60:100] = [200, 200, 200]
    frames = [(content, float(i)) for i in range(10)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [10.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 10.0))
    low_contrast = [f for f in result.findings if f.kind == "low_contrast"]
    # With 10s duration and 1fps sampling + dedup, expect few findings
    assert len(low_contrast) <= 3, f"expected <=3 findings, got {len(low_contrast)}: {[f.timestamp for f in low_contrast]}"


def test_lint_video_low_sample_fps_reduces_findings():
    # sample_fps=0.1 -> one sample per 10s over 10s video -> ~1 sample
    content = _solid_frame([40, 40, 40], 160, 120)
    content[40:80, 60:100] = [200, 200, 200]
    frames = [(content, float(i)) for i in range(10)]
    cfg = FrameLintConfig(enabled=True, sample_fps=0.1)
    result = lint_video("fake.mp4", [10.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 10.0))
    assert len(result.findings) <= 3, f"expected <=3 findings with 0.1fps, got {len(result.findings)}"


# ---------------------------------------------------------------------------
# lint_video: empty-frame end-of-video suppression
# ---------------------------------------------------------------------------

def _empty_frame(width=160, height=120):
    return _solid_frame([40, 40, 40], width, height)


def test_lint_video_empty_during_fade_out_not_warned():
    """Empty frames in the last second (end fade) should NOT produce a warning."""
    content = _solid_frame([40, 40, 40], 160, 120)
    content[40:80, 60:100] = [200, 200, 200]
    blank = _empty_frame()
    # content until 3.5s, then blank from 3.5s to 5.0s (end of 5s video)
    # sample_fps=1.0 samples at 0,1,2,3,4; blank frame at 4s is
    # within the last second (>= 4.0s threshold) -> suppressed.
    # Blank at 3s is NOT in last second -> should warn.
    frames = [
        (content, 0.0),
        (content, 1.0),
        (content, 2.0),
        (blank, 3.0),   # blank but NOT in last second -> warned
        (blank, 4.0),   # blank in last second -> suppressed
    ]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    empty = [f for f in result.findings if f.kind == "empty"]
    assert len(empty) == 1, f"expected 1 empty warning at t=3s, got {len(empty)}: {[f.timestamp for f in empty]}"
    assert empty[0].timestamp == 3.0


def test_lint_video_empty_before_fade_out_still_warned():
    """Blank section that ends before the last second should still warn."""
    content = _solid_frame([40, 40, 40], 160, 120)
    content[40:80, 60:100] = [200, 200, 200]
    blank = _empty_frame()
    # content until 1.0s, blank from 1.0s to 2.5s, content again at 2.5s
    # blank at 1s and 2s are BEFORE the last second (threshold = 4.0s for 5s video)
    frames = [
        (content, 0.0),
        (blank, 1.0),   # blank before fade-out zone -> warned
        (blank, 2.0),   # blank before fade-out zone -> warned
        (content, 2.5), # content returns
        (content, 3.0),
        (content, 4.0),
    ]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [5.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 5.0))
    empty = [f for f in result.findings if f.kind == "empty"]
    assert len(empty) >= 1, f"expected >=1 empty warning for blank section before fade-out, got {len(empty)}"


def test_lint_video_genuinely_empty_video_warned():
    """A completely empty video should produce an empty warning."""
    blank = _empty_frame()
    frames = [(blank, 0.0), (blank, 1.0), (blank, 2.0)]
    cfg = FrameLintConfig(enabled=True, sample_fps=1.0)
    result = lint_video("fake.mp4", [3.0], cfg, decode=lambda p: _make_container(frames, 160, 120, 3.0))
    empty = [f for f in result.findings if f.kind == "empty"]
    assert len(empty) >= 1, f"expected >=1 empty warning for fully empty video, got {len(empty)}"
