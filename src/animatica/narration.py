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
import tarfile
import tempfile
import wave
from pathlib import Path

from animatica.config import config_dir
from animatica.pipeline import beat_text
from animatica.storyboard.models import Storyboard
from animatica.tex_bundle import download, sha256_file

#: Voices whose MODEL_CARD has been checked against the real
#: rhasspy/piper-voices data (spec section 2), not a reseller page.
#: ``en_US-ljspeech-medium`` is public domain (LJSpeech corpus).
DEFAULT_VOICE = "en_US-ljspeech-medium"
ALLOWED_VOICES: tuple[str, ...] = (DEFAULT_VOICE,)
#: Recorded in report.json so whoever ships the video knows what binds them.
VOICE_LICENSES: dict[str, str] = {DEFAULT_VOICE: "public domain (LJSpeech corpus)"}

#: The Piper engine (MIT) binary, pinned to a tagged release -- never
#: "latest" -- so the URL and the hash below cannot drift apart. Fetched and
#: hashed directly from github.com/rhasspy/piper's real release asset in
#: this session: verified.
PIPER_RELEASE_TAG = "v1.2.0"
PIPER_LINUX_ASSET = "piper_amd64.tar.gz"
PIPER_LINUX_SHA256 = "467c17935d2a22dcce9dc9e08ba07485e29be813097e7cf08c5627aa09d32e42"
PIPER_URL = f"https://github.com/rhasspy/piper/releases/download/{PIPER_RELEASE_TAG}/{PIPER_LINUX_ASSET}"

#: Voice model sha256, per voice (spec section 5: lazy-fetch, fail closed on
#: an unknown hash -- same posture as the Windows TeX bundle). UNVERIFIED:
#: read off the model's own Hugging Face LFS record, not hashed from a
#: downloaded file in this sandbox (huggingface.co is not reachable here).
#: Confirm with a real `sha256sum` on a machine that can reach it before
#: trusting this for anything beyond a first cautious try.
VOICE_MODEL_SHA256: dict[str, str] = {
    DEFAULT_VOICE: "6f52a751e2349abe7a76735eb09dc1875298c77ea2342ffd2fef79ff81b87f22",
}
_VOICE_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/v1.0.0/en/en_US/{name}/medium/{voice}.onnx"


class NarrationUnavailable(RuntimeError):
    """``piper``, or the requested voice model, is not installed yet."""


def narration_dir() -> Path:
    """Where the fetched Piper binary and voice models are cached."""
    d = config_dir() / "narration"
    d.mkdir(parents=True, exist_ok=True)
    return d


def piper_binary_path() -> Path:
    """Where a lazily-fetched Piper binary lives, whether or not it exists yet."""
    return narration_dir() / "piper" / "piper"


def voice_model_file(voice: str = DEFAULT_VOICE) -> Path:
    """Where a lazily-fetched voice model lives, whether or not it exists yet."""
    return narration_dir() / f"{voice}.onnx"


def fetch_piper(download_fn=download, timeout: int = 600) -> Path:
    """Fetch and verify the Piper engine binary, cached after the first call.

    Raises :class:`NarrationUnavailable` on any network failure or a hash
    that does not match ``PIPER_LINUX_SHA256`` -- the downloaded archive is
    never used unverified.
    """
    binary = piper_binary_path()
    if binary.is_file():
        return binary
    with tempfile.TemporaryDirectory(prefix="animatica_piper_") as tmp:
        tmp_path = Path(tmp)
        archive = tmp_path / PIPER_LINUX_ASSET
        try:
            download_fn(PIPER_URL, archive, timeout=timeout)
        except Exception as exc:
            raise NarrationUnavailable(f"piper download failed: {exc}") from exc
        got = sha256_file(archive)
        if got != PIPER_LINUX_SHA256:
            raise NarrationUnavailable(
                f"piper download hash mismatch: expected {PIPER_LINUX_SHA256}, got {got} -- not installed"
            )
        with tarfile.open(archive) as tf:
            tf.extractall(tmp_path)  # hash just verified above; contents are the known piper/ tree
        dest_dir = binary.parent
        if dest_dir.exists():
            shutil.rmtree(dest_dir, ignore_errors=True)
        dest_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_path / "piper"), str(dest_dir))
    if not binary.is_file():
        raise NarrationUnavailable("piper archive did not contain a piper binary")
    binary.chmod(binary.stat().st_mode | 0o111)
    return binary


def fetch_voice_model(voice: str = DEFAULT_VOICE, download_fn=download, timeout: int = 180) -> Path:
    """Fetch and verify ``voice``'s model (and its config), cached after the first call.

    Fails closed -- never fetched -- on a voice outside ``ALLOWED_VOICES`` or
    with no known hash in ``VOICE_MODEL_SHA256``.
    """
    if voice not in ALLOWED_VOICES:
        raise NarrationUnavailable(f"voice {voice!r} is not in the checked-license allowlist {ALLOWED_VOICES}")
    expected = VOICE_MODEL_SHA256.get(voice)
    if not expected:
        raise NarrationUnavailable(f"no known sha256 for voice {voice!r}; refusing to fetch it unverified")
    dest = voice_model_file(voice)
    if dest.is_file() and sha256_file(dest) == expected:
        return dest
    name = voice.split("-")[1]  # en_US-ljspeech-medium -> ljspeech
    model_url = _VOICE_BASE.format(name=name, voice=voice)
    with tempfile.TemporaryDirectory(prefix="animatica_voice_") as tmp:
        tmp_path = Path(tmp)
        tmp_model = tmp_path / f"{voice}.onnx"
        try:
            download_fn(model_url, tmp_model, timeout=timeout)
            got = sha256_file(tmp_model)
            if got != expected:
                raise NarrationUnavailable(
                    f"voice model download hash mismatch: expected {expected}, got {got} -- not installed"
                )
            download_fn(model_url + ".json", tmp_path / f"{voice}.onnx.json", timeout=timeout)
        except NarrationUnavailable:
            raise
        except Exception as exc:
            raise NarrationUnavailable(f"voice model download failed: {exc}") from exc
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(tmp_model), str(dest))
        shutil.move(str(tmp_path / f"{voice}.onnx.json"), str(dest.parent / f"{voice}.onnx.json"))
    return dest


def synthesize(
    text: str,
    out_path: Path,
    voice: str = DEFAULT_VOICE,
    voice_model_path: Path | None = None,
    run=subprocess.run,
    which=shutil.which,
    piper_path: Path | None = None,
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
    piper = str(piper_path) if piper_path is not None else which("piper")
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


def ensure_narration(voice: str = DEFAULT_VOICE) -> tuple[Path, Path]:
    """The Piper binary and ``voice``'s model, lazily fetched on first use.

    An unchecked voice is refused before any network call. Anything missing
    that cannot be fetched and hash-verified raises :class:`NarrationUnavailable`:
    ``--narrate`` never silently falls back to no narration (spec section 5).
    """
    if voice not in ALLOWED_VOICES:
        raise NarrationUnavailable(f"voice {voice!r} is not in the checked-license allowlist {ALLOWED_VOICES}")
    found = shutil.which("piper")
    if found:
        piper = Path(found)
    elif piper_binary_path().is_file():
        piper = piper_binary_path()
    else:
        piper = fetch_piper()
    model = voice_model_file(voice)
    if not model.is_file():
        model = fetch_voice_model(voice)
    return piper, model


def narrate_for_render(sb: Storyboard, registry, out_dir: Path, voice: str = DEFAULT_VOICE):
    """Synthesize every beat; return ``(wavs, floors)`` in ``_beat_durations`` shape.

    ``floors[scene][beat]`` is the clip's real length, read back from the WAV,
    and becomes that beat's minimum duration (spec section 3, option c).
    """
    piper, model = ensure_narration(voice)

    def synth(text, out_path, voice=voice, voice_model_path=model):
        return synthesize(text, out_path, voice=voice, voice_model_path=voice_model_path, piper_path=piper)

    wavs = narrate_storyboard(sb, registry, Path(out_dir) / "narration", voice=voice, voice_model_path=model, synthesize_fn=synth)
    return wavs, [[wav_duration_seconds(w) for w in row] for row in wavs]


def build_track(wavs: list[list[Path]], durations: list[list[float]], out: Path) -> Path:
    """One WAV the length of the video: each beat's clip starts where its beat starts.

    ``durations`` are the final per-beat durations (visual extended to cover
    narration), so clips can never overlap and never drift.
    """
    clips: list[tuple[float, Path]] = []
    t = 0.0
    for s_wavs, s_durs in zip(wavs, durations):
        for wav, dur in zip(s_wavs, s_durs):
            clips.append((t, wav))
            t += dur
    total = t
    rate = width = None
    for _, wav in clips:
        with wave.open(str(wav), "rb") as w:
            fmt = (w.getframerate(), w.getsampwidth(), w.getnchannels())
        if rate is None:
            rate, width, chans = fmt
        elif fmt != (rate, width, chans):
            raise NarrationUnavailable("narration clips have mixed audio formats; cannot build one track")
    rate, width, chans = (rate or 22050, width or 2, chans if clips else 1)
    frame_bytes = width * chans
    buf = bytearray(round(total * rate) * frame_bytes)
    for start, wav in clips:
        with wave.open(str(wav), "rb") as w:
            data = w.readframes(w.getnframes())
        at = round(start * rate) * frame_bytes
        data = data[: max(0, len(buf) - at)]
        buf[at : at + len(data)] = data
    out = Path(out)
    with wave.open(str(out), "wb") as w:
        w.setnchannels(chans)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(bytes(buf))
    return out


def mux_narration(video: Path, track: Path, out: Path, ffmpeg: str | None = None) -> Path:
    """Copy ``video`` untouched and add ``track`` as its AAC audio."""
    if ffmpeg is None:
        from animatica.encode.probe import _default_ffmpeg

        ffmpeg = _default_ffmpeg()
    from animatica._nativelibs import system_tool_env

    proc = subprocess.run(
        [ffmpeg, "-y", "-i", str(video), "-i", str(track), "-map", "0:v:0", "-map", "1:a:0",
         "-c:v", "copy", "-c:a", "aac", "-shortest", str(out)],
        capture_output=True, env=system_tool_env(),
    )
    if proc.returncode != 0 or not Path(out).exists():
        detail = (proc.stderr or b"").decode("utf-8", "replace").strip()[-300:]
        raise NarrationUnavailable(f"narration mux failed (ffmpeg exit {proc.returncode}): {detail}")
    return Path(out)
