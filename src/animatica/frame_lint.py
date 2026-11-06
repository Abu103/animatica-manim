"""Deterministic frame-level quality checks for rendered Animatica videos.

Decodes a video with PyAV, samples frames at ``sample_fps``, and runs
numpy-based image analysis to detect: empty frames, content at/over
safe-area boundaries, clipped content, extremely small content, low
contrast, and blank intervals.

No LLM or external vision API is used. All checks are heuristic: definite
failures are reported as errors, everything else as warnings. Frame lint
is deliberately non-fatal: it never aborts a successful render.

Background estimation uses the modal grayscale value. It is reliable on
solid or near-solid backgrounds (the common case for manim scenes) but
unreliable on gradients, textured backgrounds, or scenes where foreground
occupies most of the frame. Contrast and safe-area checks are skipped when
the background estimate is unreliable (foreground > 50% of pixels).

Thresholds are configurable through :class:`FrameLintConfig`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import av
import numpy as np

__all__ = [
    "FrameLintConfig",
    "FrameFinding",
    "FrameLintResult",
    "lint_video",
    "lint_result_to_warnings",
]

# A pixel is "different from background" when its luminance differs by this much.
_BG_DIFF = 25

# If more than this fraction of pixels are non-background, the modal background
# estimate is unreliable (foreground likely dominates) and contrast/safe-area
# checks are skipped for that frame.
_FOREGROUND_DOMINANCE_LIMIT = 0.5

# Fraction of an edge dimension that must be non-background for "clipped"
# (error) vs "edge_contact" (warning). A single pixel at the edge is not
# evidence of clipping; a substantial run of edge pixels is.
_CLIPPED_EDGE_FRACTION = 0.5


@dataclass(frozen=True)
class FrameLintConfig:
    """Thresholds for frame-level quality checks. All values are tunable."""

    enabled: bool = False
    sample_fps: float = 1.0  # analyzed frames per second (true sampling)
    empty_threshold: float = 0.001  # min non-bg pixel fraction to not be "empty"
    safe_area_margin: float = 0.05  # fraction of frame dimension from each edge
    small_content_threshold: float = 0.01  # max bbox area fraction to be "tiny"
    low_contrast_threshold: float = 3.0  # WCAG contrast-ratio floor
    blank_interval_seconds: float = 0.5  # max blank seconds between content frames
    clipped_edge_fraction: float = _CLIPPED_EDGE_FRACTION  # edge coverage for "clipped"


@dataclass(frozen=True)
class FrameFinding:
    """A single frame-lint result."""

    kind: str  # empty | edge_contact | clipped | safe_area | small_content | low_contrast | blank_interval | decode | analysis
    severity: str  # "error" or "warning"
    timestamp: float
    scene_index: int | None
    detail: str
    frame_index: int


@dataclass
class FrameLintResult:
    findings: list[FrameFinding] = field(default_factory=list)

    @property
    def errors(self) -> list[FrameFinding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def warnings(self) -> list[FrameFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    def as_messages(self, prefix: str = "frame-lint") -> list[str]:
        msgs: list[str] = []
        for f in self.findings:
            scene = f"scene {f.scene_index}" if f.scene_index is not None else "unknown"
            msgs.append(
                f"[{prefix}] [{f.severity}] {f.kind} at {f.timestamp:.1f}s ({scene}): {f.detail}"
            )
        return msgs


# ---------------------------------------------------------------- color

def _linearize_channel(channel: np.ndarray) -> np.ndarray:
    """sRGB -> linear light for one 0..255 channel (vectorized)."""
    c = channel.astype(np.float64) / 255.0
    return np.where(c <= 0.03928, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _relative_luminance(rgb: np.ndarray) -> np.ndarray:
    """Per-pixel relative luminance per WCAG (linearized sRGB)."""
    r = _linearize_channel(rgb[..., 0])
    g = _linearize_channel(rgb[..., 1])
    b = _linearize_channel(rgb[..., 2])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _contrast_ratio(lum1: float, lum2: float) -> float:
    """WCAG contrast ratio between two relative luminances (0..1)."""
    hi, lo = max(lum1, lum2), min(lum1, lum2)
    return (hi + 0.05) / (lo + 0.05)


# ---------------------------------------------------------------- grayscale / mask

def _grayscale(rgb: np.ndarray) -> np.ndarray:
    """Rec. 709 grayscale (uint8) used for background/mask estimation."""
    return (rgb.astype(np.float64) @ np.array([0.2126, 0.7152, 0.0722])).astype(np.uint8)


def _background_luma(gray: np.ndarray) -> int:
    """Estimate background luminance as the modal grayscale value."""
    values, counts = np.unique(gray, return_counts=True)
    return int(values[int(np.argmax(counts))])


def _nonbg_mask(gray: np.ndarray, bg: int) -> np.ndarray:
    """Boolean mask of pixels that differ meaningfully from background."""
    return np.abs(gray.astype(np.int16) - bg) > _BG_DIFF


def _bbox(mask: np.ndarray) -> tuple[int, int, int, int] | None:
    """Return (top, left, bottom, right) of True pixels, or None if empty."""
    rows = np.any(mask, axis=1)
    cols = np.any(mask, axis=0)
    if not rows.any() or not cols.any():
        return None
    top = int(np.argmax(rows))
    bottom = len(rows) - int(np.argmax(rows[::-1]))
    left = int(np.argmax(cols))
    right = len(cols) - int(np.argmax(cols[::-1]))
    return top, left, bottom, right


# ---------------------------------------------------------------- sampling / scene

def _scene_at(scene_durations: list[float], t: float) -> int | None:
    """Map a timestamp to a scene index using cumulative durations."""
    cum = 0.0
    for i, dur in enumerate(scene_durations):
        if t < cum + dur:
            return i
        cum += dur
    return len(scene_durations) - 1 if scene_durations else None


def _margin_band_mask(mask: np.ndarray, margin_y: int, margin_x: int) -> np.ndarray:
    """Boolean mask of True pixels that fall inside the safe-area margin band."""
    band = np.zeros_like(mask)
    if margin_y > 0:
        band[:margin_y, :] |= mask[:margin_y, :]
        band[-margin_y:, :] |= mask[-margin_y:, :]
    if margin_x > 0:
        band[:, :margin_x] |= mask[:, :margin_x]
        band[:, -margin_x:] |= mask[:, -margin_x:]
    return band


# ---------------------------------------------------------------- main entry

def lint_video(
    video_path: str,
    scene_durations: list[float],
    config: FrameLintConfig | None = None,
    *,
    decode: Callable = av.open,
) -> FrameLintResult:
    """Analyze `video_path` and return findings.

    `scene_durations` is the per-scene duration list (seconds) so timestamps
    can be mapped to scene indices. `decode` is injectable for testing (it
    must behave like ``av.open(path)`` returning a container with a video
    stream supporting ``decode()``).

    Frames are *sampled*: only every ``1/sample_fps`` seconds receives full
    per-pixel quality analysis (contrast, safe-area, bbox). Every frame still
    receives a cheap subsampled emptiness check so blank-interval detection
    survives sampling. Long videos therefore avoid full pixel analysis on
    most frames while still detecting blank intervals.

    Never raises: decode failures return a single error finding.
    """
    config = config or FrameLintConfig()
    result = FrameLintResult()
    if not config.enabled:
        return result

    try:
        container = decode(video_path)
    except Exception as exc:  # pragma: no cover - defensive
        result.findings.append(
            FrameFinding(
                kind="decode",
                severity="error",
                timestamp=0.0,
                scene_index=None,
                detail=f"could not open video for frame analysis: {exc}",
                frame_index=-1,
            )
        )
        return result

    try:
        video_stream = next((s for s in container.streams if s.type == "video"), None)
        if video_stream is None:
            result.findings.append(
                FrameFinding(
                    kind="no_video_stream",
                    severity="error",
                    timestamp=0.0,
                    scene_index=None,
                    detail="video has no decodable video stream",
                    frame_index=-1,
                )
            )
            return result

        width = video_stream.width
        height = video_stream.height
        duration = float(video_stream.duration * video_stream.time_base)
        duration_list = list(scene_durations)

        # Safe-area margin in pixels (computed once).
        margin_x = max(1, int(width * config.safe_area_margin))
        margin_y = max(1, int(height * config.safe_area_margin))
        area = width * height

        # True sampling: analyze only every sample_interval seconds.
        sample_interval = 1.0 / config.sample_fps
        next_sample_ts = 0.0

        # Time-based dedup: don't report the same kind of finding more than
        # once per sample_interval seconds.
        last_report_ts: dict[str, float] = {}

        def _report(kind: str, severity: str, detail: str, scene_idx: int | None) -> None:
            last = last_report_ts.get(kind)
            if last is not None and ts - last < sample_interval:
                return
            last_report_ts[kind] = ts
            result.findings.append(
                FrameFinding(
                    kind=kind,
                    severity=severity,
                    timestamp=ts,
                    scene_index=scene_idx,
                    detail=detail,
                    frame_index=analyzed,
                )
            )

        # Cheap subsampled emptiness check for blank-interval tracking on
        # non-sampled frames. Only a fraction of pixels are inspected, so
        # this is far cheaper than full per-pixel analysis.
        _SUBSAMPLE = 8  # inspect every Nth pixel in each dimension

        def _cheap_empty(rgb: np.ndarray, bg: int) -> float:
            """Return non-bg fraction estimated from a subsampled grid."""
            sub = rgb[::_SUBSAMPLE, ::_SUBSAMPLE]
            gray = _grayscale(sub)
            mask = _nonbg_mask(gray, bg)
            return float(mask.mean())

        # Blank-interval tracking across all frames.
        prev_content_ts: float | None = None
        seen_blank_since_last_content = False
        analyzed = 0

        for frame in container.decode(video_stream):
            ts = frame.time if frame.time is not None else analyzed
            ts = float(ts)

            scene_idx = _scene_at(duration_list, ts) if duration_list else None

            # Full per-pixel analysis only on sampled frames.
            if ts < next_sample_ts:
                # Non-sampled frame: cheap subsampled emptiness check only,
                # sufficient for blank-interval tracking.
                rgb = frame.to_ndarray(format="rgb24")
                gray = _grayscale(rgb)
                bg = _background_luma(gray)
                nonbg_fraction = _cheap_empty(rgb, bg)
                if nonbg_fraction < config.empty_threshold:
                    seen_blank_since_last_content = True
                else:
                    prev_content_ts = ts
                    seen_blank_since_last_content = False
                analyzed += 1
                continue

            next_sample_ts += sample_interval

            # Sampled frame: full per-pixel analysis.
            rgb = frame.to_ndarray(format="rgb24")
            gray = _grayscale(rgb)
            bg = _background_luma(gray)
            mask = _nonbg_mask(gray, bg)
            nonbg_fraction = float(mask.mean())

            # --- 1. Edge contact (warning) vs clipped (error) ---
            edge_hits = {
                "top": int(mask[0, :].sum()),
                "bottom": int(mask[-1, :].sum()),
                "left": int(mask[:, 0].sum()),
                "right": int(mask[:, -1].sum()),
            }
            total_edge = sum(edge_hits.values())
            if total_edge > 0:
                max_edge_fraction = max(
                    edge_hits["top"] / width,
                    edge_hits["bottom"] / width,
                    edge_hits["left"] / height,
                    edge_hits["right"] / height,
                )
                if max_edge_fraction >= config.clipped_edge_fraction:
                    _report(
                        "clipped",
                        "error",
                        (
                            f"{max_edge_fraction:.0%} of an edge has non-background pixels "
                            f"({', '.join(k for k, v in edge_hits.items() if v > 0)}); "
                            "content may extend beyond the frame"
                        ),
                        scene_idx,
                    )
                else:
                    _report(
                        "edge_contact",
                        "warning",
                        (
                            f"{total_edge} non-background pixels touch the frame edge "
                            f"({', '.join(k for k, v in edge_hits.items() if v > 0)})"
                        ),
                        scene_idx,
                    )

            # --- 2. Empty / nearly empty frame ---
            if nonbg_fraction < config.empty_threshold:
                _report(
                    "empty",
                    "warning",
                    f"frame is nearly empty ({nonbg_fraction:.4%} non-background pixels)",
                    scene_idx,
                )
                seen_blank_since_last_content = True
                analyzed += 1
                continue  # skip content-quality checks on empty frames

            # Content present: track blank intervals.
            if prev_content_ts is not None and seen_blank_since_last_content:
                gap = ts - prev_content_ts
                if gap > config.blank_interval_seconds:
                    _report(
                        "blank_interval",
                        "warning",
                        f"blank interval of {gap:.1f}s since last content frame",
                        scene_idx,
                    )
            prev_content_ts = ts
            seen_blank_since_last_content = False

            # --- 3. Safe-area violation: content inside the margin band ---
            if nonbg_fraction < _FOREGROUND_DOMINANCE_LIMIT:
                band = _margin_band_mask(mask, margin_y, margin_x)
                band_hits = int(band.sum())
                if band_hits > 0:
                    _report(
                        "safe_area",
                        "warning",
                        (
                            f"{band_hits} non-background pixels inside the "
                            f"{config.safe_area_margin:.0%} safe-area margin"
                        ),
                        scene_idx,
                    )

            # --- 4. Extremely small visible content ---
            bbox = _bbox(mask)
            if bbox is not None:
                top, left, bottom, right = bbox
                bbox_area = (bottom - top) * (right - left)
                if bbox_area / area < config.small_content_threshold:
                    result.findings.append(
                        FrameFinding(
                            kind="small_content",
                            severity="warning",
                            timestamp=ts,
                            scene_index=scene_idx,
                            detail=(
                                f"content bbox {bbox_area}px ({bbox_area / area:.4%} of frame) "
                                "is very small"
                            ),
                            frame_index=analyzed,
                        )
                    )

            # --- 5. Low contrast between foreground and background ---
            if nonbg_fraction < _FOREGROUND_DOMINANCE_LIMIT:
                fg_pixels = rgb[mask]
                if fg_pixels.size > 0:
                    fg_lum = float(_relative_luminance(fg_pixels[None, :, :]).mean())
                    bg_lum = float(
                        _relative_luminance(np.full((1, 1, 3), bg, dtype=np.uint8)).mean()
                    )
                    ratio = _contrast_ratio(fg_lum, bg_lum)
                    if ratio < config.low_contrast_threshold:
                        result.findings.append(
                            FrameFinding(
                                kind="low_contrast",
                                severity="warning",
                                timestamp=ts,
                                scene_index=scene_idx,
                                detail=(
                                    f"foreground/background contrast {ratio:.1f}:1 "
                                    f"(below {config.low_contrast_threshold}:1)"
                                ),
                                frame_index=analyzed,
                            )
                        )

            analyzed += 1
    except Exception as exc:  # pragma: no cover - defensive
        result.findings.append(
            FrameFinding(
                kind="analysis",
                severity="error",
                timestamp=0.0,
                scene_index=None,
                detail=f"frame analysis failed: {exc}",
                frame_index=-1,
            )
        )
    finally:
        try:
            container.close()
        except Exception:
            pass

    return result


def lint_result_to_warnings(result: FrameLintResult) -> list[str]:
    """Convert a :class:`FrameLintResult` into plain warning strings."""
    return result.as_messages(prefix="frame-lint")
