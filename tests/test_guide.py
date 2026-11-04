from typer.testing import CliRunner

from animatica.cli import app


def test_guide_contains_all_section_headings():
    runner = CliRunner()
    result = runner.invoke(app, ["guide"])
    assert result.exit_code == 0, result.output
    text = result.output
    headings = [
        "What this does",
        "What you need",
        "Install",
        "Virtual environment",
        "Run animatica doctor",
        "Your first video",
        "Writing good prompts",
        "Getting a free API key",
        "Editing storyboard.json",
        "Troubleshooting",
        "Glossary",
    ]
    for h in headings:
        assert h in text, f"missing heading: {h}"
    # mentions py -m for Windows
    assert "py -m" in text
    # mentions every CLI command
    for cmd in ["setup", "doctor", "make", "templates", "guide"]:
        assert cmd in text

