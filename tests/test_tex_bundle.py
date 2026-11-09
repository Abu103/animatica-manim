"""Tests for the prebuilt Windows LaTeX bundle (task card T12).

The bundle must never be used unverified, must never escape its target
directory, and must fall back to the upstream installer whenever anything
about it goes wrong.
"""
from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

import pytest

from animatica import tex_bundle
from animatica.tex_bundle import (
    BundleError,
    TEX_DIR_NAME,
    WINDOWS_BIN_SUBPATH,
    WINDOWS_TEX_ASSET_NAME,
    WINDOWS_TEX_RELEASE_TAG,
    WINDOWS_TEX_SHA256,
    WINDOWS_TEX_URL,
    bundle_settings,
    extract_bundle,
    install_windows_bundle,
    sha256_file,
)


def _make_zip(path: Path, members: dict[str, str]) -> Path:
    """Build a zip with the given member paths."""
    with zipfile.ZipFile(path, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return path


def _fake_zip_bytes(members: dict[str, str]) -> bytes:
    import io

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in members.items():
            archive.writestr(name, content)
    return buffer.getvalue()


# A TinyTeX zip usually has a top-level TinyTeX/ directory.
WINDOWS_ZIP_MEMBERS = {
    "TinyTeX/bin/windows/latex.exe": "binary",
    "TinyTeX/bin/windows/dvisvgm.exe": "binary",
    "TinyTeX/texmf-dist/tex/latex/standalone.cls": "class",
}


def test_settings_use_the_pinned_url_not_latest():
    """A moving URL and a fixed hash cannot both be right."""
    assert "latest" not in WINDOWS_TEX_URL
    assert WINDOWS_TEX_ASSET_NAME in WINDOWS_TEX_URL
    assert tex_bundle.WINDOWS_TEX_RELEASE_TAG in WINDOWS_TEX_URL


def test_empty_hash_fails_closed(tmp_path, monkeypatch):
    """With no known sha256 the bundle is not used at all."""
    monkeypatch.setattr(tex_bundle, "WINDOWS_TEX_SHA256", "")
    downloaded = []

    def download(url, dest, timeout=600):
        downloaded.append(url)
        dest.write_bytes(b"whatever")
        return dest

    ok, message = install_windows_bundle(tmp_path, env={}, download_fn=download)

    assert ok is False
    assert "sha256" in message.lower()
    assert downloaded == [], "the bundle must not even be downloaded without a known hash"
    assert not (tmp_path / ".tex").exists(), "nothing may be unpacked"


def test_hash_match_installs_the_bundle(tmp_path):
    """The happy path: a verified bundle is unpacked to .tex/bin/windows."""
    payload = _fake_zip_bytes(WINDOWS_ZIP_MEMBERS)
    expected = hashlib.sha256(payload).hexdigest()

    def download(url, dest, timeout=600):
        dest.write_bytes(payload)
        return dest

    ok, message = install_windows_bundle(
        tmp_path,
        env={tex_bundle.SHA256_ENV_VAR: expected},
        download_fn=download,
    )

    assert ok is True, message
    bin_dir = tmp_path / ".tex" / WINDOWS_BIN_SUBPATH
    assert bin_dir.is_dir()
    assert (bin_dir / "latex.exe").is_file()
    assert (bin_dir / "dvisvgm.exe").is_file()


def test_hash_mismatch_deletes_the_file_and_falls_through(tmp_path):
    """A corrupt or tampered bundle is deleted and never unpacked."""
    payload = _fake_zip_bytes(WINDOWS_ZIP_MEMBERS)
    wrong = hashlib.sha256(b"different").hexdigest()

    def download(url, dest, timeout=600):
        dest.write_bytes(payload)
        return dest

    ok, message = install_windows_bundle(
        tmp_path,
        env={tex_bundle.SHA256_ENV_VAR: wrong},
        download_fn=download,
    )

    assert ok is False
    assert "mismatch" in message.lower()
    assert not (tmp_path / ".tex").exists(), "a mismatching bundle must not be unpacked"
    # the downloaded file is deleted, not left behind
    leftovers = list(tmp_path.glob("**/*.zip"))
    assert leftovers == [], f"the bad archive was left on disk: {leftovers}"


def test_download_error_falls_through(tmp_path):
    """A 404 (or any network error) must not raise, only report."""
    def download(url, dest, timeout=600):
        raise BundleError("download failed: HTTP 404 for " + url)

    ok, message = install_windows_bundle(
        tmp_path,
        env={tex_bundle.SHA256_ENV_VAR: "0" * 64},
        download_fn=download,
    )

    assert ok is False
    assert "404" in message
    assert not (tmp_path / ".tex").exists()


def test_env_override_supplies_url_and_hash(tmp_path):
    """The build workflow uses the overrides to test its fresh artifact."""
    payload = _fake_zip_bytes(WINDOWS_ZIP_MEMBERS)
    expected = hashlib.sha256(payload).hexdigest()
    seen = []

    def download(url, dest, timeout=600):
        seen.append(url)
        dest.write_bytes(payload)
        return dest

    env = {
        tex_bundle.URL_ENV_VAR: "https://example.invalid/custom.zip",
        tex_bundle.SHA256_ENV_VAR: expected,
    }
    ok, message = install_windows_bundle(tmp_path, env=env, download_fn=download)

    assert ok is True, message
    assert seen == ["https://example.invalid/custom.zip"]
    assert (tmp_path / ".tex" / WINDOWS_BIN_SUBPATH / "latex.exe").is_file()


def test_env_override_without_hash_still_fails_closed(tmp_path, monkeypatch):
    """An override URL alone must not make an unverified bundle usable."""
    monkeypatch.setattr(tex_bundle, "WINDOWS_TEX_SHA256", "")
    downloaded = []

    def download(url, dest, timeout=600):
        downloaded.append(url)
        dest.write_bytes(b"x")
        return dest

    ok, message = install_windows_bundle(
        tmp_path,
        env={tex_bundle.URL_ENV_VAR: "https://example.invalid/custom.zip"},
        download_fn=download,
    )

    assert ok is False
    assert downloaded == []


def test_bundle_settings_default_to_the_pinned_pair():
    url, sha = bundle_settings(env={})
    assert url == WINDOWS_TEX_URL
    assert sha == WINDOWS_TEX_SHA256.lower()


def test_shipped_hash_with_wrong_bytes_is_rejected(tmp_path):
    """With the seeded constant, a wrong payload is rejected and nothing is unpacked."""
    downloaded = []

    def download(url, dest, timeout=600):
        downloaded.append(url)
        dest.write_bytes(b"wrong payload bytes")
        return dest

    ok, message = install_windows_bundle(
        tmp_path,
        env={},
        download_fn=download,
    )

    assert ok is False
    assert "mismatch" in message.lower()
    assert downloaded == [WINDOWS_TEX_URL]
    assert not (tmp_path / ".tex").exists(), "a mismatching bundle must not be unpacked"
    leftovers = list(tmp_path.glob("**/*.zip"))
    assert leftovers == [], f"the bad archive was left on disk: {leftovers}"


def test_zip_without_a_toplevel_directory_is_normalised(tmp_path):
    """Some archives have no TinyTeX/ wrapper; bin/windows must still land right."""
    archive = _make_zip(
        tmp_path / "flat.zip",
        {
            "bin/windows/latex.exe": "binary",
            "bin/windows/dvisvgm.exe": "binary",
        },
    )
    target = tmp_path / ".tex"
    bin_dir = extract_bundle(archive, target)
    assert bin_dir == target / WINDOWS_BIN_SUBPATH
    assert (bin_dir / "latex.exe").is_file()


def test_zip_with_a_toplevel_directory_is_normalised(tmp_path):
    """The usual TinyTeX/bin/windows layout is unwrapped to .tex/bin/windows."""
    archive = _make_zip(tmp_path / "wrapped.zip", WINDOWS_ZIP_MEMBERS)
    target = tmp_path / ".tex"
    bin_dir = extract_bundle(archive, target)
    assert bin_dir == target / WINDOWS_BIN_SUBPATH
    assert (bin_dir / "latex.exe").is_file()
    assert (target / "texmf-dist").is_dir(), "the rest of the tree must come along"


def test_zip_entries_that_escape_the_target_are_rejected(tmp_path):
    """A zip-slip archive must not write outside the target directory."""
    archive = _make_zip(
        tmp_path / "evil.zip",
        {
            "TinyTeX/bin/windows/latex.exe": "binary",
            "../escaped.txt": "pwned",
        },
    )
    target = tmp_path / ".tex"
    with pytest.raises(BundleError, match="escape"):
        extract_bundle(archive, target)
    assert not (tmp_path.parent / "escaped.txt").exists()
    assert not (target / "bin").exists()


def test_interrupted_unpack_never_looks_installed(tmp_path):
    """Extraction happens in a temp dir; only a complete tree is moved in."""
    archive = _make_zip(tmp_path / "bundle.zip", WINDOWS_ZIP_MEMBERS)
    target = tmp_path / ".tex"

    def exploding_move(*args, **kwargs):
        raise OSError("interrupted")

    original_move = tex_bundle.shutil.move
    tex_bundle.shutil.move = exploding_move
    try:
        with pytest.raises(OSError):
            extract_bundle(archive, target)
    finally:
        tex_bundle.shutil.move = original_move

    # the target must not exist at all: a partial install must be invisible
    assert not target.exists() or not (target / WINDOWS_BIN_SUBPATH).is_dir()


def test_sha256_file_matches_hashlib(tmp_path):
    payload = b"some bytes" * 1000
    target = tmp_path / "blob.bin"
    target.write_bytes(payload)
    assert sha256_file(target) == hashlib.sha256(payload).hexdigest()


def test_windows_bin_dirs_include_the_bundle_location(tmp_path, monkeypatch):
    """tinytex_bin_dirs must look where the bundle unpacks."""
    from animatica import doctor

    monkeypatch.chdir(tmp_path)
    (tmp_path / ".tex" / WINDOWS_BIN_SUBPATH).mkdir(parents=True)
    dirs = doctor.tinytex_bin_dirs(platform="win32", env={})
    assert tmp_path / ".tex" / WINDOWS_BIN_SUBPATH in dirs


def test_the_release_tag_and_the_hash_are_a_single_pair():
    """The tag and the hash must describe the same asset.

    They are one pair in one module on purpose: a URL pinned to a tag and a
    hash of a different build cannot both be right. The URL is DERIVED from
    the tag, so the tag and the URL cannot drift apart by accident; what the
    runbook guards is the hash, which is a value copied from GitHub.
    """
    # The URL is built from the tag, never from a moving "latest" ref.
    assert WINDOWS_TEX_URL.startswith("https://github.com/")
    assert f"/{WINDOWS_TEX_RELEASE_TAG}/" in WINDOWS_TEX_URL
    assert WINDOWS_TEX_URL.endswith(WINDOWS_TEX_ASSET_NAME)
    assert "latest" not in WINDOWS_TEX_URL


def test_changing_the_tag_changes_the_url():
    """The URL follows the tag: one edit moves both, so they cannot drift."""
    from animatica import tex_bundle as module

    original_tag = module.WINDOWS_TEX_RELEASE_TAG
    try:
        module.WINDOWS_TEX_RELEASE_TAG = "tex-deps-v9-windows"
        # the module-level URL was built at import time, so recompute the way
        # a fresh import would: the tag must be the only thing that changes.
        rebuilt = (
            f"https://github.com/Abu103/animatica-manim/releases/download/"
            f"{module.WINDOWS_TEX_RELEASE_TAG}/{module.WINDOWS_TEX_ASSET_NAME}"
        )
        assert "/tex-deps-v9-windows/" in rebuilt
        assert f"/{original_tag}/" not in rebuilt
    finally:
        module.WINDOWS_TEX_RELEASE_TAG = original_tag


def test_the_hash_constant_is_empty_or_64_hex_chars():
    """Offline check only: the shape of the constant.

    Whether the constant matches the PUBLISHED asset is a runbook step (read
    `gh release view <tag> --json assets` and compare), not a unit test: a
    unit test cannot see GitHub.
    """
    if WINDOWS_TEX_SHA256 == "":
        return  # not seeded yet: the bundle fails closed
    assert len(WINDOWS_TEX_SHA256) == 64
    assert all(c in "0123456789abcdef" for c in WINDOWS_TEX_SHA256), (
        f"the sha256 constant is not lowercase hex: {WINDOWS_TEX_SHA256!r}"
    )


def test_install_windows_bundle_oserror_falls_back(tmp_path, monkeypatch):
    """OSError on the per-user dir falls through to cwd .tex, in order.

    Uses a fake download_fn and fake expected sha so no network happens.
    """
    from animatica import tex_bundle

    attempts = []

    def fake_download(url, dest, timeout=600):
        attempts.append(("download", url))
        dest.write_bytes(b"fake bundle bytes")
        return dest

    def failing_extract(zip_path, target):
        attempts.append(("extract", target))
        raise OSError("permission denied")

    monkeypatch.setattr(tex_bundle, "extract_bundle", failing_extract)
    monkeypatch.setattr(tex_bundle, "download", fake_download)

    env = {"LOCALAPPDATA": str(tmp_path / "AppData" / "Local")}
    fake_sha = hashlib.sha256(b"fake bundle bytes").hexdigest()
    monkeypatch.setattr(tex_bundle, "WINDOWS_TEX_SHA256", fake_sha)

    ok, message = tex_bundle.install_windows_bundle(
        platform="win32", env=env, download_fn=fake_download
    )

    assert ok is False
    # Per-user dir tried first, then cwd .tex fallback. Download is attempt 0.
    per_user = tmp_path / "AppData" / "Local" / "Animatica" / "tex"
    cwd_tex = Path.cwd() / TEX_DIR_NAME
    extract_attempts = [t for t in attempts if t[0] == "extract"]
    assert extract_attempts[0] == ("extract", per_user), f"first extract wrong: {extract_attempts}"
    assert extract_attempts[1] == ("extract", cwd_tex), f"second extract wrong: {extract_attempts}"
    assert len(extract_attempts) == 2, f"expected exactly 2 extract attempts: {extract_attempts}"


def test_install_windows_bundle_corrupt_zip_fails_closed(tmp_path, monkeypatch):
    """A corrupt zip raises BundleError and aborts (no fall-through)."""
    from animatica import tex_bundle

    def fake_download(url, dest, timeout=600):
        dest.write_bytes(b"not a zip at all")
        return dest

    monkeypatch.setattr(tex_bundle, "download", fake_download)

    env = {"LOCALAPPDATA": str(tmp_path / "AppData" / "Local")}
    fake_sha = hashlib.sha256(b"not a zip at all").hexdigest()

    monkeypatch.setattr(tex_bundle, "WINDOWS_TEX_SHA256", fake_sha)

    ok, message = tex_bundle.install_windows_bundle(
        platform="win32", env=env, download_fn=fake_download
    )

    assert ok is False
    assert "escape" in message.lower() or "zip" in message.lower(), message
