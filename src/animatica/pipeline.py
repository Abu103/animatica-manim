"""``animatica make`` pipeline: prompt -> storyboard -> render -> captions -> report."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from animatica.ai.router import get_provider
from animatica.ai.template import TemplateMatcher
from animatica.ai.repair import generate_storyboard, generate_storyboard_two_stage
from animatica.backends.base import RenderBackend, RenderOptions
from animatica.backends.manim_backend import ManimBackend
from animatica.backends import default_backends
from animatica.components.registry import default_registry
from animatica.config import load_config
from animatica.encode.probe import pick_encoder, probe_encoders
from animatica.encode.transcode import transcode
from animatica.paths import long_path
from animatica.report import write_report
from animatica.storyboard.cache import StoryboardCache
from animatica.storyboard.lint import lint_storyboard
from animatica.storyboard.models import Storyboard, dump_storyboard, load_storyboard


@dataclass
class MakeResult:
    video: Path
    storyboard: Path
    captions: Path
    report: Path
    warnings: list[str]


def _vtt_timestamp(seconds: float) -> str:
    total = int(round(seconds * 1000))
    h = total // 3_600_000
    total %= 3_600_000
    m = total // 60_000
    total %= 60_000
    s = total // 1000
    ms = total % 1000
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


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
) -> MakeResult:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_dir = long_path(out_dir)
    registry = default_registry()
    warnings: list[str] = []

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

    errors = registry.validate(sb)
    if errors:
        raise ValueError("invalid storyboard: " + "; ".join(errors[:6]))

    dump_storyboard(sb, out_dir / "storyboard.json")

    # ---- render ----
    render_backend = resolve_backend(backend)
    if preview:
        quality = "preview"
    render_result = render_backend.render(
        sb, out_dir, RenderOptions(quality=quality, captions=captions)
    )
    video = render_result.video
    warnings.extend(render_result.warnings)

    # ---- optional transcode ----
    encoder_used = "x264 (manim default)"
    if encoder != "auto":
        enc_infos = probe_encoders()
        enc = pick_encoder(encoder, enc_infos)
        encoder_used = enc.name
        transcode_result = transcode(video, out_dir / "video_transcoded.mp4", enc)
        video = transcode_result.path
        if transcode_result.warning:
            warnings.append(f"transcode: {transcode_result.warning}")

    # ---- captions + report (single writer) ----
    _write_captions(sb, registry, out_dir / "captions.vtt")
    write_report(
        out_dir / "report.json",
        render_result.stage_times,
        warnings,
        backend={"name": render_backend.name, "version": getattr(render_backend, "version", "unknown")},
    )

    typer_print_provider(provider_used, encoder_used)

    return MakeResult(
        video=video,
        storyboard=out_dir / "storyboard.json",
        captions=out_dir / "captions.vtt",
        report=out_dir / "report.json",
        warnings=warnings,
    )


def typer_print_provider(provider_used: str, encoder_used: str) -> None:
    import typer

    typer.echo(f"Provider: {provider_used}")
    typer.echo(f"Encoder: {encoder_used}")

