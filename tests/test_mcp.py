"""The real thing: starts `prins mcp` as a subprocess and talks to it over stdio, like Claude does."""

from __future__ import annotations

import base64
import io
import json
import os
import sys
from pathlib import Path

import anyio
import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from PIL import Image

from prins.design.canvas import bitmap_to_image
from prins.server import make_server, serve_in_background


def call_mcp(env: dict, script):
    async def main():
        params = StdioServerParameters(
            command=sys.executable, args=["-m", "prins.cli", "mcp"],
            env={**os.environ, **env}, cwd=env["PRINS_HOME"],
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                info = await session.initialize()
                return await script(session, info)

    return anyio.run(main)


@pytest.fixture
def mcp_env(tmp_path):
    return {"PRINS_HOME": str(tmp_path), "PRINS_HTTP_PORT": "1", "PRINS_CLOUD_URL": "", "PRINS_CLOUD_TOKEN": ""}


def text_of(result) -> str:
    return " ".join(c.text for c in result.content if getattr(c, "type", "") == "text")


def test_server_lists_tools_and_explains_itself(mcp_env):
    async def script(session, info):
        return (await session.list_tools()).tools, info

    tools, info = call_mcp(mcp_env, script)
    names = {tool.name for tool in tools}
    assert {"draw_logo", "draw_svg", "draw_image", "draw_pixels", "draw_batch", "preview", "print_note", "send_to_friend", "list_friends", "catalog"} <= names
    assert "312x216" in info.instructions


def test_print_the_spotify_logo_end_to_end(mcp_env):
    """What an agent does when someone says: print the Spotify logo."""

    async def script(session, info):
        drawn = await session.call_tool("draw_logo", {"name": "spotify", "x": 76, "y": 28, "w": 160, "h": 160})
        preview = await session.call_tool("preview", {})
        printed = await session.call_tool("print_note", {"title": "Spotify logo"})
        return drawn, preview, printed

    drawn, preview, printed = call_mcp(mcp_env, script)
    assert drawn.is_error is False and text_of(drawn) == "ok"
    image_block = next(c for c in preview.content if c.type == "image")
    picture = Image.open(io.BytesIO(base64.b64decode(image_block.data)))
    assert picture.size == (312, 216)
    assert picture.convert("L").histogram()[0] > 5000
    # No daemon is running in this test, and the agent is told how to fix that.
    assert printed.is_error is True and "prins run" in text_of(printed)


def test_errors_reach_the_agent_as_tool_errors_not_crashes(mcp_env):
    async def script(session, info):
        bad = await session.call_tool("draw_figure", {"name": "nope"})
        good = await session.call_tool("draw_figure", {"name": "star"})
        return bad, good

    bad, good = call_mcp(mcp_env, script)
    assert bad.is_error is True and "catalog" in text_of(bad)
    assert good.is_error is False


def test_friends_without_a_dashboard_say_what_to_set(mcp_env):
    async def script(session, info):
        return await session.call_tool("list_friends", {})

    result = call_mcp(mcp_env, script)
    assert result.is_error is True and "PRINS_CLOUD_URL" in text_of(result)


def test_print_reaches_the_real_daemon_queue(rig, tmp_path):
    (tmp_path / "token").write_text("secret-token-for-test")
    server = make_server(rig.engine, "secret-token-for-test", 0)
    serve_in_background(server)
    env = {"PRINS_HOME": str(tmp_path), "PRINS_HTTP_PORT": str(server.server_address[1]), "PRINS_CLOUD_URL": "", "PRINS_CLOUD_TOKEN": ""}

    async def script(session, info):
        await session.call_tool("draw_batch", {"ops": [
            {"op": "frame", "name": "stamp"},
            {"op": "logo", "name": "spotify", "x": 96, "y": 28, "w": 120, "h": 120},
            {"op": "text", "s": "On repeat", "x": 30, "y": 150, "w": 252, "h": 40},
        ]})
        return await session.call_tool("print_note", {"title": "Spotify note"})

    try:
        result = call_mcp(env, script)
    finally:
        server.shutdown()
    assert result.is_error is False and "green button" in text_of(result)
    assert rig.device.current.source == "agent" and rig.device.current.title == "Spotify note"
    assert bitmap_to_image(rig.device.current.bitmap).size == (312, 216)

    rig.device.click("confirm")
    assert len(rig.printer.printed) == 1
