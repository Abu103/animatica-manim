"""Command line entry point."""
from __future__ import annotations

import os

import typer
from pathlib import Path

from animatica import __version__
from animatica.ai.base import ProviderError, RateLimited, StoryboardGenerationError
from animatica.components.registry import ComponentRegistry
from animatica.doctor import run_checks
from animatica.pipeline import MakeResult, make_video
from animatica.setup_wizard import setup
from animatica.storyboard.models import load_storyboard, dump_storyboard

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
    # TinyTeX may be installed but not on this shell's PATH (a child installer cannot change it).
    from animatica.doctor import ensure_tex_on_path

    ensure_tex_on_path()


def _print_checks(checks) -> int:
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
    return failures


@app.command()
def doctor(
    fix: bool = typer.Option(False, "--fix", help="Offer to auto-fix missing dependencies."),
    yes: bool = typer.Option(False, "--yes", "-y", help="With --fix: do not prompt (for scripts/CI)."),
) -> None:
    """Check Python, Manim, LaTeX, ffmpeg, encoders, and configured provider."""
    failures = _print_checks(run_checks())
    if fix and failures and _offer_fix(assume_yes=yes):
        typer.echo("\nRe-checking after fixes:")
        failures = _print_checks(run_checks())  # exit status reflects the state AFTER the fix attempt
    if failures:
        raise typer.Exit(code=1)
    typer.echo("\nAll checks passed.")


def _offer_fix(assume_yes: bool = False) -> bool:
    """Ask (unless assume_yes), then attempt fixes. Returns True only if fixes were attempted."""
    from animatica.doctor import fix_dependencies

    ans = "y" if assume_yes else typer.prompt(
        "Auto-install missing dependencies now (ffmpeg, TinyTeX + TeX packages)? (y/N)",
        default="N", show_default=False,
    ).strip().lower()
    if ans != "y":
        typer.echo("No changes made. Re-run 'animatica doctor --fix' any time.")
        return False
    for line in fix_dependencies():
        typer.echo(line)
    return True


@app.command()
def bootstrap() -> None:
    """One-command setup: install Animatica deps, ffmpeg, and TinyTeX + required TeX packages."""
    import subprocess
    import sys

    from animatica.doctor import fix_dependencies

    typer.echo("[1/3] pip install -e . (animatica + deps incl. manim)")
    pip = subprocess.run([sys.executable, "-m", "pip", "install", "-e", "."], check=False)
    if pip.returncode != 0:
        typer.echo(f"pip install failed (exit {pip.returncode}); fix that first, then re-run.")
        raise typer.Exit(code=pip.returncode or 1)
    typer.echo("[2/3] system dependencies")
    for line in fix_dependencies():
        typer.echo(line)
    typer.echo("[3/3] verifying")
    failures = _print_checks(run_checks())
    if failures:
        typer.echo("\nSetup is NOT complete; see the FAIL lines above.")
        raise typer.Exit(code=1)
    typer.echo("\nDone. All checks passed.")


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


@app.command("eval")
def eval_cmd(
    provider: str = typer.Option("auto", "--provider", help="AI provider to evaluate (single-provider mode)"),
    models: str = typer.Option(None, "--models", help="Comma-separated providers for multi-provider comparison (Phase 2.1)"),
    prompts_file: Path = typer.Option(Path("tests/reference_prompts.txt"), "--prompts", help="One prompt per line"),
    max_retries: int = typer.Option(2, "--max-retries"),
) -> None:
    """Run reference prompts through storyboard generation and print a score table."""
    from animatica.ai.router import get_provider
    from animatica.components.registry import default_registry
    from animatica.config import load_config
    from animatica.eval import format_multi_table, format_table, run_eval, run_eval_multi

    prompts = [l.strip() for l in prompts_file.read_text(encoding="utf-8").splitlines() if l.strip() and not l.startswith("#")]
    registry = default_registry()
    cfg = load_config()

    if models:
        # Phase 2.1: multi-provider comparison
        model_list = [m.strip() for m in models.split(",") if m.strip()]
        providers = []
        for m in model_list:
            prov = get_provider(m, cfg)
            if prov is None:
                typer.echo(f"Error: no AI provider available for {m!r}; run 'animatica setup' or check the provider name")
                raise typer.Exit(code=1)
            providers.append(prov)
        summary = run_eval_multi(prompts, providers, registry, max_retries=max_retries)
        typer.echo(format_multi_table(summary))
    else:
        # P1.2: single-provider eval
        prov = get_provider(provider, cfg)
        if prov is None:
            typer.echo("Error: no AI provider available; run 'animatica setup' or pass --provider")
            raise typer.Exit(code=1)
        typer.echo(run_eval(prompts, prov, registry, max_retries=max_retries, as_table=True))


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


@app.command("lint")
def lint(storyboard: Path = typer.Argument(..., help="model-written storyboard.json to lint")) -> None:
    """Lint a storyboard; prints JSON {storyboard, notes} (agent tool)."""
    import json as _json

    from animatica.storyboard.lint import lint_storyboard
    from animatica.storyboard.models import load_storyboard

    sb, notes = lint_storyboard(load_storyboard(storyboard))
    typer.echo(_json.dumps({"storyboard": _json.loads(sb.model_dump_json()), "notes": notes}, indent=2))


@app.command("mcp")
def mcp() -> None:
    """Run the Animatica MCP server on stdio (Model Context Protocol).

    Exposes tools: list_components, component_schema, validate_storyboard,
    render_storyboard, preview_frame, lint_video.
    Hermes (or any MCP client) connects via stdio and calls tools via JSON-RPC.
    """
    import asyncio
    import sys

    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import (
        CallToolRequestParams,
        CallToolResult,
        ListToolsRequest,
        ListToolsResult,
        PaginatedRequestParams,
        TextContent,
        Tool,
    )

    from animatica.components.registry import default_registry
    from animatica.frame_lint import FrameLintConfig, lint_video, lint_result_to_warnings
    from animatica.pipeline import MakeResult, make_video, preview_frame
    from animatica.storyboard.lint import lint_storyboard
    from animatica.storyboard.models import load_storyboard

    reg = default_registry()
    server = Server("animatica")

    # ------------------------------------------------------------------
    # Tool definitions (MCP protocol)
    # ------------------------------------------------------------------

    TOOL_DEFS = [
        Tool(
            name="list_components",
            description="List all registered component names",
            input_schema={"type": "object", "properties": {}, "additionalProperties": False},
        ),
        Tool(
            name="component_schema",
            description="Get the JSON params schema for a component",
            input_schema={
                "type": "object",
                "properties": {"name": {"type": "string", "description": "Component name"}},
                "required": ["name"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="validate_storyboard",
            description="Validate a storyboard JSON file; returns errors if invalid",
            input_schema={
                "type": "object",
                "properties": {"path": {"type": "string", "description": "Path to storyboard.json"}},
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="render_storyboard",
            description="Render a storyboard JSON file into a video",
            input_schema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to storyboard.json"},
                    "out_dir": {"type": "string", "description": "Output directory", "default": "."},
                    "preview": {"type": "boolean", "description": "Preview quality", "default": False},
                },
                "required": ["path"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="preview_frame",
            description="Extract a single frame from a rendered video at scene+t",
            input_schema={
                "type": "object",
                "properties": {
                    "video": {"type": "string", "description": "Path to video.mp4"},
                    "scene_index": {"type": "integer", "description": "Scene index"},
                    "t": {"type": "number", "description": "Seconds within the scene", "default": 0.0},
                    "out": {"type": "string", "description": "Output PNG path (optional)"},
                },
                "required": ["video", "scene_index"],
                "additionalProperties": False,
            },
        ),
        Tool(
            name="lint_video",
            description="Run frame-level quality checks on a rendered video",
            input_schema={
                "type": "object",
                "properties": {
                    "video": {"type": "string", "description": "Path to video.mp4"},
                    "scene_durations": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Per-scene durations in seconds",
                        "default": [],
                    },
                },
                "required": ["video"],
                "additionalProperties": False,
            },
        ),
    ]

    async def handle_list_tools(_ctx: object, _request: PaginatedRequestParams) -> ListToolsResult:
        return ListToolsResult(tools=TOOL_DEFS)

    server.add_request_handler(
        "tools/list",
        PaginatedRequestParams,
        handle_list_tools,
    )

    async def handle_call_tool(_ctx: object, request: CallToolRequestParams) -> CallToolResult:
        import json as _json
        from pathlib import Path as _Path

        name = request.name
        arguments = request.arguments or {}

        try:
            if name == "list_components":
                structured = {"components": reg.names()}
            elif name == "component_schema":
                comp_name = arguments.get("name")
                if comp_name not in reg.names():
                    structured = {"error": f"unknown component {comp_name!r}"}
                else:
                    structured = {"schema": reg.get(comp_name).Params.model_json_schema()}
            elif name == "validate_storyboard":
                path = arguments.get("path")
                if not path:
                    structured = {"error": "missing 'path' argument"}
                else:
                    sb = load_storyboard(_Path(path))
                    errors = reg.validate(sb)
                    structured = {"valid": not errors, "errors": errors}
            elif name == "render_storyboard":
                path = arguments.get("path")
                out_dir = arguments.get("out_dir", ".")
                preview = arguments.get("preview", False)
                if not path:
                    structured = {"error": "missing 'path' argument"}
                else:
                    result_obj: MakeResult = make_video(
                        storyboard_path=_Path(path),
                        out_dir=_Path(out_dir),
                        preview=preview,
                    )
                    structured = {
                        "video": str(result_obj.video),
                        "storyboard": str(result_obj.storyboard),
                        "captions": str(result_obj.captions),
                        "report": str(result_obj.report),
                        "warnings": result_obj.warnings,
                    }
            elif name == "preview_frame":
                video = arguments.get("video")
                scene_index = arguments.get("scene_index")
                t = arguments.get("t", 0.0)
                out = arguments.get("out")
                if not video:
                    structured = {"error": "missing 'video' argument"}
                elif scene_index is None:
                    structured = {"error": "missing 'scene_index' argument"}
                else:
                    vp = _Path(video)
                    rp = vp.parent / "report.json"
                    durations: list[float] = []
                    if rp.is_file():
                        try:
                            durations = (
                                _json.loads(rp.read_text(encoding="utf-8"))
                                .get("stages", {})
                                .get("durations", [])
                            )
                        except Exception:
                            durations = []
                    out_path = preview_frame(
                        vp,
                        durations,
                        int(scene_index),
                        float(t),
                        _Path(out) if out else None,
                    )
                    structured = {"frame": str(out_path)}
            elif name == "lint_video":
                video = arguments.get("video")
                scene_durations = arguments.get("scene_durations", [])
                if not video:
                    structured = {"error": "missing 'video' argument"}
                else:
                    lint_result = lint_video(
                        video,
                        scene_durations,
                        FrameLintConfig(enabled=True),
                    )
                    structured = {
                        "findings": [f.__dict__ for f in lint_result.findings],
                        "warnings": lint_result_to_warnings(lint_result),
                    }
            else:
                structured = {"error": f"unknown tool {name!r}"}
        except Exception as exc:  # noqa: BLE001 - MCP surface must never crash
            structured = {"error": f"tool {name} failed: {type(exc).__name__}: {exc}"}

        is_error = isinstance(structured, dict) and "error" in structured
        return CallToolResult(
            content=[TextContent(type="text", text=_json.dumps(structured))],
            structured_content=structured,
            is_error=is_error,
        )

    server.add_request_handler(
        "tools/call",
        CallToolRequestParams,
        handle_call_tool,
    )

    async def _run() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(
                read_stream,
                write_stream,
                server.create_initialization_options(),
            )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:  # pragma: no cover - stdio server
        pass
    except BrokenPipeError:  # pragma: no cover - client disconnected
        pass


@app.command("edit")
def edit_cmd(
    out_dir: Path = typer.Argument(..., help="Output directory containing storyboard.json"),
    instruction: str = typer.Argument(..., help="Edit instruction, e.g. 'slow down scene 3'"),
    provider: str = typer.Option("auto", "--provider", help="AI provider for the edit"),
    preview: bool = typer.Option(False, "--preview", help="Preview quality (480p15)"),
) -> None:
    """AI-assisted storyboard edit: read storyboard.json, apply instruction, re-render."""
    import json as _json

    from animatica.ai.router import get_provider
    from animatica.ai.repair import generate_storyboard
    from animatica.components.registry import default_registry
    from animatica.config import load_config
    from animatica.pipeline import MakeResult, make_video

    sb_path = out_dir / "storyboard.json"
    if not sb_path.is_file():
        typer.echo(f"Error: no storyboard.json in {out_dir}")
        raise typer.Exit(code=1)

    sb = load_storyboard(sb_path)
    reg = default_registry()
    cfg = load_config()
    prov = get_provider(provider, cfg)
    if prov is None:
        typer.echo("Error: no AI provider available; run 'animatica setup' or pass --provider")
        raise typer.Exit(code=1)

    # Build an edit prompt: current storyboard + instruction -> corrected storyboard
    edit_prompt = (
        "You are editing an explainer-video storyboard. Reply with ONE JSON object and nothing else.\n"
        "\n"
        "Current storyboard:\n"
        + _json.dumps(_json.loads(sb.model_dump_json()), indent=2)
        + "\n"
        "\n"
        "Edit instruction: "
        + instruction
        + "\n"
        "\n"
        "Rules:\n"
        "- Preserve the version, title, and scene structure unless the instruction changes them.\n"
        "- Only change what the instruction asks for; keep everything else identical.\n"
        "- Use ONLY components from the registry with exactly the params their schema allows.\n"
        "- 1 to 12 scenes; each scene 1 to 8 beats.\n"
        "- Every text value at most 300 characters.\n"
        "- One-sentence caption per beat describing only what the component draws.\n"
        "\n"
        "Components:\n"
        + _catalog(reg)
    )

    try:
        new_sb = generate_storyboard(edit_prompt, prov, reg, max_retries=2)
    except StoryboardGenerationError as exc:
        typer.echo(f"Error: {exc}")
        for line in exc.errors[:6]:
            typer.echo(f"  - {line}")
        raise typer.Exit(code=1)

    errors = reg.validate(new_sb)
    if errors:
        typer.echo("Error: edited storyboard failed validation:")
        for e in errors[:6]:
            typer.echo(f"  - {e}")
        raise typer.Exit(code=1)

    # Write edited storyboard and re-render
    dump_storyboard(new_sb, sb_path)
    result: MakeResult = make_video(
        storyboard_path=sb_path,
        out_dir=out_dir,
        preview=preview,
    )
    typer.echo(f"Video: {result.video}")
    for w in result.warnings:
        typer.echo(f"Warning: {w}")


def _catalog(registry: ComponentRegistry) -> str:
    """Render the component catalog as text for the edit prompt."""
    import json as _json

    lines = []
    for name, schema in registry.json_schema().items():
        schema = {k: v for k, v in schema.items() if k not in ("title", "description")}
        lines.append(f"- {name}: params schema: {_json.dumps(schema, separators=(',', ':'))}")
    return "\n".join(lines)


@app.command("make")
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
    backend: str = typer.Option("manim", "--backend", help="Renderer backend (manim, or any registered backend)"),
    jobs: int = typer.Option(1, "--jobs", min=1, help="Render scenes in parallel (1 = serial; each scene is already a subprocess)"),
    frame_lint: bool = typer.Option(False, "--frame-lint/--no-frame-lint", help="Run non-fatal frame-quality checks on the rendered video"),
    vertical: bool = typer.Option(False, "--vertical", help="9:16 vertical aspect ratio for mobile/social"),
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
            backend=backend,
            jobs=jobs,
            frame_lint=frame_lint,
            vertical=vertical,
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



if __name__ == "__main__":
    app()
