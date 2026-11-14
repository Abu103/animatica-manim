"""Offline narration: Piper TTS synthesized per beat, from the exact caption text.

docs/superpowers/specs/2026-11-14-narration-design.md is the design record
this implements. Two things from that spec that matter here:

* The engine (Piper) is MIT; each *voice model* carries its own license,
  checked individually. ``ALLOWED_VOICES`` is the allowlist of voices whose
  MODEL_CARD has actually been checked -- adding a voice is a data change to
  that tuple, never a bare string accepted from the CLI.
* This module does not fetch anything. It expects ``piper`` and the voice
  model already on disk and fails closed, with an actionable message,
  otherwise -- the same "nothing silent" posture as ``tex_bundle.py``.
  Fetching the voice model (pinned sha256, lazy on first use) is a separate
  card (the doctor ``--fix`` check), not implemented here.
"""
from __future__ import annotations

import shutil
import subprocess
import wave
from pathlib import Path

from animatica.pipeline import beat_text
from animatica.storyboard.models import Storyboard

#: Voices whose MODEL_CARD has been checked against the real
#: rhasspy/piper-voices data (spec section 2), not a reseller page.
#: ``en_US-ljspeech-medium`` is public domain (LJSpeech corpus).
DEFAULT_VOICE = "en_US-ljspeech-medium"
ALLOWED_VOICES: tuple[str, ...] = (DEFAULT_VOICE,)


class NarrationUnavailable(RuntimeError):
    """``piper``, or the requested voice model, is not installed yet."""


def synthesize(
    text: str,
    out_path: Path,
    voice: str = DEFAULT_VOICE,
    voice_model_path: Path | None = None,
    run=subprocess.run,
    which=shutil.which,
) -> Path:
    """Synthesize ``text`` to a WAV at ``out_path`` with Piper.

    Raises :class:`NarrationUnavailable` -- never guesses, never falls back
    to silence -- when ``voice`` isn't checked, ``piper`` isn't on PATH, the
    voice model file is missing, or Piper itself fails.
    """
    if voice not in ALLOWED_VOICES:
        raise NarrationUnavailable(
            f"voice {voice!r} is not in the checked-license allowlist {ALLOWED_VOICES}"
        )
    piper = which("piper")
    if not piper:
        raise NarrationUnavailable("piper is not on PATH; run `animatica doctor --fix` to install it")
    if voice_model_path is None or not voice_model_path.exists():
        raise NarrationUnavailable(
            f"the {voice} voice model is not installed; run `animatica doctor --fix` to fetch it"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    proc = run(
        [piper, "--model", str(voice_model_path), "--output_file", str(out_path)],
        input=text,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0 or not out_path.exists():
        lines = [ln for ln in (proc.stderr or "").strip().splitlines() if ln.strip()]
        reason = lines[-1][:200] if lines else f"piper exited {proc.returncode}"
        raise NarrationUnavailable(f"piper failed to synthesize: {reason}")
    return out_path


def wav_duration_seconds(path: Path) -> float:
    """How long a WAV file plays, from its own frame count and rate.

    Used to turn each beat's synthesized narration into a duration floor for
    ``pipeline._beat_durations`` (spec section 3) -- never assumed, always
    read back from the file Piper actually wrote.
    """
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / float(w.getframerate())


def narrate_storyboard(
    sb: Storyboard,
    registry,
    out_dir: Path,
    voice: str = DEFAULT_VOICE,
    voice_model_path: Path | None = None,
    synthesize_fn=synthesize,
) -> list[list[Path]]:
    """One WAV per beat, same nested shape and order as ``pipeline._beat_durations``.

    Reuses ``pipeline.beat_text`` so a narrated beat is never saying something
    other than what its caption shows.
    """
    out: list[list[Path]] = []
    for s_idx, scene in enumerate(sb.scenes):
        paths: list[Path] = []
        for b_idx, beat in enumerate(scene.beats):
            comp = registry.get(beat.component)
            text = beat_text(beat, comp)
            wav = out_dir / f"scene{s_idx:02d}_beat{b_idx:02d}.wav"
            paths.append(
                synthesize_fn(text, wav, voice=voice, voice_model_path=voice_model_path)
            )
        out.append(paths)
    return out
