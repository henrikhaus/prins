from __future__ import annotations

from email.message import EmailMessage

from prins.connectors.email_imap import ImapPoller, parse_email
from prins.connectors.slack import from_mention_event, from_message_event, reaction_target
from prins.store import Store

OWNER = "U_OWNER"


def _reaction(user=OWNER, reaction="printer", item_type="message"):
    return {"user": user, "reaction": reaction, "item": {"type": item_type, "channel": "C1", "ts": "1.2"}}


def test_slack_dm_becomes_a_message():
    event = {"channel_type": "im", "user": "U1", "text": "hi", "channel": "D1", "ts": "1.2"}
    message = from_message_event(event)
    assert (message.sender_id, message.text, message.external_id) == ("U1", "hi", "D1:1.2")


def test_slack_ignores_bots_edits_and_channel_chatter():
    base = {"channel_type": "im", "user": "U1", "text": "hi", "channel": "D1", "ts": "1.2"}
    assert from_message_event({**base, "bot_id": "B1"}) is None
    assert from_message_event({**base, "subtype": "message_changed"}) is None
    assert from_message_event({**base, "channel_type": "channel"}) is None


def test_slack_mention_needs_text():
    assert from_mention_event({"user": "U1", "text": "  ", "channel": "C1", "ts": "1"}) is None


def test_only_the_owners_printer_reaction_counts():
    assert reaction_target(_reaction(), OWNER) == ("C1", "1.2")
    assert reaction_target(_reaction(user="U_STRANGER"), OWNER) is None
    assert reaction_target(_reaction(reaction="thumbsup"), OWNER) is None
    assert reaction_target(_reaction(item_type="file"), OWNER) is None
    assert reaction_target(_reaction(), "") is None


def _email(body="Please call me.", html=None, headers=None) -> bytes:
    message = EmailMessage()
    message["From"] = "Bjørn Dæhlie <bjorn@example.com>"
    message["Subject"] = "Kontrakt"
    message["Message-ID"] = "<abc@example.com>"
    for key, value in (headers or {}).items():
        message[key] = value
    message.set_content(body)
    if html:
        message.add_alternative(html, subtype="html")
    return message.as_bytes()


def test_parses_sender_subject_and_body():
    parsed = parse_email(_email())
    assert parsed.sender == "Bjørn Dæhlie"
    assert parsed.message_id == "<abc@example.com>"
    assert parsed.text == "Subject: Kontrakt\n\nPlease call me."
    assert parsed.is_bulk is False


def test_strips_quoted_replies():
    body = "Yes, do it.\n\nOn Mon, Jan 1, Sam wrote:\n> old stuff\n> more old stuff"
    assert parse_email(_email(body=body)).body == "Yes, do it."


def test_html_only_email_is_reduced_to_text():
    message = EmailMessage()
    message["From"] = "a@example.com"
    message["Subject"] = "s"
    message.set_content("<style>x{}</style><p>Call &amp; confirm</p>", subtype="html")
    assert parse_email(message.as_bytes()).body == "Call & confirm"


def test_newsletters_are_marked_bulk():
    assert parse_email(_email(headers={"List-Unsubscribe": "<mailto:x@y>"})).is_bulk is True
    assert parse_email(_email(headers={"Precedence": "bulk"})).is_bulk is True


class FakeImap:
    def __init__(self, uids: list[int], raw: bytes = b"") -> None:
        self.uids, self.raw, self.fetched = uids, raw, []

    def uid(self, command, *args):
        if command == "search":
            criteria = args[1]
            if criteria == "ALL":
                return "OK", [" ".join(map(str, self.uids)).encode()]
            start = int(criteria.split()[1].split(":")[0])
            # Real IMAP servers answer n:* with the newest message even if it is older than n.
            found = [u for u in self.uids if u >= start] or self.uids[-1:]
            return "OK", [" ".join(map(str, found)).encode()]
        self.fetched.append((args[0], args[1]))
        return "OK", [(b"1 (BODY[] {10}", self.raw), b")"]


def _poller(store, got):
    return ImapPoller(host="h", user="u", password="p", folder="INBOX", store=store,
                      ingest=lambda **kw: got.append(kw))


def test_first_run_does_not_import_the_whole_inbox():
    store, got = Store(":memory:"), []
    _poller(store, got)._ingest_new(FakeImap([1, 2, 3], _email()))
    assert got == []
    assert store.kv_get("imap_last_uid") == "3"


def test_new_mail_is_ingested_once_and_left_unread():
    store, got = Store(":memory:"), []
    store.kv_set("imap_last_uid", "3")
    imap = FakeImap([1, 2, 3, 4], _email())
    poller = _poller(store, got)
    poller._ingest_new(imap)
    assert [g["sender"] for g in got] == ["Bjørn Dæhlie"]
    assert imap.fetched == [(b"4", "(BODY.PEEK[])")]

    poller._ingest_new(imap)  # The server repeats UID 4 for "5:*": it must not come in again.
    assert len(got) == 1
