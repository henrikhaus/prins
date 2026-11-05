"""Messages from one person on Slack, read from System Zero with its `sz` command line.

System Zero already syncs the Slack account, and `sz` is signed in on this Mac, so the label maker
asks it for news instead of talking to Slack itself. Every second it looks at the three newest
conversations (a small answer: a new message always makes its conversation the newest), and only
when the person's DM has something new does it fetch the whole thread.

Who counts is decided by the Slack user id and the DM's id, never by a display name, because
names can be copied and this decides who gets to put something on the desk.
"""

from __future__ import annotations

import json
import logging
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional

log = logging.getLogger(__name__)

MAX_TEXT_CHARS = 2000
_SEEN_KEEP = 300


class InboxError(Exception):
    """`sz` could not be run, or answered with something unreadable."""


@dataclass(frozen=True)
class Incoming:
    sender: str        # What to print as the sender. From our settings, not from the message.
    text: str
    external_id: str
    sent_at: float     # Milliseconds since 1970, as System Zero reports it.


def _flatten(thread: Any) -> list[dict]:
    """Every message of a `sz msg thread` answer: thread roots and their replies, oldest first."""
    found: list[dict] = []
    for entry in (thread.get("messages") if isinstance(thread, dict) else thread) or []:
        if not isinstance(entry, dict):
            continue
        if isinstance(entry.get("root"), dict):
            found.append(entry["root"])
        found.extend(m for m in entry.get("replies") or [] if isinstance(m, dict))
        if "text" in entry and "root" not in entry:
            found.append(entry)
    return sorted(found, key=lambda m: float(m.get("sentAt") or 0))


class SzInbox:
    def __init__(
        self,
        *,
        user_id: str,
        conversation: str,
        name: str,
        state_path: Path,
        sz: str = "sz",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        clock: Callable[[], float] = time.time,
        interval: float = 1.0,
        max_age_s: float = 24 * 3600,
        max_backlog: int = 10,
    ) -> None:
        self.user_id, self.conversation, self.name = user_id, conversation, name
        self.state_path, self.sz, self._runner, self._clock = state_path, sz, runner, clock
        self.interval, self.max_age_s, self.max_backlog = interval, max_age_s, max_backlog
        self._last_at: Optional[float] = None   # Newest message time handled. None: never run, so no backlog.
        self._seen: list[str] = []
        self._first_poll = True
        self._load()

    # ---- state ------------------------------------------------------------------------

    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text())
            self._last_at = float(data["last_at"])
            self._seen = [str(x) for x in data.get("seen", [])][-_SEEN_KEEP:]
        except (OSError, ValueError, KeyError, TypeError):
            self._last_at = None

    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"last_at": self._last_at, "seen": self._seen[-_SEEN_KEEP:]}))
        except OSError as exc:
            log.warning("Could not save the inbox position: %s", exc)

    # ---- talking to sz ------------------------------------------------------------------

    def _sz(self, *args: str) -> Any:
        try:
            result = self._runner([self.sz, *args, "--json"], capture_output=True, text=True, timeout=30)
        except (OSError, subprocess.SubprocessError) as exc:
            raise InboxError(f"could not run {self.sz}: {exc}") from exc
        if result.returncode != 0:
            raise InboxError(f"{self.sz} {' '.join(args)} failed: {(result.stderr or result.stdout).strip()[:200]}")
        try:
            return json.loads(result.stdout)
        except ValueError as exc:
            raise InboxError(f"{self.sz} {' '.join(args)} gave unreadable output") from exc

    def _is_from_them(self, message: dict) -> bool:
        sender = message.get("from") or {}
        return (sender.get("externalId") == self.user_id and not sender.get("isMe") and not sender.get("automated"))

    # ---- one look ---------------------------------------------------------------------------

    def poll_once(self) -> list[Incoming]:
        """New messages from the person, oldest first. Never the same one twice."""
        # After a start, look wide once, in case the DM was busy while we were off. After that three is plenty.
        conversations = self._sz("msg", "ls", "--limit", "60" if self._first_poll else "3")
        self._first_poll = False
        convo = next((c for c in conversations if isinstance(c, dict) and c.get("externalId") == self.conversation), None)
        if convo is None:
            if self._last_at is None:  # Very first run and the DM is quiet: whatever comes later is new.
                self._last_at = self._clock() * 1000
                self._save()
            return []
        latest = float(convo.get("lastMessageAt") or 0)
        if self._last_at is None:      # Very first run: start from now, do not print old conversations.
            self._last_at = latest
            self._save()
            log.info("Inbox started: watching %s from now on.", self.name)
            return []
        if latest <= self._last_at:
            return []

        floor = max(self._last_at, (self._clock() - self.max_age_s) * 1000)
        thread = self._sz("msg", "thread", str(convo["_id"]))
        fresh = [
            Incoming(self.name, str(m.get("text") or "").strip()[:MAX_TEXT_CHARS], str(m.get("externalId") or ""), float(m.get("sentAt") or 0))
            for m in _flatten(thread)
            if self._is_from_them(m) and float(m.get("sentAt") or 0) > floor and str(m.get("externalId") or "") not in self._seen
        ]
        fresh = [m for m in fresh if m.text and m.external_id][-self.max_backlog:]
        self._seen.extend(m.external_id for m in fresh)
        self._last_at = latest
        self._save()
        return fresh

    # ---- forever ---------------------------------------------------------------------------

    def run(self, on_message: Callable[[Incoming], None], stop: threading.Event) -> None:
        failures = 0
        while not stop.is_set():
            started = time.monotonic()
            wait = self.interval
            try:
                for message in self.poll_once():
                    log.info("Message from %s: %d characters.", self.name, len(message.text))
                    on_message(message)
                if failures:
                    log.info("System Zero is answering again.")
                failures = 0
            except InboxError as exc:
                failures += 1
                if failures in (1, 10) or failures % 60 == 0:
                    log.warning("Could not read System Zero (%d in a row): %s", failures, exc)
                wait = min(30.0, self.interval * (2 ** min(failures, 5)))
            except Exception:
                log.exception("The inbox failed")
                wait = 5.0
            stop.wait(max(0.0, wait - (time.monotonic() - started)))  # A look every `interval`, however long `sz` took.
