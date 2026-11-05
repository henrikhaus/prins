from __future__ import annotations

import base64
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from PIL import Image

from prins.design.canvas import Canvas
from prins.printers import M110Printer, PrintError


@pytest.fixture
def fake_server():
    """Answers like printer/server.py."""
    received: list = []
    state = {"status": 200}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _reply(self, status, payload):
            body = json.dumps(payload).encode()
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            self._reply(200, {"width": 312, "height": 216})

        def do_POST(self):
            received.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            if state["status"] == 200:
                self._reply(200, {"black_pixels": 5, "printed": True})
            else:
                self._reply(state["status"], {"detail": "printer 'Q199' not found (is it on?)"})

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}", received, state
    server.shutdown()


def test_a_note_goes_in_the_format_the_printer_server_expects(fake_server):
    url, received, _ = fake_server
    canvas = Canvas()
    canvas.apply({"op": "logo", "name": "spotify"})
    M110Printer(url).print_image(canvas.image, "note-1")
    sent = received[0]
    assert (sent["width"], sent["height"], sent["format"], sent["dry_run"]) == (312, 216, "1bpp", False)
    # Exactly the note's own bitmap: 1 = black, most significant bit first.
    assert sent["data"] == canvas.bitmap()
    assert len(base64.b64decode(sent["data"])) == 8424


def test_a_printer_that_is_off_says_why(fake_server):
    url, _, state = fake_server
    state["status"] = 503
    with pytest.raises(PrintError, match="not found"):
        M110Printer(url).print_image(Image.new("1", (312, 216), 1), "x")


def test_a_stopped_server_says_how_to_start_it():
    with pytest.raises(PrintError, match="uv run server.py"):
        M110Printer("http://127.0.0.1:1").print_image(Image.new("1", (312, 216), 1), "x")
    assert M110Printer("http://127.0.0.1:1").reachable() is False


def test_reachable(fake_server):
    assert M110Printer(fake_server[0]).reachable() is True
