from pathlib import Path

import pytest

from animatica.paths import check_tex_safe, long_path, tex_unsafe_chars


def test_long_path_is_a_noop_off_windows(tmp_path):
    assert long_path(tmp_path, platform="linux") == tmp_path


def test_long_path_expands_short_names_on_windows(tmp_path):
    """RUNNER~1 -> runneradmin, for a folder that does not exist yet too (nearest parent is expanded)."""
    seen = []

    def expand(p):
        seen.append(p)
        return str(tmp_path / "runneradmin")

    (tmp_path / "RUNNER~1").mkdir()
    target = tmp_path / "RUNNER~1" / "new" / "deeper"
    out = long_path(target, platform="win32", expand=expand)
    assert seen == [str(tmp_path / "RUNNER~1")]  # only the existing part is handed to the OS call
    assert out == tmp_path / "runneradmin" / "new" / "deeper"
    assert "~" not in str(out)


def test_long_path_never_raises(tmp_path):
    def boom(p):
        raise OSError("nope")

    assert long_path(tmp_path, platform="win32", expand=boom) == tmp_path.absolute()


def test_tex_unsafe_characters_are_detected():
    assert tex_unsafe_chars("C:/Users/RUNNER~1/x") == "~"
    assert tex_unsafe_chars("C:/Users/me/50%/x#y") == "#%"
    assert tex_unsafe_chars("C:/Users/me/animatica smoke \u00fc/out") == ""  # spaces and non-ASCII are fine
    with pytest.raises(RuntimeError, match="LaTeX cannot handle"):
        check_tex_safe("C:/a~b")


def test_backend_refuses_a_tex_unsafe_output_folder_with_a_clear_message(tmp_path):
    from animatica.ai.template import TemplateMatcher
    from animatica.backends.base import RenderOptions
    from animatica.backends.manim_backend import ManimBackend

    sb = TemplateMatcher().match("make a title card about Hello")
    with pytest.raises(RuntimeError, match="output folder"):
        ManimBackend().render(sb, tmp_path / "bad~name", RenderOptions(quality="preview", captions=False))


def test_probe_uses_the_expanded_temp_dir(monkeypatch):
    import animatica.latex_check as lc

    monkeypatch.setattr(lc, "long_path", lambda p: Path(str(p) + "_LONG"))
    seen = {}

    class P:
        returncode = 0

    def run(cmd, **kw):
        seen["dir"] = cmd[-1]
        return P()

    ok, _, _ = lc.probe_latex(run=run)
    assert ok and seen["dir"].endswith("_LONG")
