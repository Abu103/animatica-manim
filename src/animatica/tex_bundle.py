"""Prebuilt LaTeX bundle for Windows (TinyTeX).

The Linux bundle is built on Ubuntu by .github/workflows/tex-deps.yml and is a
Unix tree, so it cannot serve Windows. This module fetches the Windows bundle
instead: a TinyTeX tree built on windows-latest by
.github/workflows/build-tinytex-windows.yml.

Rules that matter here:

* Fail closed. The bundle is used only when its sha256 is known and matches.
  An unknown or mismatching bundle is deleted and the caller falls back to the
  upstream installer.
* The release tag and the sha256 live together as one constant pair, and the
  URL is pinned to that explicit tag. Never "latest": a moving URL and a fixed
  hash cannot both be right.
* Extraction happens in a temporary directory and is moved into place
  afterwards, so an interrupted unpack never looks like a finished install.
* Zip entries that would escape the target directory are rejected.
"""
from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

#: The release that carries the Windows bundle, and the sha256 of the zip in
#: it. Both are one constant pair on purpose: the URL below is pinned to this
#: exact tag, so the hash and the file cannot drift apart.
#:
#: The sha256 is empty until the first build of the bundle publishes it.
#: While it is empty the bundle is NOT used at all (fail closed) and the
#: upstream TinyTeX installer is used instead.
WINDOWS_TEX_RELEASE_TAG = "tex-deps-v1-windows"
WINDOWS_TEX_ASSET_NAME = "tinytex-manim-win.zip"
WINDOWS_TEX_SHA256 = "e3e92c824cef9d0340e81d1bbecbef522a53582b77269e4dfbe5fe7e9c2463e3"

#: Where the bundle is fetched from. Pinned to the tag above, never "latest".
WINDOWS_TEX_URL = (
    f"https://github.com/Abu103/animatica-manim/releases/download/"
    f"{WINDOWS_TEX_RELEASE_TAG}/{WINDOWS_TEX_ASSET_NAME}"
)

#: Environment overrides, used by the build workflow's own Windows job to
#: exercise the freshly built artifact before any hash is committed.
URL_ENV_VAR = "ANIMATICA_TEX_URL"
SHA256_ENV_VAR = "ANIMATICA_TEX_SHA256"

#: Where the bundle is unpacked, relative to the project root.
TEX_DIR_NAME = ".tex"

#: The directory inside the bundle that holds the executables, per platform.
WINDOWS_BIN_SUBPATH = Path("bin") / "windows"


class BundleError(Exception):
    """The bundle could not be fetched, verified or unpacked."""


def bundle_settings(env=None) -> tuple[str, str]:
    """Return (url, sha256) for the bundle, honouring the env overrides.

    The env overrides exist so the build workflow can test the artifact it
    just produced. They are not a way to skip verification: an override with
    an empty hash still fails closed.
    """
    env = os.environ if env is None else env
    url = env.get(URL_ENV_VAR) or WINDOWS_TEX_URL
    sha = (env.get(SHA256_ENV_VAR) or WINDOWS_TEX_SHA256 or "").strip().lower()
    return url, sha


def sha256_file(path: Path) -> str:
    """Hex sha256 of a file, read in chunks so a 100 MB bundle stays cheap."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(url: str, dest: Path, timeout: int = 600) -> Path:
    """Download `url` to `dest`. Raises BundleError on any network failure."""
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            with dest.open("wb") as handle:
                shutil.copyfileobj(response, handle)
    except urllib.error.HTTPError as exc:
        raise BundleError(f"download failed: HTTP {exc.code} for {url}") from exc
    except Exception as exc:
        raise BundleError(f"download failed: {type(exc).__name__} for {url}") from exc
    return dest


def _is_unsafe_member(name: str) -> bool:
    """True when a zip entry would escape the extraction directory."""
    if name.startswith("/") or name.startswith("\\"):
        return True
    if len(name) > 1 and name[1] == ":":  # C:\...
        return True
    parts = Path(name.replace("\\", "/")).parts
    return ".." in parts


def _normalise_root(members: list[str]) -> Path | None:
    """Find the directory inside the zip that holds `bin/windows`.

    TinyTeX zips usually carry a top-level `TinyTeX/` directory, so the
    executables live at `TinyTeX/bin/windows/...`. Some archives have no such
    wrapper. Both must end up with `bin/windows` at the same depth, so the
    caller knows where to look.
    """
    for name in members:
        parts = Path(name.replace("\\", "/")).parts
        for i in range(len(parts) - 1):
            if parts[i] == "bin" and parts[i + 1] == "windows":
                return Path(*parts[:i]) if i else Path()
    return None


def extract_bundle(zip_path: Path, target: Path) -> Path:
    """Extract the bundle so that `target` contains `bin/windows`.

    The archive is unpacked into a temporary directory first and only moved
    into `target` when it is complete, so a half-finished unpack never looks
    like an installed TeX.
    """
    with zipfile.ZipFile(zip_path) as archive:
        members = archive.namelist()
        unsafe = [m for m in members if _is_unsafe_member(m)]
        if unsafe:
            raise BundleError(f"archive contains entries that escape the target: {unsafe[0]}")
        root = _normalise_root(members)
        if root is None:
            raise BundleError("archive does not contain a bin/windows directory")

        with tempfile.TemporaryDirectory(prefix="animatica_texbundle_") as tmp:
            staging = Path(tmp) / "stage"
            staging.mkdir(parents=True, exist_ok=True)
            for member in members:
                extracted = staging / member
                target_path = extracted.resolve()
                if not str(target_path).startswith(str(staging.resolve())):
                    raise BundleError(f"archive entry escapes the target: {member}")
            archive.extractall(staging)

            source = staging / root if str(root) not in ("", ".") else staging
            if not (source / WINDOWS_BIN_SUBPATH).is_dir():
                raise BundleError("archive does not contain a bin/windows directory")

            # Replace only the tree we manage; a partial move must not leave a
            # half-installed bundle behind.
            if target.exists():
                shutil.rmtree(target, ignore_errors=True)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(target))

    if not (target / WINDOWS_BIN_SUBPATH).is_dir():
        raise BundleError("unpacked bundle has no bin/windows directory")
    return target / WINDOWS_BIN_SUBPATH


def install_windows_bundle(
    root: Path,
    env=None,
    download_fn=download,
    timeout: int = 600,
) -> tuple[bool, str]:
    """Try to install the prebuilt Windows bundle into `root/.tex`.

    Returns (ok, message). Never raises: every failure is reported as a
    message so the caller can fall back to the upstream installer.
    """
    url, expected = bundle_settings(env)
    if not expected:
        # Fail closed: an unverified bundle is never used.
        return False, "no known sha256 for the prebuilt bundle; using the upstream installer"

    target = Path(root) / TEX_DIR_NAME
    with tempfile.TemporaryDirectory(prefix="animatica_texdl_") as tmp:
        archive = Path(tmp) / WINDOWS_TEX_ASSET_NAME
        try:
            download_fn(url, archive, timeout=timeout)
        except BundleError as exc:
            return False, str(exc)

        actual = sha256_file(archive)
        if actual != expected:
            try:
                archive.unlink()
            except OSError:
                pass
            return False, f"sha256 mismatch (expected {expected[:12]}..., got {actual[:12]}...); bundle deleted"

        try:
            bin_dir = extract_bundle(archive, target)
        except BundleError as exc:
            return False, str(exc)
        except Exception as exc:
            return False, f"could not unpack the bundle: {type(exc).__name__}: {exc}"

    return True, f"prebuilt LaTeX bundle installed at {bin_dir}"


def bundle_bin_dirs(root: Path) -> list[Path]:
    """The Windows bin directories a bundle would provide, for tinytex_bin_dirs."""
    base = Path(root) / TEX_DIR_NAME
    if not base.is_dir():
        return []
    return [base / WINDOWS_BIN_SUBPATH]
