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


def test_fix_installs_tinytex_and_packages_on_windows():
    run = FakeRun()
    which = lambda name: "/bin/tlmgr" if name == "tlmgr" else None
    actions = fix_dependencies(run=run, which=which, platform="win32")
    assert any("ffmpeg" in c.lower() and "winget" in c for c in run.commands)
    assert any("tinytex" in c.lower() for c in run.commands)
    assert any("tlmgr" in c and " ".join(TEX_PACKAGES) in c for c in run.commands)
    assert any("PATH" in a or "restart" in a for a in actions)


def test_fix_linux_uses_apt_and_texlive():
    run = FakeRun()
    fix_dependencies(run=run, which=lambda name: None, platform="linux")
    assert any("apt" in c and "ffmpeg" in c for c in run.commands)
    assert any("apt" in c and "texlive" in c for c in run.commands)


def test_fix_skips_what_is_already_present():
    run = FakeRun()
    fix_dependencies(run=run, which=lambda name: f"/usr/bin/{name}", platform="linux")
    assert run.commands == []


def test_fix_continues_past_a_failing_command():
    run = FakeRun(fail_on=["winget"])
    which = lambda name: "/bin/tlmgr" if name == "tlmgr" else None
    actions = fix_dependencies(run=run, which=which, platform="win32")
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
