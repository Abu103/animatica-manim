import sys

import pytest

from animatica.doctor import fix_dependencies, TEX_PACKAGES


class FakeRun:
    def __init__(self, fail_on=None):
        self.commands = []
        self.fail_on = fail_on or []

    def __call__(self, cmd, **kwargs):
        self.commands.append(cmd if isinstance(cmd, str) else " ".join(cmd))
        class R:
            returncode = 1 if any(f in self.commands[-1] for f in self.fail_on) else 0
        return R()


def test_tex_packages_include_the_ones_that_bit_us():
    # from the session logs: standalone.cls + babel-english were missing on a fresh TinyTeX
    for pkg in ("standalone", "preview", "babel-english", "amsmath", "amsfonts", "dvisvgm"):
        assert pkg in TEX_PACKAGES


def test_fix_installs_tinytex_and_packages_on_windows(monkeypatch):
    run = FakeRun()
    which = lambda name: "/bin/tlmgr" if name == "tlmgr" else None
    monkeypatch.setattr(
        "animatica.tex_bundle.install_windows_bundle",
        lambda root, env=None, **kwargs: (False, "bundle unavailable in test"),
    )
    actions = fix_dependencies(run=run, which=which, platform="win32", bundled_ffmpeg=lambda: None, sleep=lambda _: None)
    assert any("ffmpeg" in c.lower() and "winget" in c for c in run.commands)
    assert any("tinytex" in c.lower() for c in run.commands)
    assert any("tlmgr" in c and " ".join(TEX_PACKAGES) in c for c in run.commands)
    assert any("PATH" in a or "restart" in a for a in actions)


def test_windows_tinytex_retries_transient_installer_failures(monkeypatch):
    from animatica import doctor

    attempts = []
    installed = False
    ensure_calls = []
    sleeps = []

    class Result:
        def __init__(self, returncode=0, stdout="", stderr=""):
            self.returncode = returncode
            self.stdout = stdout
            self.stderr = stderr

    def run(cmd, **kwargs):
        nonlocal installed
        command = " ".join(cmd)
        if "install-bin-windows.ps1" in command:
            attempts.append(kwargs)
            if len(attempts) < 3:
                return Result(1, stderr="curl: (22) HTTP 504")
            installed = True
        return Result()

    def which(name):
        if installed and name in {"latex", "dvisvgm"}:
            return f"C:/TinyTeX/bin/windows/{name}.exe"
        return None

    def ensure_tex(platform):
        ensure_calls.append(platform)
        return "C:/TinyTeX/bin/windows" if installed else None

    monkeypatch.setattr(doctor, "ensure_tex_on_path", ensure_tex)
    monkeypatch.setattr(
        "animatica.tex_bundle.install_windows_bundle",
        lambda root, env=None, **kwargs: (False, "bundle unavailable in test"),
    )
    actions = doctor.fix_dependencies(
        run=run,
        which=which,
        platform="win32",
        bundled_ffmpeg=lambda: "/bundled/ffmpeg",
        sleep=sleeps.append,
    )

    assert len(attempts) == 3
    assert all(call["timeout"] == doctor.TINYTEX_WIN_INSTALL_TIMEOUT_SECONDS for call in attempts)
    assert sleeps == [5, 10]
    # One initial PATH check, then a fresh latex.exe check after each installer attempt.
    assert ensure_calls == ["win32"] * (1 + len(attempts))
    assert any("TinyTeX found at C:/TinyTeX/bin/windows" in action for action in actions)


def test_windows_tinytex_retry_count_is_bounded(monkeypatch):
    from animatica import doctor

    attempts = []
    sleeps = []

    class Result:
        returncode = 1
        stdout = ""
        stderr = "curl: (22) HTTP 504"

    def run(cmd, **kwargs):
        if "install-bin-windows.ps1" in " ".join(cmd):
            attempts.append(kwargs)
        return Result()

    monkeypatch.setattr(doctor, "ensure_tex_on_path", lambda _platform: None)
    monkeypatch.setattr(
        "animatica.tex_bundle.install_windows_bundle",
        lambda root, env=None, **kwargs: (False, "bundle unavailable in test"),
    )
    actions = doctor.fix_dependencies(
        run=run,
        which=lambda _name: None,
        platform="win32",
        bundled_ffmpeg=lambda: "/bundled/ffmpeg",
        sleep=sleeps.append,
    )

    assert len(attempts) == doctor.TINYTEX_WIN_INSTALL_ATTEMPTS == 3
    assert sleeps == [5, 10]
    assert any("failed after 3 attempts" in action and "HTTP 504" in action for action in actions)


def test_windows_uses_the_prebuilt_bundle_before_the_upstream_installer(monkeypatch, tmp_path):
    """The verified bundle is tried first; the upstream installer is skipped."""
    from animatica import doctor

    monkeypatch.chdir(tmp_path)
    bundle_calls = []
    installer_calls = []
    installed = {"value": False}

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def install_windows_bundle(root=None, env=None, **kwargs):
        bundle_calls.append(root)
        installed["value"] = True
        return True, "prebuilt LaTeX bundle installed"

    def ensure_tex(platform):
        return None

    def which(name):
        # latex only appears once the bundle has been installed
        if installed["value"] and name in ("latex", "dvisvgm"):
            return f"C:/TinyTeX/bin/windows/{name}.exe"
        return None

    def run(cmd, **kwargs):
        command = " ".join(cmd)
        if "install-bin-windows.ps1" in command:
            installer_calls.append(command)
        return Result()

    monkeypatch.setattr(doctor, "ensure_tex_on_path", ensure_tex)
    monkeypatch.setattr("animatica.tex_bundle.install_windows_bundle", install_windows_bundle)

    actions = doctor.fix_dependencies(
        run=run,
        which=which,
        platform="win32",
        bundled_ffmpeg=lambda: "/bundled/ffmpeg",
        sleep=lambda _: None,
    )

    assert bundle_calls, "the prebuilt bundle must be tried"
    assert installer_calls == [], "the upstream installer must not run when the bundle works"
    assert any("bundle" in a.lower() for a in actions)


def test_windows_falls_back_to_the_upstream_installer_when_the_bundle_fails(monkeypatch, tmp_path):
    """A failed bundle must not stop the upstream installer from running."""
    from animatica import doctor

    monkeypatch.chdir(tmp_path)
    installer_calls = []

    class Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def install_windows_bundle(root=None, env=None, **kwargs):
        return False, "sha256 mismatch; bundle deleted"

    def ensure_tex(platform):
        return None

    installed = {"value": False}

    def which(name):
        # latex is absent at first; the upstream installer provides it
        if installed["value"] and name in ("latex", "dvisvgm"):
            return f"C:/TinyTeX/bin/windows/{name}.exe"
        return None

    def run(cmd, **kwargs):
        command = " ".join(cmd)
        if "install-bin-windows.ps1" in command:
            installer_calls.append(command)
            installed["value"] = True
        return Result()

    monkeypatch.setattr(doctor, "ensure_tex_on_path", ensure_tex)
    monkeypatch.setattr("animatica.tex_bundle.install_windows_bundle", install_windows_bundle)

    actions = doctor.fix_dependencies(
        run=run,
        which=which,
        platform="win32",
        bundled_ffmpeg=lambda: "/bundled/ffmpeg",
        sleep=lambda _: None,
    )

    assert installer_calls, "the upstream installer must run when the bundle failed"
    assert any("mismatch" in a.lower() for a in actions)


def test_fix_linux_uses_apt_and_texlive():
    run = FakeRun()
    fix_dependencies(run=run, which=lambda name: None, platform="linux", bundled_ffmpeg=lambda: None)
    assert any("apt" in c and "ffmpeg" in c for c in run.commands)
    assert any("apt" in c and "texlive" in c for c in run.commands)


def test_fix_skips_what_is_already_present():
    run = FakeRun()
    fix_dependencies(run=run, which=lambda name: f"/usr/bin/{name}", platform="linux")
    assert run.commands == []


def test_fix_continues_past_a_failing_command(monkeypatch):
    run = FakeRun(fail_on=["winget"])
    which = lambda name: "/bin/tlmgr" if name == "tlmgr" else None
    monkeypatch.setattr(
        "animatica.tex_bundle.install_windows_bundle",
        lambda root, env=None, **kwargs: (False, "bundle unavailable in test"),
    )
    actions = fix_dependencies(run=run, which=which, platform="win32", bundled_ffmpeg=lambda: None, sleep=lambda _: None)
    # ffmpeg failed, but TinyTeX + tlmgr still attempted
    assert any("tinytex" in c.lower() for c in run.commands)
    assert any("tlmgr" in c for c in run.commands)
    assert any("failed" in a.lower() for a in actions)


def test_ffmpeg_check_accepts_imageio_bundled_binary():
    import importlib.util
    from animatica import doctor

    class FakeWhich:
        def __call__(self, name):
            return None
    # imageio-ffmpeg present in this env? if not, simulate by checking the helper directly
    if importlib.util.find_spec("imageio_ffmpeg") is None:
        pytest.skip("imageio-ffmpeg not installed in test env")
    import imageio_ffmpeg
    checks = doctor.run_checks(which=FakeWhich(), deep_latex=False)
    ff = next(c for c in checks if c.name == "ffmpeg")
    assert ff.ok and "imageio" in ff.detail
