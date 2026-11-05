"""`prins mcp`: lets Claude, Codex or any MCP client design notes and print them.

Runs over stdio on the user's machine. Drawing works with nothing else running. Printing goes
through the local daemon, and sending to friends through the dashboard.
"""

from __future__ import annotations

import base64
import json
import logging
import urllib.error
import urllib.request

import anyio
import mcp_types as types
from mcp.server.lowlevel import Server
from mcp.server.stdio import stdio_server

from . import __version__
from .cloud import checked_url
from .config import Config
from .design.canvas import Canvas, DesignError
from .design.tools import GUIDE, TOOLS, Result, Session, run_tool
from .server import TOKEN_HEADER

log = logging.getLogger(__name__)


class LocalOutput:
    """Sends finished notes where they need to go."""

    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg

    def print_note(self, title: str, bitmap: str) -> str:
        body = {"title": title, "bitmap": bitmap, "source": "agent"}
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.cfg.http_port}/v1/notes",
            data=json.dumps(body).encode(),
            headers={TOKEN_HEADER: self.cfg.api_token(), "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise DesignError(f"Prins refused the note: {_error_text(exc)}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DesignError("Prins isn't running. Start it with: prins run") from exc
        return result.get("message", "queued")

    def _cloud(self, method: str, path: str, body: dict | None = None) -> dict:
        if not (self.cfg.cloud_url and self.cfg.cloud_token):
            raise DesignError("Friends need the dashboard. Set PRINS_CLOUD_URL and PRINS_CLOUD_TOKEN.")
        request = urllib.request.Request(
            f"{checked_url(self.cfg.cloud_url)}{path}",
            method=method,
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {self.cfg.cloud_token}", "Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise DesignError(_error_text(exc)) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise DesignError(f"Couldn't reach the dashboard: {exc}") from exc

    def list_friends(self) -> list[dict]:
        return self._cloud("GET", "/api/device/friends")["friends"]

    def send_to_friend(self, friend: str, title: str, bitmap: str) -> str:
        result = self._cloud("POST", "/api/device/print-requests", {"to": friend, "title": title, "bitmap": bitmap})
        return result.get("message", "sent")


def _error_text(exc: urllib.error.HTTPError) -> str:
    try:
        return json.loads(exc.read()).get("error", str(exc))
    except ValueError:
        return str(exc)


def _to_content(result: Result) -> list:
    content: list = [types.TextContent(type="text", text=result.text)]
    if result.png is not None:
        content.append(types.ImageContent(type="image", data=base64.b64encode(result.png).decode(), mime_type="image/png"))
    return content


def build_server(session: Session) -> Server:
    tools = [types.Tool(name=t.name, description=t.description, input_schema=t.schema) for t in TOOLS]

    async def on_list_tools(ctx, params) -> types.ListToolsResult:
        return types.ListToolsResult(tools=tools)

    async def on_call_tool(ctx, params) -> types.CallToolResult:
        try:
            # Rendering and downloads block, so they don't run on the event loop.
            result = await anyio.to_thread.run_sync(run_tool, session, params.name, params.arguments)
        except DesignError as exc:
            return types.CallToolResult(content=[types.TextContent(type="text", text=str(exc))], is_error=True)
        return types.CallToolResult(content=_to_content(result))

    return Server(
        "prins",
        version=__version__,
        instructions=GUIDE,
        on_list_tools=on_list_tools,
        on_call_tool=on_call_tool,
    )


def run_mcp(cfg: Config) -> int:
    session = Session(canvas=Canvas(external=True, sender=cfg.name), output=LocalOutput(cfg), designs_dir=cfg.home / "designs")
    server = build_server(session)

    async def main() -> None:
        async with stdio_server() as (read_stream, write_stream):
            await server.run(read_stream, write_stream, server.create_initialization_options())

    anyio.run(main)
    return 0
