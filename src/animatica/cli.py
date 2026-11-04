"""Command line entry point."""
from __future__ import annotations

import os

import typer
from pathlib import Path

from animatica import __version__
from animatica.ai.base import ProviderError, RateLimited, StoryboardGenerationError
from animatica.doctor import run_checks
from animatica.pipeline import make_video
from animatica.setup_wizard import setup

app = typer.Typer(add_completion=False, help="Turn a plain-language prompt into an explainer video.")


def _version(value: bool) -> None:
    if value:
        typer.echo(f"animatica {__version__}")
        raise typer.Exit()


@app.callback()
def main(
    version: bool = typer.Option(False, "--version", callback=_version, is_eager=True, help="Show version."),
) -> None:
    """Animatica command group."""


@app.command()
def doctor(fix: bool = typer.Option(False, "--fix", help="Offer to auto-fix missing dependencies.")) -> None:
    """Check Python, Manim, LaTeX, ffmpeg, encoders, and configured provider."""
    checks = run_checks()
    failures = 0
    for c in checks:
        mark = "OK " if c.ok else "FAIL"
        typer.echo(f"[{mark}] {c.name}: {c.detail}")
        if not c.ok:
            failures += 1
            if c.fix:
                typer.echo(f"       fix: {c.fix}")
        elif c.fix:  # passed, but there is something worth knowing
            typer.echo(f"       tip: {c.fix}")
    if fix and failures:
        _offer_fix()
    if failures:
        raise typer.Exit(code=1)
    typer.echo("\nAll checks passed.")


def _offer_fix() -> None:
    from animatica.doctor import fix_dependencies

    ans = typer.prompt(
        "Auto-install missing dependencies now (ffmpeg, TinyTeX + TeX packages)? (y/N)",
        default="N", show_default=False,
    ).strip().lower()
    if ans != "y":
        typer.echo("No changes made. Re-run 'animatica doctor --fix' any time.")
        return
    for line in fix_dependencies():
        typer.echo(line)
    typer.echo("\nRe-run 'animatica doctor' to verify (restart your terminal first so PATH updates apply).")


@app.command()
def bootstrap() -> None:
    """One-command setup: install Animatica deps, ffmpeg, and TinyTeX + required TeX packages."""
    import subprocess
    import sys

    from animatica.doctor import fix_dependencies

    typer.echo("[1/2] pip install -e . (animatica + deps incl. manim)")
    subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=False)
    typer.echo("[2/2] system dependencies")
    for line in fix_dependencies():
        typer.echo(line)
    typer.echo("\nDone. Restart your terminal, then run: animatica doctor")


@app.command("setup")
def setup_cmd() -> None:
    """Interactive setup: choose provider, store a key, run doctor checks."""
    setup()


@app.command()
def guide() -> None:
    """Print the beginner quick-start guide."""
    here = Path(__file__).resolve()
    candidates = [
        here.parent.parent.parent / "docs" / "GUIDE.md",
        here.parent / "docs" / "GUIDE.md",
    ]
    text = None
    for p in candidates:
        if p.exists():
            text = p.read_text(encoding="utf-8")
            break
    if text is None:
        typer.echo("Guide not found. Install Animatica docs (docs/GUIDE.md).")
        raise typer.Exit(code=1)
    typer.echo(text)


@app.command("new-component")
def new_component(
    name: str = typer.Argument(..., help="Component name in snake_case, e.g. number_line"),
    root: Path = typer.Option(Path("."), "--root", help="Project root to scaffold into"),
) -> None:
    """Scaffold a new component: module, registry entry, docs row, test, conformance JSON."""
    from animatica.scaffold import scaffold_component

    try:
        created = scaffold_component(name, root)
    except ValueError as exc:
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
    typer.echo(f"Scaffolded component {name!r}:")
    for p in created:
        typer.echo(f"  {p}")
    typer.echo("Fill in the TODOs (params, duration, play), then run pytest -q.")


@app.command()
def eval_cmd(
    provider: str = typer.Option("auto", "--provider", help="AI provider to evaluate"),
    prompts_file: Path = typer.Option(Path("tests/reference_prompts.txt"), "--prompts", help="One prompt per line"),
    max_retries: int = typer.Option(2, "--max-retries"),
) -> None:
    """Run reference prompts through storyboard generation and print a score table."""
    from animatica.ai.router import get_provider
    from animatica.components.registry import default_registry
    from animatica.config import load_config
    from animatica.eval import run_eval

    prompts = [l.strip() for l in prompts_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    prov = get_provider(provider, load_config())
    if prov is None:
        typer.echo("Error: no AI provider available; run 'animatica setup' or pass --provider")
        raise typer.Exit(code=1)
    typer.echo(run_eval(prompts, prov, default_registry(), max_retries=max_retries, as_table=True))


@app.command("list-components")
def list_components() -> None:
    """JSON list of registered component names (agent tool)."""
    import json as _json

    from animatica.components.registry import default_registry

    typer.echo(_json.dumps(default_registry().names()))


@app.command("component-schema")
def component_schema(name: str) -> None:
    """JSON schema of one component's params (agent tool)."""
    import json as _json

    from animatica.components.registry import default_registry

    reg = default_registry()
    if name not in reg.names():
        typer.echo(f"Error: unknown component {name!r}")
        raise typer.Exit(code=1)
    typer.echo(_json.dumps(reg.get(name).Params.model_json_schema(), indent=2))


@app.command()
def validate(storyboard: Path = typer.Argument(..., help="storyboard.json to validate")) -> None:
    """Validate a storyboard; prints a JSON list of errors (empty = valid)."""
    import json as _json

    from animatica.components.registry import default_registry
    from animatica.storyboard.models import load_storyboard

    try:
        sb = load_storyboard(storyboard)
    except Exception as exc:
        typer.echo(_json.dumps([f"load error: {exc}"]))
        raise typer.Exit(code=0)
    typer.echo(_json.dumps(default_registry().validate(sb), indent=2))


@app.command()
def lint(storyboard: Path = typer.Argument(..., help="model-written storyboard.json to lint")) -> None:
    """Lint a storyboard; prints JSON {storyboard, notes} (agent tool)."""
    import json as _json

    from animatica.storyboard.lint import lint_storyboard
    from animatica.storyboard.models import load_storyboard

    sb, notes = lint_storyboard(load_storyboard(storyboard))
    typer.echo(_json.dumps({"storyboard": _json.loads(sb.model_dump_json()), "notes": notes}, indent=2))


@app.command()
def make(
    prompt: str = typer.Argument("", help="Prompt to render into a video"),
    out_dir: Path = typer.Option(Path("."), "-o", "--output", help="Output directory"),
    preview: bool = typer.Option(False, "--preview", help="Preview quality (480p15)"),
    quality: str = typer.Option("standard", "--quality", help="preview/standard/high"),
    encoder: str = typer.Option("auto", "--encoder", help="Video encoder (auto/x264/hardware)"),
    provider: str = typer.Option("auto", "--provider", help="AI provider (auto/template/groq/...)"),
    from_storyboard: Path | None = typer.Option(None, "--from", help="Render an existing storyboard.json"),
    captions: bool = typer.Option(True, "--captions/--no-captions", help="Burn captions into the video"),
    debug: bool = typer.Option(False, "--debug", help="Show tracebacks on errors"),
    two_stage: bool = typer.Option(False, "--two-stage", help="Two-stage AI generation: outline, then fill each scene"),
    model: str | None = typer.Option(None, "--model", help="Override the AI model id for the chosen provider"),
) -> None:
    """Turn a plain-language prompt into an explainer video."""
    if model:
        os.environ["ANIMATICA_MODEL"] = model
    try:
        result = make_video(
            prompt=prompt or None,
            storyboard_path=from_storyboard,
            out_dir=out_dir,
            preview=preview,
            quality=quality,
            encoder=encoder,
            provider=provider,
            captions=captions,
            two_stage=two_stage,
        )
        typer.echo(f"Video: {result.video}")
        for w in result.warnings:
            typer.echo(f"Warning: {w}")
        if result.warnings:
            typer.echo(f"({len(result.warnings)} warning(s); details in {result.report})")
    except StoryboardGenerationError as exc:
        if debug:
            raise
        typer.echo(f"Error: {exc}")
        for line in exc.errors[:6]:
            typer.echo(f"  - {line}")
        typer.echo("Tip: try again, pick another --provider/model, or use --debug for the full traceback.")
        raise typer.Exit(code=1)
    except (ProviderError, RateLimited) as exc:
        if debug:
            raise
        typer.echo(f"Error: {exc}")
        raise typer.Exit(code=1)
    except ValueError as exc:
        msg = str(exc)
        if debug:
            raise
        if "invalid storyboard" in msg:
            typer.echo(msg)
            raise typer.Exit(code=2)
        typer.echo(f"Error: {msg}")
        raise typer.Exit(code=1)
    except Exception as exc:  # unexpected: keep the terminal readable unless --debug
        if debug:
            raise
        typer.echo(f"Error: {type(exc).__name__}: {exc}")
        typer.echo("Re-run with --debug for the full traceback.")
        raise typer.Exit(code=1)

