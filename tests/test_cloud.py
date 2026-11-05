from __future__ import annotations

import urllib.error

import pytest

from prins.cloud import AuthError, CloudSync, checked_url
from prins.store import Store

STATUS = {"deviceKind": "sim", "printer": "preview", "handyInstalled": False, "slack": False,
          "email": False, "mode": "idle", "queue": 0, "version": "0"}


class FakeDashboard:
    def __init__(self) -> None:
        self.bodies: list[dict] = []
        self.commands: list[dict] = []
        self.error: Exception | None = None

    def __call__(self, url: str, token: str, body: dict) -> dict:
        if self.error:
            raise self.error
        self.bodies.append(body)
        return {"commands": self.commands}


def make_sync(rig, dashboard: FakeDashboard) -> CloudSync:
    return CloudSync("https://prins.example.com/", "prins_x", rig.store, rig.engine, lambda: STATUS, post=dashboard)


def test_url_must_be_https_except_on_localhost():
    assert checked_url("https://prins.henhau.no/") == "https://prins.henhau.no"
    assert checked_url("http://localhost:3000") == "http://localhost:3000"
    with pytest.raises(ValueError):
        checked_url("http://prins.henhau.no")
    with pytest.raises(ValueError):
        checked_url("ftp://prins.henhau.no")


def test_only_the_short_note_is_uploaded_never_the_raw_text(rig):
    dashboard = FakeDashboard()
    rig.message("SECRET full email body. It goes on and on.", sender="Maria")
    rig.store.add(source="email", sender="A", raw_text="SECRET raw text", title="Short task")
    make_sync(rig, dashboard).sync_once()
    item = dashboard.bodies[0]["items"][1]
    assert item["title"] == "Short task"
    assert "raw" not in str(item).lower()
    assert "SECRET raw text" not in str(dashboard.bodies)


def test_items_are_sent_once_and_again_after_a_decision(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("First.")
    sync.sync_once()
    sync.sync_once()
    assert len(dashboard.bodies[0]["items"]) == 1
    assert dashboard.bodies[1]["items"] == []

    rig.device.click("dismiss")
    sync.sync_once()
    assert dashboard.bodies[2]["items"][0]["status"] == "dismissed"
    assert dashboard.bodies[2]["items"][0]["decidedAt"] is not None


def test_a_failed_upload_is_retried(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("First.")
    dashboard.error = urllib.error.URLError("down")
    with pytest.raises(urllib.error.URLError):
        sync.sync_once()
    dashboard.error = None
    sync.sync_once()
    assert len(dashboard.bodies[0]["items"]) == 1


def test_a_change_during_the_upload_is_sent_next_time(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("First.")
    item_id = rig.store.next_queued().id

    def post_and_decide(url, token, body):
        rig.store.decide(item_id, "dismissed")  # The button is pressed mid-upload.
        return dashboard(url, token, body)

    sync.post = post_and_decide
    sync.sync_once()
    sync.post = dashboard
    sync.sync_once()
    assert dashboard.bodies[-1]["items"][0]["status"] == "dismissed"


def test_print_from_the_web_prints_and_is_acknowledged(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("First.")
    item_id = rig.store.next_queued().id
    dashboard.commands = [{"id": 9, "action": "print", "localId": item_id}]
    sync.sync_once()
    assert len(rig.printer.printed) == 1
    assert rig.store.get(item_id).status == "printed"

    dashboard.commands = []
    sync.sync_once()
    assert dashboard.bodies[-1]["ackedCommands"] == [9]
    sync.sync_once()
    assert dashboard.bodies[-1]["ackedCommands"] == []


def test_a_command_delivered_twice_prints_once(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("First.")
    item_id = rig.store.next_queued().id
    dashboard.commands = [{"id": 9, "action": "print", "localId": item_id}]
    sync.sync_once()
    sync.sync_once()
    assert len(rig.printer.printed) == 1


def test_dismiss_from_the_web_advances_the_screen(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("First.")
    rig.message("Second.")
    dashboard.commands = [{"id": 1, "action": "dismiss", "localId": rig.store.next_queued().id}]
    sync.sync_once()
    assert rig.device.current.title == "Second."
    assert rig.printer.printed == []


def test_a_web_print_of_another_note_leaves_the_card_on_screen(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("On screen.")
    rig.message("Other.")
    other = [i for i in rig.store.unsynced() if i.title == "Other."][0]
    dashboard.commands = [{"id": 1, "action": "print", "localId": other.id}]
    sync.sync_once()
    assert rig.store.get(other.id).status == "printed"
    assert rig.device.current.title == "On screen."
    assert rig.device.current.queue == 1


def test_a_busy_device_waits_and_does_not_acknowledge(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    rig.message("First.")
    item_id = rig.store.next_queued().id
    rig.device.press("talk", True)  # Someone is dictating.
    dashboard.commands = [{"id": 9, "action": "print", "localId": item_id}]
    sync.sync_once()
    assert rig.printer.printed == []
    sync.sync_once()
    assert dashboard.bodies[-1]["ackedCommands"] == []

    rig.clock.now += 0.1
    rig.device.press("talk", False)  # A short tap, so it's cancelled and the device is free.
    sync.sync_once()
    assert len(rig.printer.printed) == 1


def test_a_command_for_an_unknown_note_is_acknowledged_so_it_stops(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    dashboard.commands = [{"id": 5, "action": "print", "localId": 999}]
    sync.sync_once()
    dashboard.commands = []
    sync.sync_once()
    assert dashboard.bodies[-1]["ackedCommands"] == [5]


def test_a_revoked_token_raises_a_clear_error(rig):
    dashboard = FakeDashboard()
    dashboard.error = AuthError("rejected")
    with pytest.raises(AuthError):
        make_sync(rig, dashboard).sync_once()


def test_old_databases_get_the_new_columns(tmp_path):
    import sqlite3

    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.execute("""CREATE TABLE items (id INTEGER PRIMARY KEY AUTOINCREMENT, source TEXT NOT NULL,
        sender TEXT NOT NULL DEFAULT '', raw_text TEXT NOT NULL, title TEXT NOT NULL,
        detail TEXT NOT NULL DEFAULT '', priority TEXT NOT NULL DEFAULT 'normal',
        due TEXT NOT NULL DEFAULT '', status TEXT NOT NULL, engine TEXT NOT NULL, external_id TEXT,
        created_at REAL NOT NULL, decided_at REAL, UNIQUE (source, external_id))""")
    db.execute("INSERT INTO items (source, raw_text, title, status, engine, created_at) VALUES ('a','b','c','queued','x',1)")
    db.commit()
    db.close()
    assert [item.title for item in Store(path).unsynced()] == ["c"]


def _design():
    from prins.design.canvas import Canvas

    canvas = Canvas()
    canvas.apply({"op": "figure", "name": "heart"})
    return canvas.bitmap()


def test_a_friends_note_waits_for_the_button_even_with_auto_print_on(rig):
    rig.engine.agent_auto_print = True
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    dashboard_reply = {"commands": [], "requests": [{"id": 3, "sender": "Sam", "title": "For you", "detail": "", "bitmap": _design()}]}
    sync.post = lambda *_: dashboard_reply
    sync.sync_once()
    assert rig.printer.printed == []
    assert rig.device.current.source == "friend" and rig.device.current.sender == "Sam"
    assert rig.device.current.bitmap


def test_a_repeated_friend_request_only_appears_once(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    reply = {"commands": [], "requests": [{"id": 3, "sender": "Sam", "title": "Hi", "detail": "", "bitmap": None}]}
    sync.post = lambda *_: reply
    sync.sync_once()
    sync.sync_once()
    assert rig.device.current.queue == 1


def test_friend_requests_are_acknowledged(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    sent: list = []

    def post(url, token, body):
        sent.append(body)
        return {"commands": [], "requests": [{"id": 3, "sender": "Sam", "title": "Hi"}] if len(sent) == 1 else []}

    sync.post = post
    sync.sync_once()
    sync.sync_once()
    sync.sync_once()
    assert sent[1]["ackedRequests"] == [3] and sent[2]["ackedRequests"] == []


def test_a_malformed_friend_note_is_dropped_and_stops_coming(rig):
    dashboard = FakeDashboard()
    sync = make_sync(rig, dashboard)
    sent: list = []

    def post(url, token, body):
        sent.append(body)
        return {"commands": [], "requests": [{"id": 4, "sender": "Sam", "title": "x", "bitmap": "garbage"}] if len(sent) == 1 else []}

    sync.post = post
    sync.sync_once()
    sync.sync_once()
    assert rig.device.current.title == "All clear"
    assert sent[1]["ackedRequests"] == [4]


def test_custom_designs_are_uploaded_for_the_web_preview(rig):
    dashboard = FakeDashboard()
    design = _design()
    rig.engine.add_note(source="agent", sender="", title="Heart", bitmap=design)
    make_sync(rig, dashboard).sync_once()
    assert dashboard.bodies[0]["items"][0]["bitmap"] == design


def test_your_own_agent_can_skip_the_button_if_you_turn_that_on(rig):
    assert "green button" in rig.engine.add_note(source="agent", sender="", title="A", bitmap=_design())
    assert rig.printer.printed == []
    rig.device.click("dismiss")
    rig.engine.agent_auto_print = True
    assert rig.engine.add_note(source="agent", sender="", title="B", bitmap=_design()) == "Printing."
    assert len(rig.printer.printed) == 1
