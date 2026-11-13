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


def test_key_changes_when_an_optional_dependency_changes(tmp_path):
    """The runtime also carries the test and TUI extras, so they are part of the key."""
    a = _key(_pyproject(tmp_path, ["a>=1"], '[project.optional-dependencies]\ndev = ["pytest>=8"]\n'))
    b = _key(_pyproject(tmp_path, ["a>=1"], '[project.optional-dependencies]\ndev = ["pytest>=9"]\n'))
    c = _key(_pyproject(tmp_path, ["a>=1"], '[project.optional-dependencies]\ndev = ["pytest>=8"]\ntui = ["textual>=1"]\n'))
    none = _key(_pyproject(tmp_path, ["a>=1"]))
    assert len({a, b, c, none}) == 4


def test_key_ignores_comments_inside_optional_dependencies(tmp_path):
    plain = _key(_pyproject(tmp_path, ["a>=1"], '[project.optional-dependencies]\ndev = ["pytest>=8", "x"]\n'))
    noisy = _key(_pyproject(tmp_path, ["a>=1"], '[project.optional-dependencies]\n# a "quoted" comment\ndev = [\n  "x",  # why\n  "pytest>=8",\n]\n'))
    assert plain == noisy


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


def _make_runtime_archive(tmp: Path, name: str = "rt", marker: str = "v1", fonts: bool = False) -> Path:
    """A tiny runtime: python/bin/python3 stub, native/lib/libfake.so, a marker file."""
    src = tmp / f"{name}-src"
    shutil.rmtree(src, ignore_errors=True)
    (src / "python" / "bin").mkdir(parents=True)
    (src / "python" / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    (src / "native" / "lib").mkdir(parents=True)
    (src / "python" / "bin" / "python3").write_text("#!/bin/sh\necho stub-python \"$@\"\n")
    (src / "python" / "bin" / "python3").chmod(0o755)
    (src / "native" / "lib" / "libfake.so").write_text("x")
    (src / "MARKER").write_text(marker)
    if fonts:
        (src / "native" / "etc").mkdir(parents=True)
        (src / "native" / "etc" / "fonts.conf").write_text("<fontconfig/>")
    archive = tmp / f"{name}.tar.gz"
    archive.unlink(missing_ok=True)
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


def test_deps_flag_includes_the_optional_extras(tmp_path):
    p = _pyproject(tmp_path, ["a>=1"], '[project.optional-dependencies]\ntui = ["textual>=0.86"]\ndev = ["pytest>=8", "pytest-xdist>=3"]\n')
    r = subprocess.run([SH, str(KEY_SH), "--deps", str(p)], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    assert sorted(r.stdout.splitlines()) == ["a>=1", "pytest-xdist>=3", "pytest>=8", "textual>=0.86"]


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


# --------------------------------------------------------------------------- #
# Task 3: code layer, activation, idempotence
# --------------------------------------------------------------------------- #
GIT = shutil.which("git")


def _git(cwd: Path, *args: str) -> str:
    env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
    r = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=env, timeout=60)
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def _publish_for_checkout(remote: Remote, co: Path, tmp: Path, marker: str = "v1", fonts: bool = False) -> str:
    key = subprocess.run([SH, str(co / "scripts" / "runtime_key.sh"), str(co / "pyproject.toml")], capture_output=True, text=True).stdout.strip()
    remote.publish_release(key, _make_runtime_archive(tmp, marker=marker, fonts=fonts))
    return key


def _run_main(co: Path, remote: Remote, *args: str, extra_env: dict | None = None):
    env = {
        **os.environ, **remote.env(),
        "ANIMATICA_GIT_URL": "file:///nonexistent/repo.git",
        "ANIMATICA_PYPI_URL": f"file:///nonexistent/pypi",
        "ANIMATICA_DOCTOR_CMD": "true",
        "ANIMATICA_SMOKE_CMD": "true",
        "ANIMATICA_TEX_FETCH": "true",
        **(extra_env or {}),
    }
    return subprocess.run([SH, str(co / "scripts" / "sandbox.sh"), *args], capture_output=True, text=True, env=env, timeout=180, cwd=co.parent)


def _site_packages(co: Path) -> Path:
    return co / ".animatica-runtime" / "python" / "lib" / "python3.12" / "site-packages"


def _import_in(co: Path, module: str) -> subprocess.CompletedProcess:
    code = f"import site; site.addsitedir({str(_site_packages(co))!r}); import {module}"
    return subprocess.run([shutil.which("python3"), "-S", "-c", code], capture_output=True, text=True, timeout=60)


def test_pth_points_at_src_not_a_copy(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    r = _run_main(co, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (_site_packages(co) / "animatica-src.pth").read_text().strip() == str(co / "src")
    assert not (_site_packages(co) / "animatica").exists()


def test_added_module_importable_and_deleted_module_gone_without_rebuild(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    assert _run_main(co, remote).returncode == 0
    assert _import_in(co, "animatica.newmod").returncode != 0
    (co / "src" / "animatica" / "newmod.py").write_text("VALUE = 1\n")
    assert _import_in(co, "animatica.newmod").returncode == 0
    (co / "src" / "animatica" / "newmod.py").unlink()
    assert _import_in(co, "animatica.newmod").returncode != 0


def test_second_run_does_not_redownload_when_key_matches(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    assert _run_main(co, remote).returncode == 0
    shutil.rmtree(remote.root)  # the network is gone
    r = _run_main(co, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert "source=" not in r.stdout
    assert "up to date" in r.stdout


def test_second_run_keeps_local_edits(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    assert _run_main(co, remote).returncode == 0
    (co / "src" / "animatica" / "__init__.py").write_text("EDITED = True\n")
    (co / "notes.txt").write_text("mine\n")
    assert _run_main(co, remote).returncode == 0
    assert (co / "src" / "animatica" / "__init__.py").read_text() == "EDITED = True\n"
    assert (co / "notes.txt").read_text() == "mine\n"


def test_root_with_spaces_and_non_ascii(tmp_path):
    base = tmp_path / "my chéck out"
    base.mkdir()
    remote, co = Remote(tmp_path), _checkout(base)
    _publish_for_checkout(remote, co, tmp_path)
    r = _run_main(co, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert (_site_packages(co) / "animatica-src.pth").read_text().strip() == str(co / "src")
    out = subprocess.run([SH, "-c", '. ./.animatica-env && printf "%s" "$ANIMATICA_HOME"'], cwd=co, capture_output=True, text=True)
    assert out.stdout == str(co)
    shim = subprocess.run([SH, "-c", '. ./.animatica-env && animatica hello'], cwd=co, capture_output=True, text=True)
    assert shim.stdout.strip() == "stub-python -m animatica hello", shim.stderr


def test_env_file_exports_path_and_native_dirs(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    assert _run_main(co, remote).returncode == 0
    probe = '. ./.animatica-env && printf "%s\n%s\n%s" "$PATH" "$LD_LIBRARY_PATH" "$ANIMATICA_NATIVE_DIR"'
    out = subprocess.run([SH, "-c", probe], cwd=co, capture_output=True, text=True).stdout.split("\n")
    rt = co / ".animatica-runtime"
    assert out[0].startswith(f"{rt}/bin:{rt}/python/bin:")
    assert str(rt / "native" / "lib") in out[1].split(":")
    assert out[2] == str(rt / "native" / "lib")


def test_no_git_access_gets_git_init_and_one_commit(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    r = _run_main(co, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(co, "rev-list", "--count", "HEAD") == "1"
    assert _git(co, "remote", "get-url", "origin") == "file:///nonexistent/repo.git"
    assert _git(co, "status", "--porcelain") == ""  # runtime and env files are excluded


def test_git_clone_path_adds_history_without_touching_files(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    origin = tmp_path / "origin.git-src"
    shutil.copytree(co, origin)
    _git(origin, "init", "-q", "-b", "main")
    _git(origin, "add", "-A")
    _git(origin, "commit", "-qm", "upstream history")
    before = (co / "src" / "animatica" / "__init__.py").read_text()
    _publish_for_checkout(remote, co, tmp_path)
    r = _run_main(co, remote, extra_env={"ANIMATICA_GIT_URL": str(origin)})
    assert r.returncode == 0, r.stdout + r.stderr
    assert _git(co, "log", "-1", "--format=%s") == "upstream history"
    assert _git(co, "status", "--porcelain") == ""
    assert (co / "src" / "animatica" / "__init__.py").read_text() == before


def test_degraded_runtime_is_retried_on_the_next_run(tmp_path):
    """A substituted (older) runtime must not be recorded as the wanted key."""
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    remote.publish_release(OLD_KEY, _make_runtime_archive(tmp_path, marker="old"))
    remote.publish_latest(OLD_KEY)
    assert _run_main(co, remote).returncode == 0
    assert (co / ".animatica-runtime" / "MARKER").read_text() == "old"
    key = _publish_for_checkout(remote, co, tmp_path, marker="new")
    assert _run_main(co, remote).returncode == 0
    assert (co / ".animatica-runtime" / "MARKER").read_text() == "new"
    assert (co / ".animatica-runtime" / "KEY").read_text().strip() == key


# --------------------------------------------------------------------------- #
# Task 4: verify, timings, TeX in the background
# --------------------------------------------------------------------------- #
import time


def _final_line(r: subprocess.CompletedProcess) -> str:
    lines = [ln for ln in r.stdout.splitlines() if ln.strip()]
    return lines[-1] if lines else ""


def _ready_setup(tmp_path: Path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    return remote, co


def test_final_line_is_ready_with_seconds(tmp_path):
    remote, co = _ready_setup(tmp_path)
    r = _run_main(co, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert re.fullmatch(r"READY \d+s", _final_line(r)), r.stdout


def test_per_phase_timings_are_printed(tmp_path):
    remote, co = _ready_setup(tmp_path)
    r = _run_main(co, remote)
    for name in ("code", "runtime", "env", "verify"):
        assert re.search(rf"^phase {name}: \d+s$", r.stdout, re.M), (name, r.stdout)
    assert re.search(r"^timings: .*total \d+s$", r.stdout, re.M), r.stdout


def test_degraded_when_latest_runtime_substituted(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    remote.publish_release(OLD_KEY, _make_runtime_archive(tmp_path, marker="old"))
    remote.publish_latest(OLD_KEY)
    r = _run_main(co, remote)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _final_line(r).startswith("DEGRADED "), r.stdout
    assert OLD_KEY in _final_line(r)


def test_exit_nonzero_when_doctor_fails(tmp_path):
    remote, co = _ready_setup(tmp_path)
    r = _run_main(co, remote, extra_env={"ANIMATICA_DOCTOR_CMD": "echo cairo manim; exit 1"})
    assert r.returncode != 0
    assert _final_line(r).startswith("FAILED doctor"), r.stdout
    assert "cairo manim" in _final_line(r)


def test_exit_nonzero_when_the_smoke_render_fails(tmp_path):
    remote, co = _ready_setup(tmp_path)
    r = _run_main(co, remote, extra_env={"ANIMATICA_SMOKE_CMD": "exit 1"})
    assert r.returncode != 0
    assert _final_line(r).startswith("FAILED smoke render"), r.stdout


def test_exit_nonzero_over_budget(tmp_path):
    remote, co = _ready_setup(tmp_path)
    r = _run_main(co, remote, extra_env={"ANIMATICA_SMOKE_CMD": "sleep 3", "ANIMATICA_BUDGET_S": "1"})
    assert r.returncode != 0
    assert _final_line(r).startswith("FAILED over budget"), r.stdout


def test_tex_start_does_not_block(tmp_path):
    remote, co = _ready_setup(tmp_path)
    marker = tmp_path / "tex-done"
    t0 = time.time()
    r = _run_main(co, remote, extra_env={"ANIMATICA_TEX_FETCH": f'sleep 4; echo done > "{marker}"', "PATH": _path_without(tmp_path, "latex")})
    assert time.time() - t0 < 3.5, "main waited for the TeX download"
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tex: downloading in the background" in r.stdout
    assert re.fullmatch(r"READY \d+s", _final_line(r)), r.stdout
    for _ in range(30):
        if marker.exists():
            break
        time.sleep(0.5)
    assert marker.exists(), "the background TeX fetch never ran"


def test_no_tex_flag_skips_it(tmp_path):
    remote, co = _ready_setup(tmp_path)
    marker = tmp_path / "tex-ran"
    r = _run_main(co, remote, "--no-tex", extra_env={"ANIMATICA_TEX_FETCH": f'echo x > "{marker}"'})
    assert r.returncode == 0, r.stdout + r.stderr
    time.sleep(1)
    assert not marker.exists()
    assert "tex: skipped" in r.stdout


def test_verify_only_does_not_download(tmp_path):
    remote, co = _ready_setup(tmp_path)
    assert _run_main(co, remote).returncode == 0
    shutil.rmtree(remote.root)
    r = _run_main(co, remote, "--verify-only")
    assert r.returncode == 0, r.stdout + r.stderr
    assert "source=" not in r.stdout
    assert re.fullmatch(r"READY \d+s", _final_line(r)), r.stdout


def test_verify_only_without_a_runtime_fails_clearly(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    r = _run_main(co, remote, "--verify-only")
    assert r.returncode != 0
    assert _final_line(r).startswith("FAILED no runtime"), r.stdout


def test_runtime_only_skips_verification_and_tex(tmp_path):
    remote, co = _ready_setup(tmp_path)
    r = _run_main(co, remote, "--runtime-only", extra_env={"ANIMATICA_DOCTOR_CMD": "exit 1"})
    assert r.returncode == 0, r.stdout + r.stderr


def _tex_bundle(tmp: Path) -> Path:
    src = tmp / "tex-src"
    (src / "bin" / "x86_64-linux").mkdir(parents=True)
    (src / "bin" / "x86_64-linux" / "latex").write_text("#!/bin/sh\n")
    out = tmp / "animatica-tex.tar.xz"
    with tarfile.open(out, "w:xz") as t:
        t.add(src / "bin", arcname="bin")
    return out


def _wait_for(path: Path, seconds: int = 20) -> bool:
    for _ in range(seconds * 2):
        if path.exists():
            return True
        time.sleep(0.5)
    return False


def test_default_tex_fetcher_unpacks_the_release_bundle(tmp_path):
    remote, co = _ready_setup(tmp_path)
    bundle = _tex_bundle(tmp_path)
    r = _run_main(co, remote, extra_env={"ANIMATICA_TEX_FETCH": "", "ANIMATICA_TEX_URL": f"file://{bundle}", "PATH": _path_without(tmp_path, "latex")})
    assert r.returncode == 0, r.stdout + r.stderr
    assert _wait_for(co / ".tex" / "bin" / "x86_64-linux" / "latex")


def test_default_tex_fetcher_falls_back_to_the_codeload_artifacts_branch(tmp_path):
    remote, co = _ready_setup(tmp_path)
    bundle = _tex_bundle(tmp_path)
    inner = tmp_path / "art" / "repo-artifacts" / "native"
    inner.mkdir(parents=True)
    shutil.copy(bundle, inner / "animatica-tex.tar.xz")
    with tarfile.open(remote.codeload / "artifacts", "w:gz") as t:
        t.add(tmp_path / "art" / "repo-artifacts", arcname="repo-artifacts")
    r = _run_main(co, remote, extra_env={"ANIMATICA_TEX_FETCH": "", "ANIMATICA_TEX_URL": f"file://{tmp_path / 'nope.tar.xz'}", "PATH": _path_without(tmp_path, "latex")})
    assert r.returncode == 0, r.stdout + r.stderr
    assert _wait_for(co / ".tex" / "bin" / "x86_64-linux" / "latex")


def test_tex_already_present_is_not_fetched_again(tmp_path):
    remote, co = _ready_setup(tmp_path)
    (co / ".tex" / "bin").mkdir(parents=True)
    marker = tmp_path / "tex-ran"
    r = _run_main(co, remote, extra_env={"ANIMATICA_TEX_FETCH": f'echo x > "{marker}"', "PATH": _path_without(tmp_path, "latex")})
    assert r.returncode == 0, r.stdout + r.stderr
    assert "tex: ready" in r.stdout
    time.sleep(1)
    assert not marker.exists()


# --------------------------------------------------------------------------- #
# Task 5: building and publishing the runtime
# --------------------------------------------------------------------------- #
BUILD_SH = ROOT / "scripts" / "build_runtime.sh"
RUNTIME_WORKFLOW = ROOT / ".github" / "workflows" / "sandbox-runtime.yml"


def _stage(tmp: Path, payload: int = 300_000) -> Path:
    stage = tmp / "stage"
    (stage / "python" / "bin").mkdir(parents=True)
    (stage / "python" / "lib" / "python3.12" / "site-packages").mkdir(parents=True)
    (stage / "native" / "lib").mkdir(parents=True)
    (stage / "python" / "bin" / "python3").write_text("#!/bin/sh\necho stub-python \"$@\"\n")
    (stage / "python" / "bin" / "python3").chmod(0o755)
    (stage / "native" / "lib" / "libfake.so").write_bytes(os.urandom(payload))  # incompressible
    (stage / "MARKER").write_text("packed")
    return stage


def _pack(tmp: Path, part_bytes: int = 65536, stage: Path | None = None):
    out = tmp / "out"
    env = {**os.environ, "ANIMATICA_PART_BYTES": str(part_bytes)}
    r = subprocess.run([SH, str(BUILD_SH), "--pack-only", str(stage or _stage(tmp)), str(out)], capture_output=True, text=True, env=env, timeout=120)
    return r, out


def _repo_key() -> str:
    return subprocess.run([SH, str(KEY_SH), str(ROOT / "pyproject.toml")], capture_output=True, text=True).stdout.strip()


def test_pack_only_produces_parts_under_the_size_limit(tmp_path):
    r, out = _pack(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    parts = sorted(out.glob("part-*"))
    assert len(parts) > 1
    assert [p.name for p in parts] == [f"part-{i:02d}" for i in range(len(parts))]
    assert all(p.stat().st_size <= 65536 for p in parts)
    archive = out / f"animatica-runtime-{_repo_key()}.tar.gz"
    assert archive.is_file()
    assert b"".join(p.read_bytes() for p in parts) == archive.read_bytes()


def test_default_part_size_is_below_githubs_100mb_limit(tmp_path):
    text = BUILD_SH.read_text()
    m = re.search(r"ANIMATICA_PART_BYTES:-(\d+)", text)
    assert m, "the part size default must be written in the script"
    assert int(m.group(1)) < 100 * 1000 * 1000


def test_sha256sums_cover_parts_and_archive(tmp_path):
    r, out = _pack(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    listed = {}
    for line in (out / "SHA256SUMS").read_text().splitlines():
        digest, name = line.split(None, 1)
        listed[name.lstrip("*")] = digest
    expected = {p.name for p in out.glob("part-*")} | {f"animatica-runtime-{_repo_key()}.tar.gz"}
    assert set(listed) == expected
    for name, digest in listed.items():
        assert _sha(out / name) == digest, name


def test_packed_archive_keeps_the_runtime_layout(tmp_path):
    r, out = _pack(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    with tarfile.open(out / f"animatica-runtime-{_repo_key()}.tar.gz") as t:
        names = t.getnames()
    assert "python/bin/python3" in names
    assert "native/lib/libfake.so" in names


def test_packed_output_is_fetchable_through_the_release_path(tmp_path):
    r, out = _pack(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    key = _repo_key()
    remote = Remote(tmp_path)
    rel = remote.releases / f"runtime-{key}"
    rel.mkdir()
    shutil.copy(out / f"animatica-runtime-{key}.tar.gz", rel)
    shutil.copy(out / "SHA256SUMS", rel)
    res, dest = _fetch(tmp_path, remote, key=key)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "source=release" in res.stdout
    assert (dest / "MARKER").read_text() == "packed"


def test_packed_output_is_fetchable_through_the_codeload_branch_path(tmp_path):
    r, out = _pack(tmp_path)
    assert r.returncode == 0, r.stdout + r.stderr
    key = _repo_key()
    remote = Remote(tmp_path)
    top = tmp_path / "top"
    inner = top / f"repo-runtime-{key}"
    inner.mkdir(parents=True)
    for part in out.glob("part-*"):
        shutil.copy(part, inner)
    shutil.copy(out / "SHA256SUMS", inner)
    with tarfile.open(remote.codeload / f"runtime-{key}", "w:gz") as t:
        t.add(inner, arcname=inner.name)
    res, dest = _fetch(tmp_path, remote, key=key)
    assert res.returncode == 0, res.stdout + res.stderr
    assert "source=branch" in res.stdout
    assert (dest / "MARKER").read_text() == "packed"


def test_pack_only_rejects_a_stage_without_python(tmp_path):
    stage = tmp_path / "bad-stage"
    (stage / "native" / "lib").mkdir(parents=True)
    r, out = _pack(tmp_path, stage=stage)
    assert r.returncode != 0
    assert not list(out.glob("part-*")) if out.exists() else True


def test_build_script_pins_python_and_checks_the_download():
    text = BUILD_SH.read_text()
    assert re.search(r"^PBS_TAG=\d{8}$", text, re.M)
    assert re.search(r"^PBS_PYTHON=3\.12\.\d+$", text, re.M)
    assert re.search(r"^PBS_SHA256=[0-9a-f]{64}$", text, re.M)
    assert "--deps" in text  # installs the same list the key is computed from


def test_runtime_workflow_triggers_publishes_and_prunes():
    text = RUNTIME_WORKFLOW.read_text()
    assert re.search(r"^on:\s*$", text, re.M)
    for needle in ("pyproject.toml", "sandbox-runtime.yml", "schedule:", "cron:", "workflow_dispatch"):
        assert needle in text, needle
    assert "runtime_key.sh" in text and "build_runtime.sh" in text
    assert "python:3.12-slim-bookworm" in text  # glibc 2.36, the floor the runtime promises
    assert "gh release create" in text
    assert "runtime-latest" in text
    assert re.search(r"name:\s*Prune", text)
    assert "contents: write" in text


def test_build_script_compiles_extensions_with_gcc_not_the_pinned_pythons_clang():
    """python-build-standalone records CC=clang; the build host only has gcc (build-essential)."""
    text = BUILD_SH.read_text()
    assert re.search(r'CC="\$\{CC:-gcc\}"', text) and re.search(r'CXX="\$\{CXX:-g\+\+\}"', text)
    pip_line = next(ln for ln in text.splitlines() if "pip install" in ln)
    assert "CC=" in pip_line, "the compiler override must apply to the pip install that builds pycairo/manimpango"


# --------------------------------------------------------------------------- #
# Task 5b: a truly bare machine has no glib, fontconfig, freetype, X libs or fonts
# --------------------------------------------------------------------------- #
FONTS_CONF = ROOT / "scripts" / "sandbox_fonts.conf"


def _seed_library() -> Path:
    for d in ("/usr/lib/x86_64-linux-gnu", "/lib/x86_64-linux-gnu", "/usr/lib64", "/usr/lib"):
        for name in ("libpng16.so.16", "libfreetype.so.6"):
            if (Path(d) / name).exists():
                return Path(d) / name
    raise AssertionError("no libpng16 or libfreetype on this machine to seed the closure test")


def test_closure_bundles_the_non_glibc_dependencies(tmp_path):
    stage = _stage(tmp_path)
    seed = _seed_library()
    shutil.copy(seed, stage / "native" / "lib" / seed.name, follow_symlinks=True)
    r = subprocess.run([SH, str(BUILD_SH), "--closure", str(stage)], capture_output=True, text=True, timeout=120)
    assert r.returncode == 0, r.stdout + r.stderr
    names = {p.name for p in (stage / "native" / "lib").iterdir()}
    assert any(n.startswith("libz.so") for n in names), names
    core = {"libc.so.6", "libm.so.6", "libpthread.so.0", "libdl.so.2", "ld-linux-x86-64.so.2", "libgcc_s.so.1", "libstdc++.so.6"}
    assert not (names & core), names & core


def test_closure_is_idempotent(tmp_path):
    stage = _stage(tmp_path)
    seed = _seed_library()
    shutil.copy(seed, stage / "native" / "lib" / seed.name, follow_symlinks=True)
    for _ in range(2):
        assert subprocess.run([SH, str(BUILD_SH), "--closure", str(stage)], capture_output=True, timeout=120).returncode == 0
    first = sorted(p.name for p in (stage / "native" / "lib").iterdir())
    assert subprocess.run([SH, str(BUILD_SH), "--closure", str(stage)], capture_output=True, timeout=120).returncode == 0
    assert sorted(p.name for p in (stage / "native" / "lib").iterdir()) == first


def test_fonts_conf_is_well_formed_and_only_uses_the_bundled_fonts():
    import xml.etree.ElementTree as ET

    root = ET.parse(FONTS_CONF).getroot()
    assert root.tag == "fontconfig"
    dirs = [(d.get("prefix"), (d.text or "").strip()) for d in root.findall("dir")]
    assert dirs == [("relative", "../fonts")], dirs  # relative to native/etc: native/fonts
    assert not root.findall("include"), "system fonts would make renders differ between sandboxes"


def test_env_exports_fontconfig_only_when_the_runtime_ships_fonts(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path, fonts=True)
    assert _run_main(co, remote).returncode == 0
    out = subprocess.run([SH, "-c", '. ./.animatica-env && printf "%s" "$FONTCONFIG_FILE"'], cwd=co, capture_output=True, text=True).stdout
    assert out == str(co / ".animatica-runtime" / "native" / "etc" / "fonts.conf")


def test_env_leaves_fontconfig_alone_without_bundled_fonts(tmp_path):
    remote, co = Remote(tmp_path), _checkout(tmp_path)
    _publish_for_checkout(remote, co, tmp_path)
    assert _run_main(co, remote).returncode == 0
    out = subprocess.run([SH, "-c", 'unset FONTCONFIG_FILE; . ./.animatica-env && printf "%s" "${FONTCONFIG_FILE-unset}"'], cwd=co, capture_output=True, text=True).stdout
    assert out == "unset"


def test_build_ships_fonts_and_checks_a_real_render():
    text = BUILD_SH.read_text()
    assert "sandbox_fonts.conf" in text and "DejaVu" in text
    assert "--closure" in text
    assert "animatica make" in text or "-m animatica make" in text  # the build proves a render works on the bundled fonts alone
    wf = RUNTIME_WORKFLOW.read_text()
    assert "fonts-dejavu-core" in wf


# --------------------------------------------------------------------------- #
# Task 7: the agent entry point and the docs
# --------------------------------------------------------------------------- #
SANDBOX_SH = ROOT / "scripts" / "sandbox.sh"
ONE_COMMAND = (
    "curl -fsSL https://codeload.github.com/Abu103/animatica-manim/tar.gz/refs/heads/main"
    " | tar xz && sh animatica-manim-main/scripts/sandbox.sh"
)


def _help() -> str:
    r = subprocess.run([SH, str(SANDBOX_SH), "--help"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_agents_md_leads_with_the_one_command():
    head = "\n".join((ROOT / "AGENTS.md").read_text(encoding="utf-8").splitlines()[:16])
    assert ONE_COMMAND in head
    assert ". ./.animatica-env" in head
    assert "Read this first" in head  # the existing opening is kept, not replaced


def test_agents_md_command_matches_sandbox_help():
    text = _help()
    assert ONE_COMMAND in text, "sandbox.sh --help must print the same command AGENTS.md leads with"
    assert ". ./.animatica-env" in text


def test_help_does_not_start_an_install(tmp_path):
    """--help only prints: no runtime directory, no checkout changes."""
    co = _checkout(tmp_path)
    r = subprocess.run([SH, str(co / "scripts" / "sandbox.sh"), "--help"], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0
    assert not (co / ".animatica-runtime").exists()
    assert not (co / ".animatica-env").exists()


def test_setup_doc_lists_every_flag_tier_and_fallback():
    doc = (ROOT / "docs" / "SETUP.md").read_text(encoding="utf-8")
    for flag in ("--no-tex", "--verify-only", "--runtime-only", "--ref"):
        assert flag in doc, flag
        assert flag in _help(), f"{flag} is documented but sandbox.sh --help does not list it"
    for word in ("ANIMATICA_REF", "ANIMATICA_BUDGET_S", "codeload", "bootstrap.sh", "runtime-latest", "glibc"):
        assert word in doc, word
    for state in ("READY", "DEGRADED", "FAILED"):
        assert state in doc, state


def test_readme_points_agents_at_the_sandbox_command():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/sandbox.sh" in readme and "AGENTS.md" in readme
