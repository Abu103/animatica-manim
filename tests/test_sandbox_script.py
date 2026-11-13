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
