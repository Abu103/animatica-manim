"""Hardware encoder probing and safe transcode.

Probes ffmpeg for available hardware encoders (NVENC, QSV, VAAPI/AMF,
VideoToolbox), verifies each with a real 256x256 1s test encode, and falls
back to libx264. Results are cached keyed by ffmpeg version + device list.
Transcode never raises: on failure it returns the source path with a warning.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

_ENCODER_CACHE: dict[str, list["EncoderInfo"]] = {}


@dataclass(frozen=True)
class DeviceInfo:
    vendor: str
    name: str


@dataclass(frozen=True)
class EncoderInfo:
    name: str
    codec: str
    verified: bool
    reason: str


@dataclass(frozen=True)
class TranscodeResult:
    path: Path
    encoder: EncoderInfo
    warning: str | None


def _codec_of(name: str) -> str:
    low = name.lower()
    if "nvenc" in low:
        return "h264_nvenc"
    if "qsv" in low:
        return "h264_qsv"
    if "vaapi" in low:
        return "h264_vaapi"
    if "amf" in low:
        return "h264_amf"
    if "videotoolbox" in low:
        return "h264_videotoolbox"
    if name == "libx264":
        return "libx264"
    return name


_PLATFORM_MIDDLE = {"linux": "vaapi", "win32": "amf", "darwin": "h264_videotoolbox"}


def _candidates(platform: str) -> list[str]:
    base = ["h264_nvenc", "h264_qsv"]
    middle = _PLATFORM_MIDDLE.get(platform)
    if middle:
        base.append(middle)
    base.append("libx264")
    return base


def detect_devices(run: Callable = subprocess.run, platform: str = sys.platform) -> list[DeviceInfo]:
    """Detect GPU devices. Never raises; returns [] when tools are absent."""
    devices: list[DeviceInfo] = []
    try:
        if platform == "linux":
            out = run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
                      capture_output=True, text=True, timeout=10)
            for line in out.stdout.splitlines():
                line = line.strip()
                if line:
                    devices.append(DeviceInfo("nvidia", line))
            out = run(["vainfo"], capture_output=True, text=True, timeout=10)
            for line in out.stdout.splitlines():
                if "VA Profile" in line:
                    devices.append(DeviceInfo("vaapi", line.strip()))
        elif platform == "win32":
            out = run(["wmic", "path", "win32_VideoController", "get", "name"],
                      capture_output=True, text=True, timeout=10)
            for line in out.stdout.splitlines()[1:]:
                line = line.strip()
                if line:
                    devices.append(DeviceInfo("windows", line))
        elif platform == "darwin":
            out = run(["system_profiler", "SPDisplaysDataType"],
                      capture_output=True, text=True, timeout=10)
            for line in out.stdout.splitlines():
                if "Chipset:" in line or "GPU" in line:
                    devices.append(DeviceInfo("apple", line.strip()))
    except Exception:
        pass
    return devices


def _test_encode(ffmpeg: str, name: str, run: Callable) -> tuple[bool, str]:
    try:
        proc = run([
            ffmpeg, "-y", "-f", "lavfi", "-i", "testsrc=size=256x256:rate=1:duration=1",
            "-c:v", name, "-f", "null", "-",
        ], capture_output=True, text=True, timeout=60)
        if proc.returncode == 0:
            return True, ""
        return False, (proc.stderr or proc.stdout or "").strip() or "test encode failed"
    except Exception as exc:  # pragma: no cover - defensive
        return False, f"test encode raised: {exc}"


def _cache_key(version: str, devices: list[DeviceInfo]) -> str:
    return hashlib.sha256((version + repr(devices)).encode()).hexdigest()


def _default_ffmpeg() -> str:
    import shutil
    if shutil.which("ffmpeg"):
        return "ffmpeg"
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def probe_encoders(
    ffmpeg: str | None = None,
    run: Callable = subprocess.run,
    cache_dir: Path | None = None,
) -> list[EncoderInfo]:
    """Return encoder infos in preference order, each verified by a test encode."""
    if ffmpeg is None:
        ffmpeg = _default_ffmpeg()
    try:
        version_proc = run([ffmpeg, "-version"], capture_output=True, text=True, timeout=30)
        version = version_proc.stdout
    except Exception:
        return [EncoderInfo("libx264", "libx264", False, "ffmpeg not found or unusable")]

    devices = detect_devices(run=run)
    key = _cache_key(version, devices)

    cached = _ENCODER_CACHE.get(key)
    if cached is not None:
        return cached

    if cache_dir:
        cache_dir.mkdir(parents=True, exist_ok=True)
        cache_file = cache_dir / f"encoders_{key}.json"
        if cache_file.exists():
            try:
                data = json.loads(cache_file.read_text(encoding="utf-8"))
                result = [EncoderInfo(**d) for d in data]
                _ENCODER_CACHE[key] = result
                return result
            except Exception:
                pass

    try:
        enc_proc = run([ffmpeg, "-encoders"], capture_output=True, text=True, timeout=30)
        encoders_text = enc_proc.stdout
    except Exception:
        encoders_text = ""
    available = set()
    for line in encoders_text.splitlines():
        for tok in line.split():
            available.add(tok)

    result: list[EncoderInfo] = []
    for cand in _candidates(sys.platform):
        if cand != "libx264" and cand not in available:
            continue
        verified, reason = _test_encode(ffmpeg, cand, run)
        result.append(EncoderInfo(cand, _codec_of(cand), verified, reason))

    _ENCODER_CACHE[key] = result
    if cache_dir:
        try:
            cache_file.write_text(
                json.dumps([{"name": e.name, "codec": e.codec, "verified": e.verified,
                             "reason": e.reason} for e in result], indent=2),
                encoding="utf-8",
            )
        except Exception:
            pass
    return result


def pick_encoder(
    requested: str = "auto",
    infos: list[EncoderInfo] | None = None,
) -> EncoderInfo:
    if infos is None:
        infos = probe_encoders()
    if not infos:
        raise ValueError("no encoders available")
    if requested == "x264":
        for i in infos:
            if i.name == "libx264":
                return i
        raise ValueError("x264 not available; choices: " + ", ".join(i.name for i in infos))
    if requested == "auto":
        for i in infos:
            if i.verified:
                return i
        for i in infos:
            if i.name == "libx264":
                return i
        raise ValueError("no verified encoder; choices: " + ", ".join(i.name for i in infos))
    for i in infos:
        if i.name == requested:
            return i
    raise ValueError(f"unknown encoder {requested!r}; choices: " + ", ".join(i.name for i in infos))

