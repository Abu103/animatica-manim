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


# ---- fix3: dvisvgm still missing after `tlmgr install` on a fresh Windows TinyTeX ----

def _fake_run(cmds, stdout="tlmgr: some output line"):
    def run(cmd, **kw):
        cmds.append(list(cmd))

        class R:
            returncode = 0
            stderr = ""

        R.stdout = stdout
        return R()

    return run


def test_dvisvgm_is_installed_on_its_own_and_output_is_reported(tmp_path):
    """dvisvgm gets its own tlmgr call; if it is still missing the log says what tlmgr and the bin dir know."""
    from animatica.doctor import fix_dependencies

    bindir = tmp_path / "TinyTeX" / "bin" / "windows"
    bindir.mkdir(parents=True)
    (bindir / "dvipdfmx.exe").write_text("")
    tlmgr = str(bindir / "tlmgr.bat")
    cmds = []
    which = lambda n: tlmgr if n == "tlmgr" else ("C:/tex/latex" if n == "latex" else None)  # dvisvgm never appears
    actions = fix_dependencies(run=_fake_run(cmds), which=which, platform="win32", bundled_ffmpeg=lambda: "x")
    assert [tlmgr, "install", "dvisvgm"] in cmds
    assert [tlmgr, "install", "--reinstall", "dvisvgm"] in cmds  # one retry before giving up
    assert [tlmgr, "info", "dvisvgm"] in cmds
    text = "\n".join(actions)
    assert "still not found" in text
    assert "dvipdfmx.exe" in text
    assert "tlmgr: some output line" in text


def test_dvisvgm_found_off_path_is_added_to_path(tmp_path, monkeypatch):
    """tlmgr installed it somewhere not on PATH: Animatica finds it in the TinyTeX tree and uses it."""
    from animatica.doctor import fix_dependencies

    bindir = tmp_path / "TinyTeX" / "bin" / "windows"
    other = tmp_path / "TinyTeX" / "bin" / "win64"
    bindir.mkdir(parents=True)
    other.mkdir(parents=True)
    (other / "dvisvgm.exe").write_text("")
    monkeypatch.setenv("PATH", "/nonexistent")
    tlmgr = str(bindir / "tlmgr.bat")
    import os

    def which(n):
        if n == "tlmgr":
            return tlmgr
        if n == "latex":
            return "C:/tex/latex"
        if n == "dvisvgm":
            return str(other / "dvisvgm.exe") if str(other) in os.environ["PATH"] else None
        return None

    actions = fix_dependencies(run=_fake_run([]), which=which, platform="win32", bundled_ffmpeg=lambda: "x")
    assert os.environ["PATH"].split(os.pathsep)[0] == str(other)
    assert any("dvisvgm found at" in a for a in actions)
    assert not any("still not found" in a for a in actions)


def test_linux_with_latex_but_no_dvisvgm_installs_dvisvgm():
    from animatica.doctor import fix_dependencies

    cmds = []
    which = lambda n: "/usr/bin/latex" if n == "latex" else ("/usr/bin/ffmpeg" if n == "ffmpeg" else None)
    fix_dependencies(run=_fake_run(cmds), which=which, platform="linux", bundled_ffmpeg=lambda: "x")
    assert any(c[-1] == "dvisvgm" and "apt" in c for c in cmds)
    assert not any("texlive" in c for c in cmds)  # TeX itself is not reinstalled


def test_apt_has_no_sudo_when_root(monkeypatch):
    import os

    from animatica.doctor import fix_dependencies

    monkeypatch.setattr(os, "geteuid", lambda: 0, raising=False)
    cmds = []
    fix_dependencies(run=_fake_run(cmds), which=lambda n: "/usr/bin/sudo" if n == "sudo" else None,
                     platform="linux", bundled_ffmpeg=lambda: None)
    assert cmds and all(c[0] == "apt" for c in cmds)


def test_doctor_fix_text_is_specific_when_only_dvisvgm_is_missing():
    from animatica.doctor import run_checks

    checks = run_checks(which=lambda n: "/usr/bin/latex" if n == "latex" else "/usr/bin/" + n if n != "dvisvgm" else None,
                        deep_latex=False)
    latex = next(c for c in checks if c.name == "latex")
    assert not latex.ok and "dvisvgm" in latex.fix and "installed" in latex.fix


# ---- fix4: tlmgr says "itself needs to be updated ... Terminating" and exits 0 ----

def test_tlmgr_is_updated_before_packages_are_installed(tmp_path):
    from animatica.doctor import TEX_PACKAGES, fix_dependencies

    bindir = tmp_path / "TinyTeX" / "bin" / "windows"
    bindir.mkdir(parents=True)
    tlmgr = str(bindir / "tlmgr.bat")
    cmds = []
    which = lambda n: tlmgr if n == "tlmgr" else ("C:/tex/latex" if n == "latex" else None)
    fix_dependencies(run=_fake_run(cmds), which=which, platform="win32", bundled_ffmpeg=lambda: "x")
    upd = cmds.index([tlmgr, "update", "--self"])
    assert upd < cmds.index([tlmgr, "install", "dvisvgm"])
    assert upd < cmds.index([tlmgr, "install", *TEX_PACKAGES])


def test_tlmgr_terminating_with_exit_zero_is_reported_as_failure(tmp_path):
    from animatica.doctor import fix_dependencies

    bindir = tmp_path / "TinyTeX" / "bin" / "windows"
    bindir.mkdir(parents=True)
    tlmgr = str(bindir / "tlmgr.bat")
    out = "tlmgr itself needs to be updated.\ntlmgr.pl: Terminating; please see warning above!"
    which = lambda n: tlmgr if n == "tlmgr" else ("C:/tex/latex" if n == "latex" else None)
    actions = fix_dependencies(run=_fake_run([], stdout=out), which=which, platform="win32", bundled_ffmpeg=lambda: "x")
    assert any(a.startswith("failed: install dvisvgm") for a in actions)
    assert not any(a.startswith("done: install dvisvgm") for a in actions)


# ---- fix5: verify by outcome (kpsewhich), not by tlmgr's exit code ----

def test_missing_tex_file_is_installed_via_tlmgr_search(tmp_path):
    """tlmgr 'succeeded' but a needed file is missing: ask tlmgr who owns it, install that, re-check."""
    from animatica.doctor import fix_dependencies

    bindir = tmp_path / "TinyTeX" / "bin" / "windows"
    bindir.mkdir(parents=True)
    (bindir / "kpsewhich.exe").write_text("")
    tlmgr = str(bindir / "tlmgr.bat")
    kpse = str(bindir / "kpsewhich.exe")
    installed = set()
    cmds = []

    def run(cmd, **kw):
        cmds.append(list(cmd))

        class R:
            returncode = 0
            stderr = ""
            stdout = ""

        if cmd[0] == kpse:
            name = cmd[1]
            R.stdout = f"C:/tex/{name}\n" if name != "standalone.cls" or "standalone-real" in installed else ""
            R.returncode = 0 if R.stdout else 1
        elif cmd[1:3] == ["search", "--file"]:
            R.stdout = "tlmgr: package repository x\nstandalone-real:\n\ttexmf-dist/tex/latex/standalone/standalone.cls\n"
        elif cmd[1] == "install":
            installed.update(cmd[2:])
        return R()

    which = lambda n: tlmgr if n == "tlmgr" else ("C:/tex/latex" if n == "latex" else None)  # dvisvgm missing -> tlmgr branch runs
    actions = fix_dependencies(run=run, which=which, platform="win32", bundled_ffmpeg=lambda: "x")
    assert [tlmgr, "search", "--file", "--global", "/standalone.cls"] in cmds
    assert [tlmgr, "install", "standalone-real"] in cmds
    assert any("standalone.cls is now available" in a for a in actions)


def test_still_missing_tex_file_is_reported_with_tlmgr_output(tmp_path):
    from animatica.doctor import fix_dependencies

    bindir = tmp_path / "TinyTeX" / "bin" / "windows"
    bindir.mkdir(parents=True)
    (bindir / "kpsewhich.exe").write_text("")
    tlmgr = str(bindir / "tlmgr.bat")
    kpse = str(bindir / "kpsewhich.exe")

    def run(cmd, **kw):
        class R:
            returncode = 1 if cmd[0] == kpse else 0
            stderr = ""
            stdout = "" if cmd[0] == kpse else "tlmgr says something odd"

        return R()

    which = lambda n: tlmgr if n == "tlmgr" else ("C:/tex/latex" if n == "latex" else None)
    actions = fix_dependencies(run=run, which=which, platform="win32", bundled_ffmpeg=lambda: "x")
    assert any(a.startswith("failed: TeX file standalone.cls still missing") and "tlmgr says something odd" in a for a in actions)


def test_missing_file_regex_handles_curly_quotes_and_cant_find_file():
    from animatica.components._latex import _tail_reason

    r, pk = _tail_reason("! LaTeX Error: File \u2018standalone.cls\u2019 not found.\n! Emergency stop.\n")
    assert "standalone.cls" in r and pk == ["standalone"]
    r, pk = _tail_reason("! I can't find file `preview.sty'.\n")
    assert "preview.sty" in r


def test_probe_reports_a_log_excerpt_when_no_package_is_identified(tmp_path):
    from animatica.latex_check import probe_latex

    class P:
        returncode = 1
        stderr = ""
        stdout = ""

    def run(cmd, **kw):
        import tempfile
        from pathlib import Path

        Path(cmd[-1], "x.log").write_text("junk\n! Emergency stop.\n<*> thing\n*** (job aborted)\n", encoding="utf-8")
        return P()

    ok, reason, pk = probe_latex(run=run)
    assert not ok and pk == [] and "Emergency stop" in reason and "job aborted" in reason


# ---- audit 2026-11-05: repair a TeX that is present but incomplete, leave a healthy one alone ------------
# Hermes made doctor --fix always run tlmgr on Windows/macOS (slow, touches working installs); the earlier
# code never ran it when latex+dvisvgm existed (the real bug: babel-english missing, fix did nothing).
# The rule now: ask kpsewhich; repair only what is actually missing.

class _R:
    def __init__(self, rc=0, out=""):
        self.returncode, self.stdout, self.stderr = rc, out, ""


def _fake_tex_env(missing=()):
    calls = []

    def run(cmd, **kw):
        cmd = [str(c) for c in cmd]
        calls.append(cmd)
        if cmd[0].endswith("kpsewhich"):
            name = cmd[1]
            return _R(1, "") if name in missing else _R(0, f"/tex/{name}\n")
        return _R(0, "")

    paths = {"latex": "/tex/latex", "dvisvgm": "/tex/dvisvgm", "tlmgr": "/tex/tlmgr", "kpsewhich": "/tex/kpsewhich"}
    return calls, run, paths.get


def test_healthy_tex_is_left_untouched_on_windows():
    from animatica.doctor import fix_dependencies
    calls, run, which = _fake_tex_env(missing=())
    fix_dependencies(run=run, which=which, platform="win32", bundled_ffmpeg=lambda: None)
    assert not any(c[0].endswith("tlmgr") for c in calls), "a working TeX must not be modified"


def test_present_but_incomplete_tex_is_repaired_on_windows():
    from animatica.doctor import fix_dependencies
    calls, run, which = _fake_tex_env(missing=("english.ldf",))
    actions = fix_dependencies(run=run, which=which, platform="win32", bundled_ffmpeg=lambda: None)
    assert any(c[0].endswith("tlmgr") and "install" in c and "babel-english" in c for c in calls)
    assert any("english.ldf" in a for a in actions)


def test_linux_never_calls_tlmgr_for_a_present_tex():
    from animatica.doctor import fix_dependencies
    calls, run, which = _fake_tex_env(missing=("english.ldf",))
    fix_dependencies(run=run, which=which, platform="linux", bundled_ffmpeg=lambda: None)
    assert not any(c[0].endswith("tlmgr") for c in calls), "on Linux apt owns TeX, not tlmgr"
