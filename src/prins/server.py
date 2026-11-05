"""Local HTTP API, for Handy's hook and anything else that wants to put a note in the queue.

It listens on 127.0.0.1 and requires a token. Without the token, any web page you visit could
post to localhost and print on your desk. The custom header also forces a CORS preflight, which
this server never approves.
"""

from __future__ import annotations

import hmac
import json
import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .design.canvas import bitmap_to_image
from .engine import Engine

log = logging.getLogger(__name__)
MAX_BODY_BYTES = 256 * 1024
TOKEN_HEADER = "X-Prins-Token"


def make_server(engine: Engine, token: str, port: int) -> ThreadingHTTPServer:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args) -> None:
            log.debug("http: " + fmt, *args)

        def _reply(self, status: int, body: bytes, content_type: str = "application/json") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, status: int, payload: dict) -> None:
            self._reply(status, json.dumps(payload).encode())

        def _authorized(self) -> bool:
            sent = self.headers.get(TOKEN_HEADER, "")
            if hmac.compare_digest(sent.encode(), token.encode()):
                return True
            self._json(401, {"error": f"missing or wrong {TOKEN_HEADER}"})
            return False

        def _body(self) -> bytes | None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = -1
            if length < 0 or length > MAX_BODY_BYTES:
                self._json(413, {"error": "body too large"})
                return None
            return self.rfile.read(length)

        def do_GET(self) -> None:
            if not self._authorized():
                return
            if self.path == "/v1/state":
                self._json(200, engine.state())
            else:
                self._json(404, {"error": "not found"})

        def do_POST(self) -> None:
            if not self._authorized():
                return
            body = self._body()
            if body is None:
                return
            if self.path == "/v1/handy/hook":
                paste = engine.hook_transcript(body.decode("utf-8", "replace"))
                self._reply(200, paste.encode(), "text/plain; charset=utf-8")
            elif self.path == "/v1/messages":
                self._post_message(body)
            elif self.path == "/v1/notes":
                self._post_note(body)
            else:
                self._json(404, {"error": "not found"})

        def _post_message(self, body: bytes) -> None:
            try:
                data = json.loads(body)
                text = str(data["text"])
            except (ValueError, KeyError, TypeError):
                self._json(400, {"error": 'send JSON with at least {"text": "..."}'})
                return
            engine.ingest(
                source=str(data.get("source", "agent"))[:20],
                sender=str(data.get("sender", ""))[:60],
                text=text,
                external_id=str(data["external_id"]) if data.get("external_id") else None,
            )
            self._json(202, {"queued": True})

        def _post_note(self, body: bytes) -> None:
            """A finished design from an agent. It skips triage: someone asked for this note."""
            try:
                data = json.loads(body)
                title = str(data["title"])[:120]
                bitmap = data.get("bitmap")
                if bitmap is not None:
                    bitmap_to_image(str(bitmap))
            except (ValueError, KeyError, TypeError) as exc:
                self._json(400, {"error": f"Send JSON with a title and an optional bitmap: {exc}"})
                return
            message = engine.add_note(
                source=str(data.get("source", "agent"))[:20],
                sender=str(data.get("sender", ""))[:60],
                title=title,
                detail=str(data.get("detail", ""))[:200],
                bitmap=bitmap,
            )
            self._json(202, {"queued": True, "message": message})

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve_in_background(server: ThreadingHTTPServer) -> threading.Thread:
    thread = threading.Thread(target=server.serve_forever, name="prins-http", daemon=True)
    thread.start()
    return thread
