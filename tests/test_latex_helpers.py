from pathlib import Path

from animatica.components._latex import explain_latex_failure, latex_to_markup, latex_to_plain
from animatica.latex_check import probe_latex

STANDALONE_LOG = "! LaTeX Error: File `standalone.cls' not found.\n\nType X to quit\n"
BABEL_LOG = "! Package babel Error: Unknown option 'english'. Either you misspelled it\n"


def test_subscripts_and_superscripts_become_markup():
    assert latex_to_markup("F_{n-1} + F_{n-2}") == "F<sub>n-1</sub> + F<sub>n-2</sub>"
    assert latex_to_markup("a^2 + b^2 = c^2") == "a<sup>2</sup> + b<sup>2</sup> = c<sup>2</sup>"


def test_symbols_fractions_and_escaping():
    assert latex_to_markup(r"\alpha \cdot \beta") == "α · β"
    assert latex_to_markup(r"\frac{a}{b}") == "a/b"
    assert latex_to_markup(r"\frac{n(n+1)}{2}") == "(n(n+1))/2"
    assert latex_to_markup("x < y & z") == "x &lt; y &amp; z"
    assert latex_to_markup(r"\sqrt{x}") == "√(x)"


def test_plain_text_form_is_readable():
    assert latex_to_plain("F_{n-1} + F_{n-2}") == "F_(n-1) + F_(n-2)"
    assert latex_to_plain("a^2") == "a^2"


def test_unbalanced_or_odd_input_never_raises():
    for s in ["{{{", "}}}", "\\", "x_", "^", r"\frac{1}", r"\unknowncmd{x}"]:
        latex_to_markup(s)
        latex_to_plain(s)


def test_explain_failure_names_missing_package(tmp_path):
    log = tmp_path / "a.log"
    log.write_text(STANDALONE_LOG)
    msg = explain_latex_failure(ValueError(f"latex error converting to dvi. See log output above or the log file: {log}"))
    assert "standalone.cls" in msg and "tlmgr install standalone" in msg


def test_explain_failure_detects_babel_english(tmp_path):
    log = tmp_path / "b.log"
    log.write_text(BABEL_LOG)
    msg = explain_latex_failure(ValueError(f"latex error converting to dvi. See log output above or the log file: {log}"))
    assert "babel-english" in msg


def test_explain_failure_without_log_points_to_doctor():
    assert "animatica doctor" in explain_latex_failure(RuntimeError("boom"))


class _Proc:
    def __init__(self, rc, err=""):
        self.returncode, self.stderr = rc, err


def test_probe_latex_ok():
    ok, _, pk = probe_latex(run=lambda *a, **k: _Proc(0))
    assert ok and pk == []


def test_probe_latex_reports_missing_package_from_log():
    def fake_run(cmd, **kw):
        tmp = Path(cmd[-1])
        (tmp / "Tex").mkdir(parents=True, exist_ok=True)
        (tmp / "Tex" / "x.log").write_text(STANDALONE_LOG)
        return _Proc(1)

    ok, reason, packages = probe_latex(run=fake_run)
    assert not ok and "standalone.cls" in reason and "standalone" in packages


def test_probe_latex_survives_runner_crash():
    def boom(*a, **k):
        raise TimeoutError

    ok, reason, _ = probe_latex(run=boom)
    assert not ok and "TimeoutError" in reason

