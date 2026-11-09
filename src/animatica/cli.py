"""Command line entry point."""
from __future__ import annotations

import os
import sys

import typer
from pathlib import Path

from animatica import __version__
from animatica.ai.base import ProviderError, RateLimited, StoryboardGenerationError
from animatica.components.registry import ComponentRegistry
from animatica.doctor import run_checks
from animatica.cli_progress import TerminalProgress
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
    as_json: bool = typer.Option(
        False, "--json", help="Machine-readable output (used by the install scripts)."
    ),
) -> None:
    """Check Python, Manim, LaTeX, ffmpeg, encoders, and configured provider."""
    checks = run_checks()

    def report(results) -> int:
        if as_json:
            import json

            typer.echo(
                json.dumps(
                    [
                        {"name": c.name, "ok": c.ok, "detail": c.detail, "fix": c.fix}
                        for c in results
                    ],
                    indent=2,
                )
            )
            return sum(1 for c in results if not c.ok)
        return _print_checks(results)

    failures = report(checks)
    if fix and failures and _offer_fix(assume_yes=yes):
        if not as_json:
            typer.echo("\nRe-checking after fixes:")
        failures = report(run_checks())  # exit status reflects the state AFTER the fix attempt
    if failures:
        raise typer.Exit(code=1)
    if not as_json:
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
        typer.echo(
            "If it mentions cairo, pango or pycairo, this machine has no cairo/pango and "
            "nothing to compile them against.\n"
            "The one-line installer handles that case (it fetches a prebuilt copy):\n"
            "  curl -fsSL https://raw.githubusercontent.com/Abu103/animatica-manim/main/"
            "scripts/bootstrap.sh | bash"
        )
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


@app.command("preview")
def preview_cmd(
    video: Path = typer.Argument(..., help="Rendered video.mp4"),
    scene_index: int = typer.Argument(..., help="Scene index (0-based)"),
    t: float = typer.Argument(0.0, help="Seconds within the scene"),
    out: Path = typer.Option(None, "--out", "-o", help="Output PNG path (default: next to video)"),
    report: Path = typer.Option(None, "--report", help="Path to report.json for scene durations"),
) -> None:
    """Extract a single frame from a rendered video at scene+t.

    Scene durations are loaded from report.json (next to the video by default,
    or via --report). Use this to verify rendered output quality without
    writing code.
    """
    import json as _json

    from animatica.pipeline import preview_frame

    if not video.is_file():
        typer.echo(f"Error: video not found: {video}")
        raise typer.Exit(code=1)

    # Load scene durations from report.json
    scene_durations: list[float] = []
    report_path = report or (video.parent / "report.json")
    if report_path and report_path.is_file():
        try:
            report_data = _json.loads(report_path.read_text(encoding="utf-8"))
            scene_durations = report_data.get("stages", {}).get("durations", [])
        except Exception:
            scene_durations = []

    if not scene_durations:
        typer.echo(
            f"Error: no scene durations available. Pass --report with report.json "
            f"(looked for {report_path})."
        )
        raise typer.Exit(code=1)

    out_path = preview_frame(video, scene_durations, scene_index, t, out)
    typer.echo(f"Frame: {out_path}")


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
                        "provider_used": result_obj.provider_used,
                        "encoder_used": result_obj.encoder_used,
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


@app.command("tui")
def tui_cmd() -> None:
    """Launch the Animatica Terminal User Interface (TUI).

    Requires the optional 'textual' package:
        pip install 'animatica[tui]'

    Provides a guided, full-screen workflow: enter a prompt or pick a
    template, configure render settings, review before starting, watch
    progress, and open the finished video.
    """
    from animatica.tui import run_tui

    run_tui()


@app.command("edit")
def edit_cmd(
    out_dir: Path = typer.Argument(..., help="Output directory containing storyboard.json"),
    instruction: str = typer.Argument(..., help="Edit instruction, e.g. 'slow down scene 3'"),
    provider: str = typer.Option("auto", "--provider", help="AI provider for the edit"),
    preview: bool = typer.Option(False, "--preview", help="Preview quality (480p15)"),
    replace: bool = typer.Option(
        False, "--replace",
        help="Replace the original output directory with the new render (backups are kept). "
             "By default the new render goes to a fresh directory and the original is left untouched.",
    ),
) -> None:
    """AI-assisted storyboard edit: read storyboard.json, apply instruction, re-render.

    By default the new render is written to a fresh, uniquely-named output directory
    alongside ``out_dir``; the original storyboard/video/report/media are left untouched.
    With --replace, the new artifacts are promoted into ``out_dir`` using recoverable
    backups and rollback if anything fails.
    """
    import json as _json
    import shutil
    import tempfile
    import time

    from animatica.ai.base import StoryboardGenerationError
    from animatica.ai.router import get_provider
    from animatica.ai.repair import generate_storyboard
    from animatica.components.registry import default_registry
    from animatica.config import load_config
    from animatica.pipeline import MakeResult, make_video

    sb_path = out_dir / "storyboard.json"
    if not sb_path.is_file():
        typer.echo(f"Error: no storyboard.json in {out_dir}")
        raise typer.Exit(code=1)

    # Snapshot originals for preservation/rollback verification.
    # NOTE: We read only the storyboard JSON into memory. Large binary
    # artifacts (video, captions, report) are NOT loaded here to avoid
    # risking a memory-exhaustion fault during an already failure-prone
    # critical section. The rollback path relies on backing up the files
    # themselves, not on holding copies in RAM.
    original_storyboard_bytes = sb_path.read_bytes()
    original_video_path = out_dir / "video.mp4"
    original_report_path = out_dir / "report.json"
    original_captions_path = out_dir / "captions.vtt"
    original_media_path = out_dir / "media"
    original_media_exists = original_media_path.is_dir()

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

    # --- Generate and validate WITHOUT touching the original storyboard ---
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

    # --- Render into a secure staging directory on the same filesystem ---
    # Use mkdtemp so the name is unpredictable and we own the directory.
    # The directory is visible (not hidden) so the output location is
    # discoverable from the filesystem listing, while still being unique
    # and owned by us — no check-then-act race against existing paths.
    staging_dir = Path(tempfile.mkdtemp(prefix="animatica-edit-", dir=str(out_dir.parent)))
    staging_sb_path = staging_dir / "storyboard.json"
    dump_storyboard(new_sb, staging_sb_path)

    result: MakeResult | None = None
    try:
        result = make_video(
            storyboard_path=staging_sb_path,
            out_dir=staging_dir,
            preview=preview,
        )
    except Exception:
        # Render failed: clean up staging dir we created, originals untouched.
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise

    if result is None:
        shutil.rmtree(staging_dir, ignore_errors=True)
        raise RuntimeError("make_video returned no result")

    typer.echo(f"Provider: {result.provider_used}")
    typer.echo(f"Encoder: {result.encoder_used}")

    # --- Decide output destination ---
    if replace:
        # Recoverable promotion: back up existing outputs, promote new ones,
        # roll back on any failure. Backups are preserved after success so
        # the user can recover if the promotion was unexpected.
        _promote_edit_artifacts_with_backup(staging_dir, out_dir)
        out_video = out_dir / "video.mp4"
    else:
        # Default: leave original untouched. The staging directory created by
        # mkdtemp is already unique and owned by us; use it directly as the
        # output rather than renaming it, which would introduce a
        # check-then-act race against any pre-existing path at the candidate
        # destination. No existing directory is ever deleted or overwritten.
        new_out_dir = staging_dir
        out_video = new_out_dir / "video.mp4"

    typer.echo(f"Video: {out_video}")
    for w in result.warnings:
        typer.echo(f"Warning: {w}")


def _promote_edit_artifacts_with_backup(staging_dir: Path, out_dir: Path) -> None:
    """Promote rendered artifacts from staging_dir into out_dir with backups + rollback.

    Backs up each existing artifact (storyboard.json, video.mp4, captions.vtt,
    report.json, media/) to a timestamped backup directory before overwriting.
    If any step fails, backed-up originals are restored and any newly created
    artifacts are removed. The backup directory is preserved for manual recovery.
    """
    import shutil
    import time

    artifacts = ["storyboard.json", "video.mp4", "captions.vtt", "report.json"]
    stamp = int(time.time() * 1000)
    backup_dir = out_dir.parent / f"{out_dir.name}.edit-backup-{stamp}"

    # Track which artifacts existed before promotion so rollback can
    # distinguish "restore original" from "remove newly created".
    pre_existing: set[str] = set()
    media_pre_existed = False

    # Create backups of everything that exists in out_dir.
    backed_up: list[tuple[Path, Path]] = []  # (backup_path, original_path)
    try:
        backup_dir.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        raise RuntimeError(f"backup directory already exists: {backup_dir}")

    try:
        # Record pre-existence before overwriting anything.
        for artifact in artifacts:
            if (out_dir / artifact).is_file():
                pre_existing.add(artifact)
        media_pre_existed = (out_dir / "media").is_dir()

        for artifact in artifacts:
            src = staging_dir / artifact
            dst = out_dir / artifact
            if src.is_file():
                if dst.is_file():
                    shutil.copy2(dst, backup_dir / artifact)
                    backed_up.append((backup_dir / artifact, dst))
                shutil.copy2(src, dst)

        staging_media = staging_dir / "media"
        dst_media = out_dir / "media"
        if staging_media.is_dir():
            if dst_media.exists():
                shutil.copytree(dst_media, backup_dir / "media")
                backed_up.append((backup_dir / "media", dst_media))
                shutil.rmtree(dst_media)
            shutil.copytree(staging_media, dst_media)
    except Exception:
        # Rollback: restore backed-up originals first.
        for backup_path, original_path in backed_up:
            try:
                if backup_path.is_dir():
                    if original_path.exists():
                        shutil.rmtree(original_path, ignore_errors=True)
                    shutil.copytree(backup_path, original_path)
                elif backup_path.is_file():
                    shutil.copy2(backup_path, original_path)
            except Exception as exc:
                # Surface rollback failures clearly so the operator is not
                # left wondering why the original is missing or corrupted.
                # The backup directory is NOT deleted here, because we cannot
                # yet confirm the original is intact.
                typer.echo(
                    f"Warning: rollback failed for {original_path}: {exc}. "
                    f"Backups preserved under {backup_dir} for manual recovery."
                )
        # Remove any artifacts that were newly created (did not exist before
        # promotion) so a failed promotion leaves out_dir as it was.
        for artifact in artifacts:
            dst = out_dir / artifact
            if artifact not in pre_existing and dst.is_file():
                dst.unlink(missing_ok=True)
        # Remove newly created media directory if it didn't exist before.
        if not media_pre_existed:
            dst_media = out_dir / "media"
            if dst_media.is_dir():
                shutil.rmtree(dst_media, ignore_errors=True)
        raise

    # Promotion succeeded: leave the backup in place so the user can
    # verify the result before deciding to discard it or roll back.
    # (The '--replace' mode is opt-in precisely because in-place
    # replacement carries risk; the backup preserves recoverability.)


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
    frame_lint: bool = typer.Option(True, "--frame-lint/--no-frame-lint", help="Run non-fatal frame-quality checks on the rendered video"),
    vertical: bool = typer.Option(False, "--vertical", help="9:16 vertical aspect ratio for mobile/social"),
    theme: str = typer.Option(None, "--theme", help="Color theme: dark-blue, light, high-contrast"),
    progress: bool = typer.Option(
        True,
        "--progress/--no-progress",
        help="Live progress line on stderr (only real render units; off in non-interactive shells)",
    ),
) -> None:
    """Turn a plain-language prompt into an explainer video."""
    if model:
        os.environ["ANIMATICA_MODEL"] = model
    reporter = TerminalProgress(enabled=progress and sys.stderr.isatty()).start()
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
            theme=theme,
            on_progress=reporter,
        )
        typer.echo(f"Provider: {result.provider_used}")
        typer.echo(f"Encoder: {result.encoder_used}")
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
    finally:
        # a half-drawn progress line must never swallow the next shell prompt
        reporter.close()



if __name__ == "__main__":
    app()
