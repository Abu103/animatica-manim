"""Test that animatica mcp implements the real MCP protocol over stdio.

Tests use plain asyncio (no pytest_asyncio dependency) so they run under
CI with just `pip install -e . pytest`. The mcp package (a main dependency)
provides both the server and client SDK.
"""
import asyncio
import json
import os
import sys

import pytest

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
    from pathlib import Path
    from animatica.pipeline import make_video

    sb = {"version": "1", "title": "MCP Test", "scenes": [{"beats": [{"component": "title_card", "params": {"title": "Test"}}]}]}
    sb_path = tmp_path / "storyboard.json"
    sb_path.write_text(_json.dumps(sb))

    result = make_video(storyboard_path=sb_path, out_dir=tmp_path, preview=True)
    assert result.video.exists()

    captured = capsys.readouterr()
    assert captured.out == "", f"MCP render_storyboard code path wrote to stdout: {captured.out!r}"