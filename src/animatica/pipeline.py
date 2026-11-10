"""``animatica make`` pipeline: prompt -> storyboard -> render -> captions -> report."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from animatica.ai.router import get_provider
from animatica.ai.template import TemplateMatcher
from animatica.ai.repair import generate_storyboard, generate_storyboard_two_stage
from animatica.ai.guidance import check_generation_guidance
from animatica.backends.base import RenderBackend, RenderOptions
from animatica.backends.manim_backend import ManimBackend
from animatica.backends import default_backends
from animatica.components.registry import ComponentRegistry, default_registry
from animatica.config import load_config
from animatica.encode.probe import pick_encoder, probe_encoders
from animatica.encode.transcode import transcode
from animatica.paths import long_path
from animatica.progress import ProgressFn, ProgressTracker
from animatica.report import write_report
from animatica.storyboard.cache import StoryboardCache
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Storyboard, dump_storyboard, load_storyboard

# Frame lint is a non-fatal post-render quality check. Imported here so the
# pipeline can wire it into ``make_video`` without the CLI knowing about PyAV.
from animatica.frame_lint import CAPTION_STRIP, FrameLintConfig, lint_video, lint_result_to_warnings  # noqa: PLC0415


@dataclass
class MakeResult:
    video: Path
    storyboard: Path
    captions: Path
    report: Path
    warnings: list[str]
    provider_used: str = ""
    encoder_used: str = ""
    fallbacks: list[str] = field(default_factory=list)


def _vtt_timestamp(seconds: float) -> str:
    total = int(round(seconds * 1000))
    h = total // 3_600_000
    total %= 3_600_000
    m = total // 60_000
    total %= 60_000
    s = total // 1000
    ms = total % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def _beat_durations(sb: Storyboard, registry) -> list[list[float]]:
    """How long each beat of each scene runs, in the storyboard's order.

    The frame lint judges a beat as a whole: a beat that fades in must not
    be condemned by its first frame, and a beat that never showed anything
    must still be reported.
    """
    out: list[list[float]] = []
    for scene in sb.scenes:
        durations: list[float] = []
        for beat in scene.beats:
            try:
                comp = registry.get(beat.component)
                durations.append(comp.duration(comp.Params.model_validate(beat.params)))
            except Exception:  # pragma: no cover - the storyboard is validated earlier
                durations.append(0.0)
        out.append(durations)
    return out


def _write_captions(sb: Storyboard, registry, path: Path) -> None:
    lines = ["WEBVTT", ""]
    t = 0.0
    for scene in sb.scenes:
        for beat in scene.beats:
            comp = registry.get(beat.component)
            params = comp.Params.model_validate(beat.params)
            dur = comp.duration(params)
            start, end = t, t + dur
            t = end
            text = beat.caption or comp.fallback_text(params)
            lines.append(f"{_vtt_timestamp(start)} --> {_vtt_timestamp(end)}")
            lines.append(text)
            lines.append("")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def resolve_backend(name: str) -> RenderBackend:
    """Resolve a render backend by name from ``default_backends()``.

    Raises ``ValueError`` listing the available names when unknown so the CLI
    can print a friendly message instead of a traceback (F6/F7, review focus #4).
    """
    backends = default_backends()
    if name not in backends:
        available = ", ".join(sorted(backends))
        raise ValueError(f"unknown backend {name!r}; available: {available}")
    return backends[name]


def cache_variant(prov, two_stage: bool, registry) -> str:
    """Cache qualifier for a storyboard: provider+model, one/two-stage mode,
    and the registry fingerprint — a model, mode, or component-schema change
    never resumes another entry's cached storyboard."""
    return f"{prov.name}:{prov.model}|{'two' if two_stage else 'one'}|{registry.fingerprint()}"


def make_video(
    prompt: str | None = None,
    storyboard_path: Path | None = None,
    out_dir: Path | str = ".",
    *,
    provider: str = "auto",
    quality: str = "standard",
    encoder: str = "auto",
    preview: bool = False,
    backend: str = "manim",
    captions: bool = True,
    two_stage: bool = False,
    jobs: int = 1,
    frame_lint: bool = True,
    vertical: bool = False,
    theme: str | None = None,
    on_progress: ProgressFn | None = None,
) -> MakeResult:
    render_backend = resolve_backend(backend)  # fail fast: before any file write or LLM call
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir = long_path(out_dir)
    registry = default_registry()
    warnings: list[str] = []

    # One unit per post-processing step the user actually asked for; the render
    # backend contributes its own scene units and fixes the total when it starts.
    post_units = 1 + (1 if encoder != "auto" else 0) + (1 if frame_lint else 0)
    progress = ProgressTracker(on_progress, post_units=post_units)

    progress.announce("storyboard", "resolving storyboard")

    # ---- storyboard: cache -> template -> provider ----
    if storyboard_path is not None:
        sb = load_storyboard(Path(storyboard_path))
        provider_used = "none (--from storyboard.json)"
    else:
        if not prompt or not str(prompt).strip():
            raise ValueError("prompt must not be empty")
        prompt = str(prompt).strip()
        # Canned templates are the offline fallback. If the user explicitly chose an AI provider,
        # they want that model's answer for *their* prompt, not a fixed example video.
        use_templates = provider in ("auto", "template")
        sb = TemplateMatcher().match(prompt) if use_templates else None
        if sb is not None:
            provider_used = "template (offline)"
        else:
            if provider == "template":
                raise ValueError(
                    "no offline template matches this prompt; pick an AI provider "
                    "with --provider (groq/openrouter/nim/ollama) or run 'animatica setup'"
                )
            cfg = load_config()
            prov = get_provider(provider, cfg)
            if prov is None:
                raise ValueError("no AI provider available; run 'animatica setup'")
            provider_used = prov.name
            cache = StoryboardCache(out_dir / ".animatica_cache")
            key = cache.key(prompt, cache_variant(prov, two_stage, registry), "1")
            try:
                sb = cache.get(key)
            except Exception:  # corrupt/stale cache entry: regenerate
                sb = None
            if sb is not None:
                provider_used = f"{prov.name} (cached)"
            else:
                sb = (generate_storyboard_two_stage(prompt, prov, registry) if two_stage
                      else generate_storyboard(prompt, prov, registry))
                cache.put(key, sb)

    if storyboard_path is None and not provider_used.startswith("template"):
        sb, lint_notes = lint_storyboard(sb)  # model output only; never touch a hand-written --from file
        warnings.extend(lint_notes)

    # Generation guidance applies to any storyboard: flag captions that
    # describe production mechanics instead of teaching, and comparisons
    # that lack a visual. These are notes, not errors.
    guidance_notes = check_generation_guidance(sb)
    warnings.extend(guidance_notes)

    errors = registry.validate(sb)
    if errors:
        raise ValueError("invalid storyboard: " + "; ".join(errors[:6]))

    # Apply CLI theme override if specified
    if theme is not None:
        sb.theme.palette = theme

    _check_capabilities(sb, render_backend)

    dump_storyboard(sb, out_dir / "storyboard.json")

    # ---- render ----
    if preview:
        quality = "preview"
    render_result = render_backend.render(
        sb,
        out_dir,
        RenderOptions(
            quality=quality,
            captions=captions,
            jobs=jobs,
            vertical=vertical,
            progress=progress.backend,
        ),
    )
    video = render_result.video
    warnings.extend(render_result.warnings)

    # ---- optional transcode ----
    encoder_used = "x264 (manim default)"
    if encoder != "auto":
        enc_infos = probe_encoders()
        enc = pick_encoder(encoder, enc_infos)
        encoder_used = enc.name
        progress.advance("transcode", f"re-encoding with {enc.name}")
        transcode_result = transcode(video, out_dir / "video_transcoded.mp4", enc)
        video = transcode_result.path
        if transcode_result.warning:
            warnings.append(f"transcode: {transcode_result.warning}")

    # ---- frame lint (non-fatal post-render quality check) ----
    if frame_lint:
        progress.advance("lint", "checking frames")
        # With no caption burned in there is no caption strip to leave out of
        # the coverage measurement.
        lint_config = FrameLintConfig(enabled=True, caption_strip=CAPTION_STRIP if captions else 0.0)
        lint_result = lint_video(
            str(video),
            render_result.durations,
            lint_config,
            beat_durations=_beat_durations(sb, registry),
        )
        warnings.extend(lint_result_to_warnings(lint_result))

    # ---- captions + report (single writer) ----
    progress.advance("captions", "writing captions and report")
    _write_captions(sb, registry, out_dir / "captions.vtt")

    # Component fallbacks: warnings from scene.py are formatted as
    # "{component}: {ExceptionType}: {message}" when play() raises and the
    # beat degrades to a text card. Extract the component names so they can
    # be recorded in report.json.
    #
    # Only that three-part shape counts. A component may also emit an
    # advisory that starts with its name ("compare: text scaled to 25 px
    # (floor 32)"); those are warnings, not fallbacks, and recording them
    # as fallbacks would report a beat as degraded when it rendered fine.
    registered = set(default_registry().names())
    fallbacks: list[str] = []
    seen_fallbacks: set[str] = set()
    for w in render_result.warnings:
        parts = w.split(": ", 2)
        if len(parts) != 3:
            continue
        component, exc_type = parts[0], parts[1]
        if component not in registered or component in seen_fallbacks:
            continue
        if not (exc_type.endswith("Error") or exc_type.endswith("Exception")):
            continue
        fallbacks.append(component)
        seen_fallbacks.add(component)

    write_report(
        out_dir / "report.json",
        render_result.stage_times,
        warnings,
        backend={"name": render_backend.name, "version": getattr(render_backend, "version", "unknown")},
        scene_durations=render_result.durations,
        fallbacks=fallbacks,
    )

    progress.finish(f"done: {video.name}")

    return MakeResult(
        video=video,
        storyboard=out_dir / "storyboard.json",
        captions=out_dir / "captions.vtt",
        report=out_dir / "report.json",
        warnings=warnings,
        provider_used=provider_used,
        encoder_used=encoder_used,
        fallbacks=fallbacks,
    )


# ---------------------------------------------------------------------------
# preview_frame: extract a single frame from a rendered video
# ---------------------------------------------------------------------------

def preview_frame(
    video_path: Path | str,
    scene_durations: list[float],
    scene_index: int,
    t: float,
    out_path: Path | str | None = None,
) -> Path:
    """Extract frame at time `t` within `scene_index` from `video_path`.

    `scene_durations` maps scene indices to cumulative time offsets so `t`
    (seconds within the scene) is translated to the video's absolute time.
    Returns the path to the extracted PNG frame (writes to `out_path` if given,
    otherwise next to the video).

    Raises ValueError for invalid scene_index or t (out of range, negative,
    non-finite). If scene_durations is empty (old report without scene
    durations), raises ValueError with an actionable message.
    """
    import av
    import numpy as np
    from PIL import Image

    video_path = Path(video_path)
    if not video_path.is_file():
        raise FileNotFoundError(f"video not found: {video_path}")

    # Validate scene_index and t before touching the video
    if not isinstance(scene_index, int) or scene_index < 0:
        raise ValueError(f"scene_index must be a non-negative integer, got {scene_index!r}")
    if not isinstance(t, (int, float)) or isinstance(t, bool):
        raise ValueError(f"t must be a number, got {t!r}")
    if not np.isfinite(float(t)):
        raise ValueError(f"t must be finite, got {t!r}")
    if not scene_durations:
        raise ValueError(
            f"no scene durations available for {video_path}: report.json has no "
            f"`scene_durations` field. Re-render the storyboard or specify "
            f"`scene_durations` as a list of per-scene seconds."
        )
    if scene_index >= len(scene_durations):
        raise ValueError(
            f"scene_index {scene_index} out of range for {len(scene_durations)} scenes: "
            f"scene_durations={scene_durations}"
        )
    if t < 0:
        raise ValueError(f"t must be >= 0, got {t!r}")
    if t > scene_durations[scene_index]:
        raise ValueError(
            f"t={t} is beyond scene {scene_index} duration "
            f"{scene_durations[scene_index]}s"
        )

    # Cumulative offsets: scene 0 starts at 0, scene 1 at sum(scene 0), etc.
    offset = sum(scene_durations[:scene_index])
    abs_ts = offset + t

    container = av.open(str(video_path))
    try:
        video_stream = next(s for s in container.streams if s.type == "video")
        target_frame = None
        for frame in container.decode(video_stream):
            ts = float(frame.time) if frame.time is not None else 0.0
            if ts >= abs_ts:
                target_frame = frame
                break
        if target_frame is None:
            raise ValueError(f"no frame at or after t={abs_ts:.1f}s in {video_path}")
        img = Image.fromarray(target_frame.to_ndarray(format="rgb24"))
    finally:
        container.close()

    if out_path is None:
        out_path = video_path.with_suffix(f".scene{scene_index}.t{t:.1f}.png")
    out_path = Path(out_path)
    img.save(out_path)
    return out_path


def _check_capabilities(sb: Storyboard, backend: RenderBackend, registry: ComponentRegistry | None = None) -> None:
    """Check that every component's required capabilities are supported by the backend.

    Raises ``ValueError`` with an actionable message when a component requires
    a capability the backend does not support. Checked before any rendering
    work begins so failures are fast and clear.

    Fail-closed: a backend that declares no capabilities supports nothing.
    Components with no required capabilities are compatible with any backend.
    """
    cap_fn = getattr(backend, "capabilities", None)
    supported = set(cap_fn()) if callable(cap_fn) else set(getattr(backend, "supported_capabilities", []))
    missing: list[str] = []
    for si, scene in enumerate(sb.scenes, 1):
        for bi, beat in enumerate(scene.beats, 1):
            # Look up component class from registry to get required_capabilities
            reg = registry or default_registry()
            try:
                comp_cls = reg.get(beat.component).__class__
            except KeyError:
                continue  # unknown component: validation already caught this
            for cap in getattr(comp_cls, "required_capabilities", []):
                if cap not in supported:
                    missing.append(
                        f"scene {si}, beat {bi}: component '{beat.component}' requires "
                        f"capability '{cap}' but backend '{backend.name}' only supports: "
                        f"{', '.join(sorted(supported)) or '(none)'}"
                    )
    if missing:
        raise ValueError(
            "Capability incompatibility: storyboard requires capabilities the backend does not support.\n"
            + "\n".join(f"  - {m}" for m in missing)
        )

