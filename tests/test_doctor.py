from animatica.doctor import CheckResult, run_checks


def test_latex_missing_fix_mentions_tinytex():
    checks = run_checks(which=lambda cmd: None)
    latex = next(c for c in checks if c.name == "latex")
    assert latex.ok is False
    assert "tinytex" in latex.fix.lower()


def test_all_present_ok(tmp_path, monkeypatch):
    from animatica import narration

    monkeypatch.setattr(narration, "voice_model_file", lambda voice=narration.DEFAULT_VOICE: tmp_path / "v.onnx")
    (tmp_path / "v.onnx").write_text("fake", encoding="utf-8")

    def which(cmd):
        return "/usr/bin/" + cmd

    checks = run_checks(which=which, deep_latex=False)
    assert all(c.ok for c in checks), [c for c in checks if not c.ok]


def test_narration_check_reports_what_is_missing():
    checks = run_checks(which=lambda cmd: None, deep_latex=False)
    narration_check = next(c for c in checks if c.name == "narration")
    assert narration_check.ok is False
    assert "piper=no" in narration_check.detail and "voice=no" in narration_check.detail
    assert "doctor --fix" in narration_check.fix


def test_every_failed_check_has_a_fix():
    checks = run_checks(which=lambda cmd: None)
    for c in checks:
        if not c.ok:
            assert c.fix, f"{c.name} has no fix"


def test_checkresult_fields():
    c = CheckResult(name="manim", ok=True, detail="0.22.1", fix="")
    assert (c.name, c.ok, c.detail, c.fix) == ("manim", True, "0.22.1", "")



def test_doctor_json_is_machine_readable():
    import json

    from typer.testing import CliRunner

    from animatica.cli import app

    result = CliRunner().invoke(app, ["doctor", "--json"])
    payload = json.loads(result.stdout)  # must parse even when checks fail
    assert isinstance(payload, list) and payload
    for check in payload:
        assert set(check) == {"name", "ok", "detail", "fix"}
    latex = next(c for c in payload if c["name"] == "latex")
    assert isinstance(latex["ok"], bool)


def test_template_provider_needs_no_key(monkeypatch):
    """template is offline and keyless: provider check passes with no key."""
    from animatica.config import Config

    monkeypatch.setattr("animatica.doctor.load_config", lambda: Config(provider="template"))
    monkeypatch.setattr("animatica.doctor.load_key", lambda provider: None)
    checks = run_checks(which=lambda cmd: None, deep_latex=False)
    provider = next(c for c in checks if c.name == "provider")
    assert provider.ok is True, provider.detail


def test_ollama_provider_needs_no_key(monkeypatch):
    """ollama is local and keyless: provider check passes with no key."""
    from animatica.config import Config

    monkeypatch.setattr("animatica.doctor.load_config", lambda: Config(provider="ollama"))
    monkeypatch.setattr("animatica.doctor.load_key", lambda provider: None)
    checks = run_checks(which=lambda cmd: None, deep_latex=False)
    provider = next(c for c in checks if c.name == "provider")
    assert provider.ok is True, provider.detail


def test_keyed_provider_still_fails_without_key(monkeypatch):
    """groq needs a key: provider check fails when no key is stored."""
    from animatica.config import Config

    monkeypatch.setattr("animatica.doctor.load_config", lambda: Config(provider="groq"))
    monkeypatch.setattr("animatica.doctor.load_key", lambda provider: None)
    checks = run_checks(which=lambda cmd: None, deep_latex=False)
    provider = next(c for c in checks if c.name == "provider")
    assert provider.ok is False
    assert "key" in provider.detail.lower()
