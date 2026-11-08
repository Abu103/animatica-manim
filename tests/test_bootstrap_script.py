"""Guards for the one-line installer (it is the only setup most users run)."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "bootstrap.sh"

def _usable_bash() -> str | None:
    """A bash that can run the script. On Windows, System32\\bash.exe is the WSL
    launcher, which fails with "no installed distributions", so Git's bash is used."""
    candidates = [shutil.which("bash")]
    if sys.platform == "win32":
        candidates += [
            r"C:\Program Files\Git\bin\bash.exe",
            r"C:\Program Files\Git\usr\bin\bash.exe",
            r"C:\Program Files (x86)\Git\bin\bash.exe",
        ]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            probe = subprocess.run([candidate, "--version"], capture_output=True, text=True, timeout=30)
        except Exception:
            continue
        if probe.returncode == 0 and "bash" in probe.stdout.lower():
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
