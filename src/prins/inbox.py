"""Messages from a few chosen people on Slack, read from System Zero with its `sz` command line.

System Zero already syncs the Slack account, and `sz` is signed in on this Mac, so the label maker
asks it for news instead of talking to Slack itself. Every second it looks at the newest
conversations (a small answer: a new message always makes its conversation the newest), and only
when someone's DM has something new does it fetch that thread.

Who counts is decided by the Slack user id and the DM's id, never by a display name, because
names can be copied and this decides who gets to put something on the desk. Each person is a
`Source`: their DM, their user id, and the name printed as the sender. A person's id only counts in
their own DM.
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
class Source:
    user_id: str       # Slack user id, e.g. U0BM141R3QX. This is what is trusted.
    conversation: str  # The DM's id, e.g. D0BTS26FXE1.
    name: str          # What is printed as the sender. Ours, not the message's.


def parse_sources(spec: str) -> list[Source]:
    """`USERID:DMID:Name` entries separated by semicolons. Raises ValueError for a broken entry."""
    sources: list[Source] = []
    for entry in filter(None, (part.strip() for part in spec.split(";"))):
        parts = [piece.strip() for piece in entry.split(":", 2)]
        if len(parts) != 3 or not all(parts):
            raise ValueError(f"inbox entry {entry!r} should look like USERID:DMID:Name")
        sources.append(Source(*parts))
    return sources


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
        sources: list[Source],
        state_path: Path,
        sz: str = "sz",
        runner: Callable[..., subprocess.CompletedProcess] = subprocess.run,
        clock: Callable[[], float] = time.time,
        interval: float = 1.0,
        max_age_s: float = 24 * 3600,
        max_backlog: int = 10,
    ) -> None:
        if not sources:
            raise ValueError("an inbox needs at least one source")
        self.sources = sources
        self.state_path, self.sz, self._runner, self._clock = state_path, sz, runner, clock
        self.interval, self.max_age_s, self.max_backlog = interval, max_age_s, max_backlog
        # Per DM: the newest message time handled (None: never run, so no backlog) and the ids already delivered.
        self._last_at: dict[str, Optional[float]] = {s.conversation: None for s in sources}
        self._seen: dict[str, list[str]] = {s.conversation: [] for s in sources}
        self._first_poll = True
        self._load()

    # ---- state ------------------------------------------------------------------------

    def _load(self) -> None:
        try:
            data = json.loads(self.state_path.read_text())
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        if "sources" not in data:
            # The first version watched one person. Its position belongs to the first source.
            data = {"sources": {self.sources[0].conversation: {"last_at": data.get("last_at"), "seen": data.get("seen", [])}}}
        for conversation, entry in (data.get("sources") or {}).items():
            if conversation in self._last_at and isinstance(entry, dict):
                try:
                    self._last_at[conversation] = float(entry["last_at"])
                    self._seen[conversation] = [str(x) for x in entry.get("seen", [])][-_SEEN_KEEP:]
                except (KeyError, TypeError, ValueError):
                    self._last_at[conversation] = None

    def _save(self) -> None:
        try:
            self.state_path.parent.mkdir(parents=True, exist_ok=True)
            self.state_path.write_text(json.dumps({"sources": {
                c: {"last_at": self._last_at[c], "seen": self._seen[c][-_SEEN_KEEP:]} for c in self._last_at if self._last_at[c] is not None
            }}))
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

    @staticmethod
    def _is_from(source: Source, message: dict) -> bool:
        sender = message.get("from") or {}
        return sender.get("externalId") == source.user_id and not sender.get("isMe") and not sender.get("automated")

    # ---- one look ---------------------------------------------------------------------------

    def poll_once(self) -> list[Incoming]:
        """New messages from the chosen people, oldest first. Never the same one twice."""
        # After a start, look wide once, in case a DM was busy while we were off. After that a few are plenty.
        conversations = self._sz("msg", "ls", "--limit", "60" if self._first_poll else str(2 + len(self.sources)))
        self._first_poll = False
        by_id = {c.get("externalId"): c for c in conversations if isinstance(c, dict)}
        found: list[Incoming] = []
        for source in self.sources:
            found.extend(self._poll_source(source, by_id.get(source.conversation)))
        return found

    def _poll_source(self, source: Source, convo: Optional[dict]) -> list[Incoming]:
        key = source.conversation
        if convo is None:
            if self._last_at[key] is None:  # Very first run and the DM is quiet: whatever comes later is new.
                self._last_at[key] = self._clock() * 1000
                self._save()
            return []
        latest = float(convo.get("lastMessageAt") or 0)
        last = self._last_at[key]
        if last is None:      # Very first run: start from now, do not print old conversations.
            self._last_at[key] = latest
            self._save()
            log.info("Inbox started: watching %s from now on.", source.name)
            return []
        if latest <= last:
            return []

        floor = max(last, (self._clock() - self.max_age_s) * 1000)
        thread = self._sz("msg", "thread", str(convo["_id"]))
        seen = set(self._seen[key])
        fresh = [
            Incoming(source.name, str(m.get("text") or "").strip()[:MAX_TEXT_CHARS], str(m.get("externalId") or ""), float(m.get("sentAt") or 0))
            for m in _flatten(thread)
            if self._is_from(source, m) and float(m.get("sentAt") or 0) > floor and str(m.get("externalId") or "") not in seen
        ]
        fresh = [m for m in fresh if m.text and m.external_id][-self.max_backlog:]
        self._seen[key].extend(m.external_id for m in fresh)
        self._last_at[key] = latest
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
                    log.info("Message from %s: %d characters.", message.sender, len(message.text))
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
