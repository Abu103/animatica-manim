"""Test that animatica mcp implements the real MCP protocol over stdio."""
import asyncio
import json
import sys

import pytest


async def _mcp_request(proc, method, params=None, request_id=1):
    """Send one MCP JSON-RPC request and read the response."""
    msg = {"jsonrpc": "2.0", "id": request_id, "method": method}
    if params is not None:
        msg["params"] = params
    line = json.dumps(msg) + "\n"
    proc.stdin.write(line.encode())
    await proc.stdin.drain()
    resp_line = await proc.stdout.readline()
    return json.loads(resp_line.decode())


async def _mcp_call(proc, name, arguments, request_id):
    """Send a tools/call request and return the parsed structured_content."""
    resp = await _mcp_request(proc, "tools/call", {
        "name": name,
        "arguments": arguments,
    }, request_id=request_id)
    assert "result" in resp, f"{name} call failed: {resp}"
    content = resp["result"]["content"][0]["text"]
    return json.loads(content)


@pytest.mark.asyncio
async def test_mcp_initialize():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "animatica", "mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        resp = await _mcp_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }, request_id=1)
        assert resp.get("jsonrpc") == "2.0"
        assert resp.get("id") == 1
        assert "result" in resp
        assert resp["result"]["serverInfo"]["name"] == "animatica"
    finally:
        proc.stdin.close()
        await proc.wait()


@pytest.mark.asyncio
async def test_mcp_tools_list():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "animatica", "mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await _mcp_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }, request_id=1)
        resp = await _mcp_request(proc, "tools/list", request_id=2)
        assert "result" in resp
        tools = resp["result"].get("tools", [])
        tool_names = {t["name"] for t in tools}
        expected = {"list_components", "component_schema", "validate_storyboard",
                    "render_storyboard", "preview_frame", "lint_video"}
        assert expected <= tool_names, f"missing tools: {expected - tool_names}"
    finally:
        proc.stdin.close()
        await proc.wait()


@pytest.mark.asyncio
async def test_mcp_call_list_components():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "animatica", "mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await _mcp_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }, request_id=1)
        data = await _mcp_call(proc, "list_components", {}, 2)
        assert "components" in data
        assert "bounce_sequence" in data["components"]
    finally:
        proc.stdin.close()
        await proc.wait()


@pytest.mark.asyncio
async def test_mcp_call_component_schema():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "animatica", "mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await _mcp_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }, request_id=1)
        data = await _mcp_call(proc, "component_schema", {"name": "bounce_sequence"}, 2)
        assert "schema" in data
        assert data["schema"].get("properties", {}).get("values") is not None
    finally:
        proc.stdin.close()
        await proc.wait()


@pytest.mark.asyncio
async def test_mcp_call_validate_storyboard_valid():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "animatica", "mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await _mcp_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }, request_id=1)
        data = await _mcp_call(proc, "validate_storyboard",
                               {"path": "docs/gallery/howto.json"}, 2)
        assert data.get("valid") is True
    finally:
        proc.stdin.close()
        await proc.wait()


@pytest.mark.asyncio
async def test_mcp_call_validate_storyboard_invalid_path():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "animatica", "mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await _mcp_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }, request_id=1)
        data = await _mcp_call(proc, "validate_storyboard",
                               {"path": "/nonexistent/foo.json"}, 2)
        assert "error" in data
    finally:
        proc.stdin.close()
        await proc.wait()


@pytest.mark.asyncio
async def test_mcp_call_unknown_tool():
    proc = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "animatica", "mcp",
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        await _mcp_request(proc, "initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "test-client", "version": "1.0"},
        }, request_id=1)
        data = await _mcp_call(proc, "nonexistent_tool", {}, 2)
        assert "error" in data
    finally:
        proc.stdin.close()
        await proc.wait()
