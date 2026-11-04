from typer.testing import CliRunner

from animatica.cli import app


def test_version():
    r = CliRunner().invoke(app, ["--version"])
    assert r.exit_code == 0
    assert "animatica" in r.output.lower()

