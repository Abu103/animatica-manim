"""A content-addressed cache of rendered storyboards.

Rendering is the slowest thing this project does. One storyboard takes about
eight seconds at preview quality, and the conformance corpus has seventeen of
them, so a full pass over the corpus costs more than two minutes. Almost
every render is a repeat: the gate renders the corpus, a developer runs the
gate again after every change, and CI renders the same corpus the suite has
just rendered.

The cache is keyed by what a render actually depends on:

* the storyboard file,
* the quality it was rendered at,
* the interpreter and the Manim version,
* a fingerprint of every source file in the package.

That last one is what makes the cache safe. A render depends on the
components, the theme, the render scene and the pipeline; hashing all of them
means any change to any of them gives a new key, so a stale render can never
be served for new code.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import sys
from functools import lru_cache
from pathlib import Path

#: Where the cached renders live. Anchored to the repository, not to the
#: working directory, so every script in the repo shares one cache.
REPO_ROOT = Path(__file__).resolve().parents[2]
CACHE_ROOT = REPO_ROOT / ".animatica_cache" / "renders"

#: The files a cached render has to carry. The report is the one the gate
#: reads; the video is there so a cache hit is a complete render.
ARTIFACTS = ("report.json", "captions.vtt", "storyboard.json", "video.mp4")

#: Set this to switch the cache off (CI wants a clean render, not a replay).
DISABLE_ENV = "ANIMATICA_NO_RENDER_CACHE"


def enabled() -> bool:
    """Whether the cache may be used."""
    return not os.environ.get(DISABLE_ENV)


@lru_cache(maxsize=1)
def source_fingerprint() -> str:
    """A hash of every source file of the package.

    The render depends on the components, the theme, the render scene and the
    pipeline. Hashing all of them means a change to any of them gives a new
    cache key, so a stale render can never be served for new code.
    """
    digest = hashlib.sha256()
    package = Path(__file__).resolve().parent
    for path in sorted(package.rglob("*.py")):
        digest.update(str(path.relative_to(package)).replace("\\", "/").encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _manim_version() -> str:
    try:
        import manim

        return str(manim.__version__)
    except Exception:  # pragma: no cover - manim is not installed
        return "none"


def render_key(storyboard: Path, quality: str = "preview", extra: str = "") -> str:
    """The cache key for one render."""
    digest = hashlib.sha256()
    digest.update(Path(storyboard).read_bytes())
    digest.update(b"\0")
    digest.update(quality.encode("utf-8"))
    digest.update(b"\0")
    digest.update(extra.encode("utf-8"))
    digest.update(b"\0")
    digest.update(source_fingerprint().encode("utf-8"))
    digest.update(b"\0")
    digest.update(sys.version.encode("utf-8"))
    digest.update(b"\0")
    digest.update(_manim_version().encode("utf-8"))
    return digest.hexdigest()[:32]


def cache_dir(key: str) -> Path:
    """Where the render with this key lives."""
    return CACHE_ROOT / key


def restore(key: str, out_dir: Path) -> bool:
    """Put a cached render back into `out_dir`. True when there was one.

    A half-written cache entry (a render that was killed halfway) is not a
    hit: the report has to be there for the entry to count.
    """
    if not enabled():
        return False
    source = cache_dir(key)
    if not (source / "report.json").is_file():
        return False
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACTS:
        artifact = source / name
        if artifact.is_file():
            shutil.copy2(artifact, out_dir / name)
    return True


def store(key: str, out_dir: Path) -> None:
    """Keep a finished render for next time."""
    if not enabled():
        return
    out_dir = Path(out_dir)
    if not (out_dir / "report.json").is_file():
        return
    destination = cache_dir(key)
    destination.mkdir(parents=True, exist_ok=True)
    for name in ARTIFACTS:
        artifact = out_dir / name
        if artifact.is_file():
            shutil.copy2(artifact, destination / name)
