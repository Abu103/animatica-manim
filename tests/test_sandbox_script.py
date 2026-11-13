"""Guards for the one-command sandbox bootstrap (scripts/sandbox.sh and friends).

Everything here runs offline: remote sources are file:// fixtures.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
KEY_SH = ROOT / "scripts" / "runtime_key.sh"
SH = shutil.which("sh")

pytestmark = pytest.mark.skipif(SH is None or os.name == "nt", reason="needs a POSIX sh")


def _pyproject(tmp_path: Path, deps: list[str], extra: str = "") -> Path:
    body = "\n".join(f'  "{d}",' for d in deps)
    p = tmp_path / "pyproject.toml"
    p.write_text(f'[project]\nname = "x"\ndependencies = [\n{body}\n]\n{extra}', encoding="utf-8")
    return p


def _key(path: Path, **env) -> str:
    e = {**os.environ, **env}
    r = subprocess.run([SH, str(KEY_SH), str(path)], capture_output=True, text=True, env=e, timeout=30)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_key_is_12_hex(tmp_path):
    assert re.fullmatch(r"[0-9a-f]{12}", _key(_pyproject(tmp_path, ["a>=1", "b==2"])))


def test_key_is_stable_across_runs(tmp_path):
    p = _pyproject(tmp_path, ["a>=1", "b==2"])
    assert _key(p) == _key(p)


def test_key_changes_when_a_dependency_changes(tmp_path):
    a = _key(_pyproject(tmp_path, ["a>=1", "b==2"]))
    b = _key(_pyproject(tmp_path, ["a>=1", "b==3"]))
    c = _key(_pyproject(tmp_path, ["a>=1", "b==2", "c"]))
    assert len({a, b, c}) == 3


def test_key_ignores_comments_whitespace_order_and_other_sections(tmp_path):
    plain = _key(_pyproject(tmp_path, ["a>=1", "b==2"]))
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[project]\nname = "renamed"\nversion = "9"\ndependencies = [\n'
        '  # a comment\n  "b==2",   # trailing\n\n  "a>=1",\n]\n[tool.pytest]\nx = 1\n',
        encoding="utf-8",
    )
    assert _key(p) == plain


def test_key_changes_with_python_minor_and_platform(tmp_path):
    p = _pyproject(tmp_path, ["a>=1"])
    base = _key(p)
    assert _key(p, ANIMATICA_RT_PYTHON="3.11") != base
    assert _key(p, ANIMATICA_RT_PLATFORM="linux-aarch64") != base


def test_key_for_the_repo_pyproject_is_computable():
    assert re.fullmatch(r"[0-9a-f]{12}", _key(ROOT / "pyproject.toml"))


# --------------------------------------------------------------------------- #
# Task 2: fetching the runtime
# --------------------------------------------------------------------------- #
import hashlib
import tarfile

SANDBOX_SH = ROOT / "scripts" / "sandbox.sh"
KEY = "aaaaaaaaaaaa"
OLD_KEY = "bbbbbbbbbbbb"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _make_runtime_archive(tmp: Path, name: str = "rt", marker: str = "v1") -> Path:
    """A tiny runtime: python/bin/python3 stub, native/lib/libfake.so, a marker file."""
    src = tmp / f"{name}-src"
    (src / "python" / "bin").mkdir(parents=True)
    (src / "native" / "lib").mkdir(parents=True)
    (src / "python" / "bin" / "python3").write_text("#!/bin/sh\nexec python3 \"$@\"\n")
    (src / "python" / "bin" / "python3").chmod(0o755)
    (src / "native" / "lib" / "libfake.so").write_text("x")
    (src / "MARKER").write_text(marker)
    archive = tmp / f"{name}.tar.gz"
    with tarfile.open(archive, "w:gz") as t:
        for child in sorted(src.iterdir()):
            t.add(child, arcname=child.name)
    return archive


class Remote:
    """A fake GitHub on disk, reached through file:// URLs."""

    def __init__(self, tmp: Path):
        self.root = tmp / "remote"
        self.releases = self.root / "releases"
        self.codeload = self.root / "codeload" / "tar.gz" / "refs" / "heads"
        self.releases.mkdir(parents=True)
        self.codeload.mkdir(parents=True)
        self.tmp = tmp

    def env(self) -> dict:
        return {
            "ANIMATICA_RELEASE_BASE": f"file://{self.releases}",
            "ANIMATICA_CODELOAD_BASE": f"file://{self.root / 'codeload'}",
        }

    def publish_release(self, key: str, archive: Path, bad_sum: bool = False) -> None:
        d = self.releases / f"runtime-{key}"
        d.mkdir(exist_ok=True)
        name = f"animatica-runtime-{key}.tar.gz"
        (d / name).write_bytes(archive.read_bytes())
        digest = "0" * 64 if bad_sum else _sha(archive)
        (d / "SHA256SUMS").write_text(f"{digest}  {name}\n")

    def _branch_tarball(self, branch: str, files: dict[str, bytes]) -> None:
        top = self.tmp / f"top-{branch}"
        inner = top / f"repo-{branch}"
        inner.mkdir(parents=True, exist_ok=True)
        for fname, data in files.items():
            (inner / fname).write_bytes(data)
        with tarfile.open(self.codeload / branch, "w:gz") as t:
            t.add(inner, arcname=inner.name)

    def publish_branch(self, key: str, archive: Path, part_size: int = 200, bad_part: bool = False) -> None:
        data = archive.read_bytes()
        name = f"animatica-runtime-{key}.tar.gz"
        files: dict[str, bytes] = {}
        sums = []
        for i in range(0, max(len(data), 1), part_size):
            chunk = data[i:i + part_size]
            pname = f"part-{i // part_size:02d}"
            files[pname] = chunk
            sums.append(f"{hashlib.sha256(chunk).hexdigest()}  {pname}")
        sums.append(f"{hashlib.sha256(data).hexdigest()}  {name}")
        if bad_part:
            files["part-00"] = files["part-00"][:-1] + b"X"
        files["SHA256SUMS"] = ("\n".join(sums) + "\n").encode()
        self._branch_tarball(f"runtime-{key}", files)

    def publish_latest(self, key: str) -> None:
        self._branch_tarball("runtime-latest", {"KEY": f"{key}\n".encode()})


def _fetch(tmp: Path, remote: Remote, key: str = KEY, extra_env: dict | None = None, path: str | None = None):
    dest = tmp / "dest"
    env = {
        **os.environ,
        **remote.env(),
        "ANIMATICA_SANDBOX_SOURCE_ONLY": "1",
        "ANIMATICA_SANDBOX_DIR": str(ROOT / "scripts"),
        "ANIMATICA_PYPI_URL": f"file://{tmp / 'no-such-pypi'}",
        **(extra_env or {}),
    }
    if path is not None:
        env["PATH"] = path
    cmd = f'. "{SANDBOX_SH}"; fetch_runtime "{key}" "{dest}"'
    r = subprocess.run([SH, "-c", cmd], capture_output=True, text=True, env=env, timeout=120)
    return r, dest


def test_release_asset_is_used_first(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_release(KEY, archive)
    remote.publish_branch(KEY, archive)
    r, dest = _fetch(tmp_path, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "source=release" in r.stdout
    assert (dest / "python" / "bin" / "python3").is_file()
    assert (dest / "native" / "lib" / "libfake.so").is_file()


def test_falls_back_to_branch_parts_when_release_missing(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_branch(KEY, archive)
    r, dest = _fetch(tmp_path, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "source=branch" in r.stdout
    assert (dest / "MARKER").read_text() == "v1"


def test_parts_are_joined_and_checksummed(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_branch(KEY, archive, part_size=64)  # many parts
    assert len(archive.read_bytes()) > 128
    r, dest = _fetch(tmp_path, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / "MARKER").read_text() == "v1"


def test_bad_checksum_is_rejected_and_next_step_tried(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_release(KEY, archive, bad_sum=True)
    remote.publish_branch(KEY, archive)
    r, dest = _fetch(tmp_path, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "source=branch" in r.stdout
    assert "source=release" not in r.stdout


def test_corrupt_branch_part_is_rejected(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_branch(KEY, archive, bad_part=True)
    r, dest = _fetch(tmp_path, remote)
    assert r.returncode != 0
    assert not dest.exists()


def test_unpublished_key_uses_latest_with_a_warning(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path, marker="old")
    remote.publish_release(OLD_KEY, archive)
    remote.publish_latest(OLD_KEY)
    r, dest = _fetch(tmp_path, remote, key=KEY)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "source=latest" in r.stdout
    assert f"WARN" in r.stdout + r.stderr and OLD_KEY in r.stdout + r.stderr
    assert (dest / "MARKER").read_text() == "old"


def test_unpublished_key_repairs_with_pip_when_pypi_reachable(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_release(OLD_KEY, archive)
    remote.publish_latest(OLD_KEY)
    reachable = tmp_path / "pypi-ok"
    reachable.write_text("ok")
    ran = tmp_path / "pip-ran"
    r, dest = _fetch(
        tmp_path, remote, key=KEY,
        extra_env={"ANIMATICA_PYPI_URL": f"file://{reachable}", "ANIMATICA_PIP_CMD": f'echo "$RT_DEST" > "{ran}"'},
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert ran.read_text().strip() == str(dest)
    assert "repaired" in r.stdout


def test_all_sources_failing_returns_nonzero_and_leaves_nothing(tmp_path):
    remote = Remote(tmp_path)
    r, dest = _fetch(tmp_path, remote)
    assert r.returncode != 0
    assert not dest.exists()
    assert not Path(str(dest) + ".tmp").exists()


def test_partial_download_never_leaves_a_runtime_dir(tmp_path):
    """The checksum matches but the archive cannot be unpacked (killed mid-write)."""
    remote = Remote(tmp_path)
    broken = tmp_path / "broken.tar.gz"
    good = _make_runtime_archive(tmp_path)
    broken.write_bytes(good.read_bytes()[: len(good.read_bytes()) // 2])
    remote.publish_release(KEY, broken)  # sums are computed from the truncated file
    r, dest = _fetch(tmp_path, remote)
    assert r.returncode != 0
    assert not dest.exists()
    assert not Path(str(dest) + ".tmp").exists()


def test_wrong_platform_is_a_clean_failure(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_release(KEY, archive)
    for env in ({"ANIMATICA_RT_UNAME_M": "aarch64"}, {"ANIMATICA_RT_GLIBC": "2.31"}, {"ANIMATICA_RT_GLIBC": ""}):
        r, dest = _fetch(tmp_path, remote, extra_env=env)
        assert r.returncode != 0, env
        assert "platform" in (r.stdout + r.stderr).lower(), env
        assert not dest.exists()


def _path_without(tmp: Path, *names: str) -> str:
    bindir = tmp / "bin-without"
    bindir.mkdir()
    for d in ("/usr/bin", "/bin"):
        for entry in os.scandir(d) if os.path.isdir(d) else []:
            if entry.name in names or (bindir / entry.name).exists():
                continue
            try:
                os.symlink(entry.path, bindir / entry.name)
            except OSError:
                pass
    return str(bindir)


@pytest.mark.skipif(not (shutil.which("shasum") or shutil.which("openssl")), reason="needs shasum or openssl")
def test_works_without_sha256sum_using_shasum_or_openssl(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_release(KEY, archive)
    r, dest = _fetch(tmp_path, remote, path=_path_without(tmp_path, "sha256sum"))
    assert r.returncode == 0, r.stdout + r.stderr
    assert (dest / "MARKER").read_text() == "v1"


def test_no_sha256_tool_at_all_fails_the_step_not_the_check(tmp_path):
    remote = Remote(tmp_path)
    archive = _make_runtime_archive(tmp_path)
    remote.publish_release(KEY, archive)
    r, dest = _fetch(tmp_path, remote, path=_path_without(tmp_path, "sha256sum", "shasum", "openssl"))
    assert r.returncode != 0
    assert not dest.exists()


def test_deps_flag_prints_requirements(tmp_path):
    p = _pyproject(tmp_path, ["a>=1", "b==2; python_version < '3.11'"])
    r = subprocess.run([SH, str(KEY_SH), "--deps", str(p)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert r.stdout.splitlines() == ["a>=1", "b==2; python_version < '3.11'"]


def _checkout(tmp: Path) -> Path:
    """A minimal checkout holding the two scripts the bootstrap needs."""
    co = tmp / "checkout"
    (co / "scripts").mkdir(parents=True)
    (co / "src" / "animatica").mkdir(parents=True)
    (co / "src" / "animatica" / "__init__.py").write_text("")
    shutil.copy(SANDBOX_SH, co / "scripts" / "sandbox.sh")
    shutil.copy(KEY_SH, co / "scripts" / "runtime_key.sh")
    shutil.copy(ROOT / "pyproject.toml", co / "pyproject.toml")
    return co


def test_all_sources_failing_runs_bootstrap(tmp_path):
    remote = Remote(tmp_path)
    co = _checkout(tmp_path)
    marker = tmp_path / "bootstrap-ran"
    stub = tmp_path / "bootstrap-stub.sh"
    stub.write_text(f'#!/bin/sh\necho ran > "{marker}"\n')
    env = {
        **os.environ, **remote.env(),
        "ANIMATICA_BOOTSTRAP": str(stub),
        "ANIMATICA_PYPI_URL": f"file://{tmp_path / 'no-such-pypi'}",
    }
    r = subprocess.run([SH, str(co / "scripts" / "sandbox.sh"), "--runtime-only"], capture_output=True, text=True, env=env, timeout=120, cwd=tmp_path)
    assert marker.exists(), r.stdout + r.stderr
