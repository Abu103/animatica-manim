"""Test that animatica mcp implements the real MCP protocol over stdio.

Tests use plain asyncio (no pytest_asyncio dependency) so they run under
CI with just `pip install -e . pytest`. The mcp package (a main dependency)
provides both the server and client SDK.
"""
import asyncio
import os
import sys


from mcp.client.stdio import stdio_client
from mcp import ClientSession, StdioServerParameters


async def _run_mcp_session(test_fn):
    """Start the animatica mcp server, run `test_fn(session)`, then shut down."""
    params = StdioServerParameters(
        command=sys.executable,
        args=["-m", "animatica", "mcp"],
        # The stdio transport filters the environment down to PATH/HOME/...,
        # which drops PYTHONPATH and the native-library path the server needs.
        env={**os.environ},
    )
    async with stdio_client(params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            await test_fn(session)


# ---------------------------------------------------------------------------
# MCP SDK client tests (official SDK, stdio transport)
# ---------------------------------------------------------------------------

def test_mcp_initialize_and_tools_list():
    async def check(session):
        tools = await session.list_tools()
        tool_names = {t.name for t in tools.tools}
        expected = {"list_components", "component_schema", "validate_storyboard",
                    "render_storyboard", "preview_frame", "lint_video"}
        assert expected <= tool_names, f"missing tools: {expected - tool_names}"

    asyncio.run(_run_mcp_session(check))


def test_mcp_call_list_components():
    async def check(session):
        result = await session.call_tool("list_components", {})
        assert result.structured_content is not None
        assert "components" in result.structured_content
        assert "bounce_sequence" in result.structured_content["components"]

    asyncio.run(_run_mcp_session(check))


def test_mcp_call_component_schema():
    async def check(session):
        result = await session.call_tool("component_schema",
                                         {"name": "bounce_sequence"})
        assert result.structured_content is not None
        assert "schema" in result.structured_content
        assert result.structured_content["schema"].get(
            "properties", {}).get("values") is not None

    asyncio.run(_run_mcp_session(check))


def test_mcp_call_validate_storyboard_valid():
    async def check(session):
        result = await session.call_tool("validate_storyboard",
                                         {"path": "docs/gallery/howto.json"})
        assert result.structured_content is not None
        assert result.structured_content.get("valid") is True

    asyncio.run(_run_mcp_session(check))


def test_mcp_call_validate_storyboard_invalid_path():
    async def check(session):
        result = await session.call_tool("validate_storyboard",
                                         {"path": "/nonexistent/foo.json"})
        assert result.structured_content is not None
        assert "error" in result.structured_content

    asyncio.run(_run_mcp_session(check))


def test_mcp_call_unknown_tool():
    async def check(session):
        result = await session.call_tool("nonexistent_tool", {})
        assert result.structured_content is not None
        assert "error" in result.structured_content

    asyncio.run(_run_mcp_session(check))


def test_mcp_sdk_client_full_flow():
    """End-to-end MCP SDK client: initialize, list tools, call multiple tools."""
    async def check(session):
        # List tools
        tools = await session.list_tools()
        tool_names = {t.name for t in tools.tools}
        assert "list_components" in tool_names
        assert "validate_storyboard" in tool_names

        # Call list_components
        result = await session.call_tool("list_components", {})
        assert "components" in result.structured_content

        # Call validate_storyboard (valid storyboard)
        result = await session.call_tool("validate_storyboard",
                                         {"path": "docs/gallery/howto.json"})
        assert result.structured_content.get("valid") is True

        # Call validate_storyboard (invalid path)
        result = await session.call_tool("validate_storyboard",
                                         {"path": "/nonexistent/foo.json"})
        assert "error" in result.structured_content

    asyncio.run(_run_mcp_session(check))


def test_mcp_render_storyboard_no_stdout(tmp_path, capsys):
    """MCP render_storyboard tool must not write to stdout (stdio is the protocol channel).

    Calls make_video directly — the same function the MCP tool invokes — and
    asserts nothing is written to stdout, which would corrupt the JSON-RPC
    protocol channel.
    """
    import json as _json
    from animatica.pipeline import make_video

    sb = {"version": "1", "title": "MCP Test", "scenes": [{"beats": [{"component": "title_card", "params": {"title": "Test"}}]}]}
    sb_path = tmp_path / "storyboard.json"
    sb_path.write_text(_json.dumps(sb))

    result = make_video(storyboard_path=sb_path, out_dir=tmp_path, preview=True)
    assert result.video.exists()

    captured = capsys.readouterr()
    assert captured.out == "", f"MCP render_storyboard code path wrote to stdout: {captured.out!r}"

# ---------------------------------------------------------------------------
# T33: agent-surface polish
# ---------------------------------------------------------------------------

def test_mcp_lists_lint_storyboard_and_narrate_option():
    async def check(session):
        tools = {t.name: t for t in (await session.list_tools()).tools}
        assert "lint_storyboard" in tools
        props = tools["render_storyboard"].input_schema["properties"]
        assert "narrate" in props and "voice" in props
        assert "0-based" in tools["preview_frame"].description

    asyncio.run(_run_mcp_session(check))


def test_mcp_validate_malformed_json_is_fixable_not_a_crash(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    async def check(session):
        result = await session.call_tool("validate_storyboard", {"path": str(bad)})
        sc = result.structured_content
        assert sc["valid"] is False
        assert sc["errors"][0].startswith("load error:")
        assert not result.is_error

    asyncio.run(_run_mcp_session(check))


def test_mcp_validate_unknown_component_lists_valid_names(tmp_path):
    import json

    sb = {"version": "1", "title": "t", "scenes": [{"beats": [{"component": "nope", "params": {}}]}]}
    p = tmp_path / "sb.json"
    p.write_text(json.dumps(sb), encoding="utf-8")

    async def check(session):
        result = await session.call_tool("validate_storyboard", {"path": str(p)})
        sc = result.structured_content
        assert sc["valid"] is False
        assert "bounce_sequence" in sc["errors"][0]

    asyncio.run(_run_mcp_session(check))


def test_mcp_lint_storyboard_returns_storyboard_and_notes():
    async def check(session):
        result = await session.call_tool("lint_storyboard", {"path": "docs/gallery/howto.json"})
        sc = result.structured_content
        assert isinstance(sc["notes"], list)
        assert sc["storyboard"]["scenes"]

    asyncio.run(_run_mcp_session(check))


def test_mcp_lint_storyboard_bad_inputs(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text("{not json", encoding="utf-8")

    async def check(session):
        malformed = await session.call_tool("lint_storyboard", {"path": str(bad)})
        assert malformed.structured_content["errors"][0].startswith("load error:")
        missing = await session.call_tool("lint_storyboard", {"path": str(tmp_path / "nope.json")})
        assert "error" in missing.structured_content
        no_arg = await session.call_tool("lint_storyboard", {})
        assert "error" in no_arg.structured_content

    asyncio.run(_run_mcp_session(check))


def test_mcp_component_schema_unknown_name_lists_valid_names():
    async def check(session):
        result = await session.call_tool("component_schema", {"name": "nope"})
        assert "bounce_sequence" in result.structured_content["error"]

    asyncio.run(_run_mcp_session(check))


def test_skill_md_documents_every_mcp_tool():
    """skills/animatica/SKILL.md must name every tool the server exposes."""
    from pathlib import Path

    skill = Path("skills/animatica/SKILL.md").read_text(encoding="utf-8")
    assert skill.startswith("---\nname: animatica\n")

    async def check(session):
        for tool in (await session.list_tools()).tools:
            assert f"`{tool.name}" in skill, f"SKILL.md does not document MCP tool {tool.name}"

    asyncio.run(_run_mcp_session(check))


def test_skill_md_has_hermes_recommended_sections():
    """Hermes' skill guide recommends these sections; the hub-installed copy has no repo around it."""
    from pathlib import Path

    skill = Path("skills/animatica/SKILL.md").read_text(encoding="utf-8")
    for heading in ("## When to Use", "## Pitfalls", "## Verification"):
        assert heading in skill, f"SKILL.md is missing {heading}"
    assert "version:" in skill.split("---")[1] and "description:" in skill.split("---")[1]
