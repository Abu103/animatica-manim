"""Guards for the one-line installer (it is the only setup most users run)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "bootstrap.sh"

def _bash_candidates() -> list[str | None]:
    """Where a bash may live, most trustworthy first.

    On Windows `bash` on PATH is often System32\\bash.exe, the WSL launcher. It starts a Linux
    shell that cannot read a `C:\\...` script path, so Git for Windows' bash is tried first,
    found from the default folders and from wherever `git` itself is installed."""
    if sys.platform != "win32":
        return [shutil.which("bash")]
    candidates: list[str | None] = []
    git = shutil.which("git")
    if git:  # <Git>/cmd/git.exe -> <Git>/bin/bash.exe
        candidates.append(str(Path(git).resolve().parent.parent / "bin" / "bash.exe"))
    candidates += [
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
        r"C:\Program Files (x86)\Git\bin\bash.exe",
        shutil.which("bash"),
    ]
    return candidates


def _usable_bash(candidates: list[str | None] | None = None) -> str | None:
    """A bash that can run the script.

    A candidate must answer `--version` and also parse the real script path: a shell that
    starts but cannot open the file (the WSL launcher on Windows) is not usable."""
    for candidate in _bash_candidates() if candidates is None else candidates:
        if not candidate:
            continue
        try:
            probe = subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=30)
            if probe.returncode != 0 or "bash" not in probe.stdout.lower():
                continue
            parses = subprocess.run([candidate, "-n", str(SCRIPT)], capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        if parses.returncode == 0:
            return candidate
    return None


BASH = _usable_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="needs a usable bash")


def test_script_parses():
    result = subprocess.run([BASH, "-n", str(SCRIPT)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_help_lists_the_flags():
    result = subprocess.run([BASH, str(SCRIPT), "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "ANIMATICA_NATIVE_URL" in result.stdout
    assert "ANIMATICA_SKIP_SETUP" in result.stdout


def test_unknown_flag_is_rejected():
    result = subprocess.run([BASH, str(SCRIPT), "--nope"], capture_output=True, text=True)
    assert result.returncode == 2
    assert "unknown flag" in result.stderr


def test_readme_one_liner_matches_the_script():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/bootstrap.sh" in readme
    assert "animatica setup" in readme
    assert "animatica tui" in readme


def test_bootstraps_launch_setup_only_when_interactive():
    """Piped one-liners must use the terminal for prompts and stay CI-safe."""
    bash = SCRIPT.read_text(encoding="utf-8")
    ps1 = (ROOT / "scripts" / "bootstrap.ps1").read_text(encoding="utf-8")

    assert '"$ROOT/.venv/bin/animatica" setup </dev/tty' in bash
    assert "[ -t 1 ]" in bash and "ANIMATICA_SKIP_SETUP" in bash
    assert '"${CI:-}"' in bash and '"${GITHUB_ACTIONS:-}"' in bash
    assert "& $animatica setup" in ps1
    assert "Test-InteractiveTerminal" in ps1
    assert "[Console]::IsInputRedirected" in ps1
    assert "ANIMATICA_SKIP_SETUP" in ps1
    assert "$env:CI" in ps1 and "$env:GITHUB_ACTIONS" in ps1


PS1 = ROOT / "scripts" / "bootstrap.ps1"


def test_powershell_installer_exists_and_mirrors_the_bash_one():
    """Windows needs its own installer; parity is what users notice."""
    text = PS1.read_text(encoding="utf-8")
    # the same things the bash script promises
    assert "animatica tui" in text, "does not point at the studio"
    assert "ANIMATICA_REF" in text, "cannot install a branch/tag"
    assert "doctor --json" in text, "scrapes doctor output instead of parsing it"
    assert '-e ".[tui]"' in text, "does not install the advertised TUI dependency"
    assert "Add-DoctorCheck" in text, "does not normalize doctor JSON results"
    assert "cairo" in text and "pango" in text, "does not explain the Windows wheel situation"
    assert "\t" not in text, "tabs render badly in PowerShell"
    # failures must not close the terminal when piped through `irm | iex`
    assert 'throw ' in text
    assert not [ln for ln in text.splitlines() if ln.strip().startswith("exit ")]


def test_powershell_installer_braces_balance():
    """Cheap syntax sanity: there is no PowerShell in the test image."""
    text = PS1.read_text(encoding="utf-8")
    assert text.count("{") == text.count("}"), "unbalanced braces"
    assert text.count("(") == text.count(")"), "unbalanced parentheses"
    assert '$ErrorActionPreference = "Stop"' in text


def test_both_bootstraps_install_the_advertised_tui_extra():
    bash = SCRIPT.read_text(encoding="utf-8")
    ps1 = PS1.read_text(encoding="utf-8")
    assert 'pip_install -e ".[tui]"' in bash
    assert '-e ".[tui]"' in ps1
    assert "doctor --json returned no checks" in ps1


def test_existing_checkout_is_updated_safely_to_requested_ref():
    """A stale checkout must not silently ignore ANIMATICA_REF or lose user work."""
    bash = SCRIPT.read_text(encoding="utf-8")
    ps1 = PS1.read_text(encoding="utf-8")
    assert "sync_existing_checkout" in bash
    assert "merge-base --is-ancestor" in bash
    assert "has local changes" in bash
    assert "Sync-ExistingCheckout" in ps1
    assert "merge-base --is-ancestor" in ps1
    assert "has local changes" in ps1


def test_both_installers_are_referenced_in_the_readme():
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "scripts/bootstrap.sh" in readme
    assert "scripts/bootstrap.ps1" in readme


@pytest.mark.skipif(sys.platform == "win32", reason="the stand-in shell is a POSIX script")
def test_a_shell_that_cannot_open_the_script_is_not_chosen(tmp_path):
    """Regression (Windows): the WSL launcher answers `--version` but cannot read a Windows
    path ("No such file or directory", exit 127). It must not be picked over a working bash."""
    fake_wsl = tmp_path / "wsl-bash"
    fake_wsl.write_text(
        '#!/bin/sh\n[ "$1" = "--version" ] && { echo "GNU bash, version 5"; exit 0; }\n'
        'echo "No such file or directory" >&2; exit 127\n'
    )
    fake_wsl.chmod(0o755)
    real = shutil.which("bash")
    assert real is not None
    assert _usable_bash([str(fake_wsl)]) is None
    assert _usable_bash([str(fake_wsl), real]) == real
