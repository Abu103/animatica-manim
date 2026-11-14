"""Safe transcode: remux/re-encode with a verified encoder, never raises."""
from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable

from animatica._nativelibs import system_tool_env
from animatica.encode.probe import EncoderInfo, TranscodeResult


def transcode(
    src: Path,
    dst: Path,
    enc: EncoderInfo,
    ffmpeg: str | None = None,
    run: Callable = subprocess.run,
) -> TranscodeResult:
    """Transcode `src` to `dst` using `enc`. On any failure return `src` with a
    warning; never raise and never modify `src`."""
    if ffmpeg is None:
        from animatica.encode.probe import _default_ffmpeg

        ffmpeg = _default_ffmpeg()
    src = Path(src)
    dst = Path(dst)
    try:
        proc = run(
            [ffmpeg, "-y", "-i", str(src), "-c:v", enc.name, str(dst)],
            capture_output=True,
            text=True,
            timeout=900,
            env=system_tool_env(),
        )
        if proc.returncode == 0 and dst.exists():
            return TranscodeResult(path=dst, encoder=enc, warning=None)
        return TranscodeResult(
            path=src,
            encoder=enc,
            warning=(proc.stderr or proc.stdout or "transcode failed").strip() or "transcode failed",
        )
    except Exception as exc:  # pragma: no cover - defensive
        return TranscodeResult(
            path=src,
            encoder=enc,
            warning=f"transcode raised: {exc}",
        )

