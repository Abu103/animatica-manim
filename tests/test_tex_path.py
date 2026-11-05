"""TinyTeX discovery / PATH activation and honest doctor exit status (Windows logic, testable anywhere)."""
import os
from pathlib import Path

from typer.testing import CliRunner

from animatica import cli
from animatica.doctor import CheckResult, TINYTEX_WIN_INSTALLER_URL, ensure_tex_on_path, tinytex_bin_dirs


def test_windows_candidates_cover_appdata_programdata_and_choco():
    env = {"APPDATA": r"C:\Users\me\AppData\Roaming", "ProgramData": r"C:\ProgramData"}
    names = [str(d).replace("\\", "/") for d in tinytex_bin_dirs("win32", env)]
    assert any(n.endswith("AppData/Roaming/TinyTeX/bin/windows") for n in names)
    assert any(n.endswith("ProgramData/TinyTeX/bin/windows") for n in names)
    assert any(n.lower().endswith("tools/tinytex/bin/windows") for n in names)


def test_explicit_tinytex_dir_wins():
    env = {"TINYTEX_DIR": r"D:\tex", "APPDATA": r"C:\a"}
    first = str(tinytex_bin_dirs("win32", env)[0]).replace("\\", "/")
    assert first.startswith("D:/tex/TinyTeX")


def test_ensure_tex_on_path_prepends_the_valid_dir_only(tmp_path):
    good = tmp_path / "ProgramData" / "TinyTeX" / "bin" / "windows"
    good.mkdir(parents=True)
    env = {"PATH": "/nonexistent", "ProgramData": str(tmp_path / "ProgramData")}
    added = ensure_tex_on_path("win32", env, is_ok=lambda d: d == good)
    assert added == good
    assert env["PATH"].split(os.pathsep)[0] == str(good)


def test_ensure_tex_on_path_noop_when_nothing_found():
    env = {"PATH": "/nonexistent", "APPDATA": "/nope"}
    assert ensure_tex_on_path("win32", env, is_ok=lambda d: False) is None
    assert env["PATH"] == "/nonexistent"


def test_installer_url_is_not_the_dead_one():
    assert "yihui.org/tinytex/install-windows.ps1" not in TINYTEX_WIN_INSTALLER_URL
    assert TINYTEX_WIN_INSTALLER_URL.endswith("install-bin-windows.ps1")


def _checks(ok: bool):
    return [CheckResult("latex", ok, "x", "" if ok else "fix it")]


def test_doctor_fix_exit_status_reflects_state_after_fix(monkeypatch):
    states = iter([_checks(False), _checks(True)])  # fails first, passes after the fix
    monkeypatch.setattr(cli, "run_checks", lambda: next(states))
    monkeypatch.setattr(cli, "_offer_fix", lambda assume_yes=False: True)
    result = CliRunner().invoke(cli.app, ["doctor", "--fix"])
    assert result.exit_code == 0
    assert "All checks passed" in result.output


def test_doctor_fix_still_fails_if_fix_did_not_help(monkeypatch):
    monkeypatch.setattr(cli, "run_checks", lambda: _checks(False))
    monkeypatch.setattr(cli, "_offer_fix", lambda assume_yes=False: True)
    result = CliRunner().invoke(cli.app, ["doctor", "--fix"])
    assert result.exit_code == 1


def test_doctor_fix_declined_stays_failed(monkeypatch):
    monkeypatch.setattr(cli, "run_checks", lambda: _checks(False))
    monkeypatch.setattr(cli, "_offer_fix", lambda assume_yes=False: False)
    assert CliRunner().invoke(cli.app, ["doctor", "--fix"]).exit_code == 1


def test_bootstrap_does_not_claim_success_when_pip_fails(monkeypatch):
    import subprocess

    class R:
        returncode = 3

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    result = CliRunner().invoke(cli.app, ["bootstrap"])
    assert result.exit_code == 3
    assert "Done" not in result.output


def test_bootstrap_fails_when_final_doctor_fails(monkeypatch):
    import subprocess

    class R:
        returncode = 0

    monkeypatch.setattr(subprocess, "run", lambda *a, **k: R())
    monkeypatch.setattr("animatica.doctor.fix_dependencies", lambda: [])
    monkeypatch.setattr(cli, "run_checks", lambda: _checks(False))
    result = CliRunner().invoke(cli.app, ["bootstrap"])
    assert result.exit_code == 1
    assert "NOT complete" in result.output


def test_doctor_fix_yes_does_not_prompt(monkeypatch):
    called = {}
    monkeypatch.setattr("animatica.doctor.fix_dependencies", lambda: called.setdefault("ran", True) and [])
    monkeypatch.setattr(cli, "run_checks", lambda: _checks(False))
    result = CliRunner().invoke(cli.app, ["doctor", "--fix", "--yes"], input="")
    assert called.get("ran") is True  # ran without needing any stdin answer
    assert "Auto-install missing" not in result.output


def test_python_dash_m_animatica_actually_runs():
    """`python -m animatica` must execute the CLI (it silently did nothing before)."""
    import subprocess
    import sys

    r = subprocess.run([sys.executable, "-m", "animatica", "--version"], capture_output=True, text=True)
    assert r.returncode == 0
    assert "animatica" in r.stdout


def test_fresh_tinytex_without_dvisvgm_is_still_found(tmp_path):
    """Regression (Windows CI): a fresh TinyTeX has latex + tlmgr but no dvisvgm yet.
    It must be found, or tlmgr never reaches PATH and dvisvgm can never be installed."""
    bin_dir = tmp_path / "AppData" / "TinyTeX" / "bin" / "windows"
    bin_dir.mkdir(parents=True)
    (bin_dir / "latex.exe").write_text("")
    (bin_dir / "tlmgr.bat").write_text("")  # note: NO dvisvgm.exe
    env = {"PATH": "/nonexistent", "APPDATA": str(tmp_path / "AppData")}
    assert ensure_tex_on_path("win32", env) == bin_dir
    assert env["PATH"].split(os.pathsep)[0] == str(bin_dir)


def test_dir_without_latex_is_not_accepted(tmp_path):
    bin_dir = tmp_path / "AppData" / "TinyTeX" / "bin" / "windows"
    bin_dir.mkdir(parents=True)
    env = {"PATH": "/nonexistent", "APPDATA": str(tmp_path / "AppData")}
    assert ensure_tex_on_path("win32", env) is None


def test_search_report_lists_every_place_looked(tmp_path):
    from animatica.doctor import describe_tex_search

    env = {"APPDATA": str(tmp_path / "A"), "ProgramData": str(tmp_path / "P")}
    (tmp_path / "A" / "TinyTeX" / "bin" / "windows").mkdir(parents=True)
    report = describe_tex_search("win32", env)
    assert "FOUND" in report and "missing" in report
    assert "TinyTeX" in report


def test_no_system_ffmpeg_install_when_bundled_ffmpeg_exists():
    from animatica.doctor import fix_dependencies

    cmds = []

    def run(cmd, **kw):
        cmds.append(" ".join(cmd))

        class R:
            returncode = 0

        return R()

    fix_dependencies(run=run, which=lambda n: "/x/" + n if n != "ffmpeg" else None, platform="win32",
                     bundled_ffmpeg=lambda: "/bundled/ffmpeg")
    assert not any("winget" in c or "ffmpeg" in c for c in cmds)


def test_only_dvisvgm_missing_installs_packages_without_reinstalling_tinytex():
    from animatica.doctor import fix_dependencies

    cmds = []

    def run(cmd, **kw):
        cmds.append(" ".join(cmd))

        class R:
            returncode = 0

        return R()

    which = lambda n: None if n == "dvisvgm" else "C:/tex/" + n  # latex + tlmgr present
    fix_dependencies(run=run, which=which, platform="win32", bundled_ffmpeg=lambda: "x")
    assert any("tlmgr" in c and "dvisvgm" in c for c in cmds)
    assert not any("install-bin-windows" in c for c in cmds)  # TeX not reinstalled
