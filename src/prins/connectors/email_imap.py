"""Email over read-only IMAP. It never marks anything as read, moves or deletes.

Works with an app password (Gmail, iCloud, Fastmail). Microsoft 365 needs OAuth instead,
which this does not implement.
"""

from __future__ import annotations

import email
import email.policy
import html
import imaplib
import logging
import re
import threading
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import parseaddr
from typing import Callable, Optional

from ..store import Store

log = logging.getLogger(__name__)
POLL_SECONDS = 60
_LAST_UID_KEY = "imap_last_uid"
_BULK_PRECEDENCE = {"bulk", "list", "junk"}
_QUOTE_START = re.compile(r"^(On .+ wrote:|-+\s*Original Message\s*-+|From: .+)$", re.MULTILINE)


@dataclass(frozen=True)
class ParsedEmail:
    sender: str
    subject: str
    body: str
    message_id: str
    is_bulk: bool

    @property
    def text(self) -> str:
        return f"Subject: {self.subject}\n\n{self.body}"


def parse_email(raw: bytes) -> ParsedEmail:
    message: EmailMessage = email.message_from_bytes(raw, policy=email.policy.default)
    name, address = parseaddr(str(message.get("From", "")))
    precedence = str(message.get("Precedence", "")).strip().lower()
    return ParsedEmail(
        sender=name or address,
        subject=str(message.get("Subject", "")).strip(),
        body=_strip_quoted(_body_text(message)),
        message_id=str(message.get("Message-ID", "")).strip(),
        # Filtered before the model runs: newsletters would cost money and add noise.
        is_bulk=bool(message.get("List-Unsubscribe")) or precedence in _BULK_PRECEDENCE,
    )


def _body_text(message: EmailMessage) -> str:
    part = message.get_body(preferencelist=("plain", "html"))
    if part is None:
        return ""
    content = part.get_content()
    if part.get_content_type() == "text/html":
        content = re.sub(r"(?is)<(script|style).*?</\1>", " ", content)
        content = html.unescape(re.sub(r"<[^>]+>", " ", content))
    return content.strip()


def _strip_quoted(body: str) -> str:
    match = _QUOTE_START.search(body)
    if match and match.start() > 0:
        body = body[: match.start()]
    lines = [line for line in body.splitlines() if not line.lstrip().startswith(">")]
    return "\n".join(lines).strip()


class ImapPoller:
    def __init__(
        self,
        *,
        host: str,
        user: str,
        password: str,
        folder: str,
        store: Store,
        ingest: Callable[..., None],
    ) -> None:
        self.host, self.user, self.password, self.folder = host, user, password, folder
        self.store, self.ingest = store, ingest
        self._stop = threading.Event()

    def run(self) -> None:
        """Blocks until stop(), so run it on its own thread."""
        while not self._stop.is_set():
            try:
                self.poll_once()
            except (imaplib.IMAP4.error, OSError) as exc:
                log.warning("Email check failed, will retry: %s", exc)
            self._stop.wait(POLL_SECONDS)

    def stop(self) -> None:
        self._stop.set()

    def poll_once(self) -> None:
        with imaplib.IMAP4_SSL(self.host) as imap:
            imap.login(self.user, self.password)
            imap.select(self.folder, readonly=True)
            self._ingest_new(imap)

    def _ingest_new(self, imap) -> None:
        last = self.store.kv_get(_LAST_UID_KEY)
        if last is None:
            # First run starts from now. Nobody wants their whole inbox in the queue.
            _, data = imap.uid("search", None, "ALL")
            uids = data[0].split()
            self.store.kv_set(_LAST_UID_KEY, uids[-1].decode() if uids else "0")
            return

        _, data = imap.uid("search", None, f"UID {int(last) + 1}:*")
        for uid in data[0].split():
            # IMAP's "n:*" returns the newest message even when it is older than n.
            if int(uid) <= int(last):
                continue
            # BODY.PEEK leaves the message unread.
            _, fetched = imap.uid("fetch", uid, "(BODY.PEEK[])")
            raw = _first_bytes(fetched)
            if raw is not None:
                self._ingest_one(raw, uid.decode())
            self.store.kv_set(_LAST_UID_KEY, uid.decode())

    def _ingest_one(self, raw: bytes, uid: str) -> None:
        parsed = parse_email(raw)
        if parsed.is_bulk:
            log.debug("Skipping bulk email: %s", parsed.subject)
            return
        self.ingest(
            source="email",
            sender=parsed.sender,
            text=parsed.text,
            external_id=parsed.message_id or f"uid:{uid}",
        )


def _first_bytes(fetched) -> Optional[bytes]:
    for part in fetched or []:
        if isinstance(part, tuple) and len(part) >= 2 and isinstance(part[1], bytes):
            return part[1]
    return None
