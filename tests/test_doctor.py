from animatica.doctor import CheckResult, run_checks


def test_latex_missing_fix_mentions_tinytex():
    checks = run_checks(which=lambda cmd: None)
    latex = next(c for c in checks if c.name == "latex")
    assert latex.ok is False
    assert "tinytex" in latex.fix.lower()


def test_all_present_ok():
    def which(cmd):
        return "/usr/bin/" + cmd

    checks = run_checks(which=which, deep_latex=False)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_every_failed_check_has_a_fix():
    checks = run_checks(which=lambda cmd: None)
    for c in checks:
        if not c.ok:
            assert c.fix, f"{c.name} has no fix"


def test_checkresult_fields():
    c = CheckResult(name="manim", ok=True, detail="0.22.1", fix="")
    assert (c.name, c.ok, c.detail, c.fix) == ("manim", True, "0.22.1", "")

