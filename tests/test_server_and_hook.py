"""The HTTP API, and the real shell hook Handy would run, against a live local server."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from prins.server import TOKEN_HEADER, make_server, serve_in_background

TOKEN = "secret-token"
HOOK = Path(__file__).resolve().parents[1] / "scripts" / "handy-hook.sh"


@pytest.fixture
def live(rig, tmp_path):
    server = make_server(rig.engine, TOKEN, 0)
    serve_in_background(server)
    (tmp_path / "token").write_text(TOKEN)
    yield rig, server.server_address[1], tmp_path
    server.shutdown()


def _post(port, path, body: bytes, token=TOKEN):
    headers = {TOKEN_HEADER: token} if token else {}
    request = urllib.request.Request(f"http://127.0.0.1:{port}{path}", data=body, headers=headers)
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.status, response.read()


def _run_hook(text: str, port: int, home: Path) -> str:
    env = {"PATH": "/usr/bin:/bin:/usr/sbin:/sbin", "HOME": str(home),
           "PRINS_HOME": str(home), "PRINS_HTTP_PORT": str(port)}
    result = subprocess.run(["/bin/sh", str(HOOK)], input=text.encode(), capture_output=True, env=env, timeout=10)
    assert result.returncode == 0, result.stderr
    return result.stdout.decode()


@pytest.mark.parametrize("token", ["", "wrong"])
def test_requests_without_the_token_are_refused(live, token):
    rig, port, _ = live
    with pytest.raises(urllib.error.HTTPError) as err:
        _post(port, "/v1/messages", b'{"text":"print this"}', token=token)
    assert err.value.code == 401
    assert rig.store.queue_size() == 0


def test_post_message_reaches_the_queue(live):
    rig, port, _ = live
    status, _ = _post(port, "/v1/messages", json.dumps(
        {"text": "Deploy is blocked on you.", "source": "agent", "sender": "Claude Code"}
    ).encode())
    assert status == 202
    assert rig.device.current.source == "agent"
    assert rig.device.current.sender == "Claude Code"


def test_bad_json_gets_a_400(live):
    _, port, _ = live
    with pytest.raises(urllib.error.HTTPError) as err:
        _post(port, "/v1/messages", b"not json")
    assert err.value.code == 400


def test_hook_passes_normal_dictation_through_unchanged(live):
    _, port, home = live
    text = 'Dear "team", 100% ready. Blåbær! @/etc/passwd $HOME `whoami`'
    assert _run_hook(text, port, home) == text


def test_hook_swallows_text_captured_by_the_talk_button(live):
    rig, port, home = live
    rig.hold_talk()
    assert _run_hook("Book the dentist.", port, home) == ""
    assert rig.device.current.title == "Book the dentist."


def test_hook_keeps_your_words_when_prins_is_off(tmp_path):
    (tmp_path / "token").write_text(TOKEN)
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free_port = sock.getsockname()[1]
    assert _run_hook("Dear team,", free_port, tmp_path) == "Dear team,"


def test_hook_keeps_your_words_with_a_wrong_token(live):
    _, port, home = live
    (home / "token").write_text("stale")
    assert _run_hook("Dear team,", port, home) == "Dear team,"


def test_api_token_file_is_private(tmp_path):
    from prins.config import Config

    cfg = Config(home=tmp_path / "home")
    token = cfg.api_token()
    assert token == cfg.api_token()
    assert os.stat(cfg.token_path).st_mode & 0o077 == 0
