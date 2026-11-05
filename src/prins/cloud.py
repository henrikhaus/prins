"""Keeps the dashboard up to date, and carries out decisions made there.

The device always works without this. If the dashboard is down, nothing here affects the
queue, the screen or the buttons. Changes wait and go up when it comes back.

Only the short note is sent, plus the picture for a custom design. The raw message text and
audio never leave the Mac from here. Friends' notes arrive here, and always wait for the button.
"""

from __future__ import annotations

import json
import logging
import threading
import urllib.error
import urllib.request
from typing import Callable, Optional, Protocol
from urllib.parse import urlparse

from .design.canvas import DesignError, bitmap_to_image
from .store import Item, Store

log = logging.getLogger(__name__)

SYNC_SECONDS = 5.0
MAX_BACKOFF_SECONDS = 120.0
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class AuthError(RuntimeError):
    pass


class Decider(Protocol):
    def remote_decide(self, item_id: int, action: str) -> bool: ...
    def add_note(self, *, source: str, sender: str, title: str, detail: str = "", bitmap=None, external_id=None) -> str: ...


def checked_url(url: str) -> str:
    """The device token must not travel in the clear."""
    parsed = urlparse(url)
    if parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in _LOCAL_HOSTS):
        return url.rstrip("/")
    raise ValueError(f"PRINS_CLOUD_URL must use https (http is only allowed for localhost): {url}")


def _to_payload(item: Item) -> dict:
    return {
        "localId": item.id,
        "source": item.source[:20],
        "sender": item.sender[:120],
        "title": item.title[:300],
        "detail": item.detail[:500],
        "priority": item.priority,
        "due": item.due[:80],
        "status": item.status,
        "engine": item.engine[:20],
        "createdAt": int(item.created_at * 1000),
        "decidedAt": int(item.decided_at * 1000) if item.decided_at else None,
        "bitmap": item.bitmap,
    }


def http_post(url: str, token: str, body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            raise AuthError("The dashboard rejected this device's token.") from exc
        raise


class CloudSync:
    def __init__(
        self,
        url: str,
        token: str,
        store: Store,
        engine: Decider,
        status: Callable[[], dict],
        post: Callable[[str, str, dict], dict] = http_post,
    ) -> None:
        self.url = f"{checked_url(url)}/api/device/sync"
        self.token = token
        self.store, self.engine, self.status = store, engine, status
        self.post = post
        self._acks: list[int] = []
        self._request_acks: list[int] = []
        self._stop = threading.Event()

    def sync_once(self) -> None:
        items = self.store.unsynced()
        acks = list(self._acks)
        request_acks = list(self._request_acks)
        response = self.post(
            self.url,
            self.token,
            {
                "status": self.status(),
                "items": [_to_payload(i) for i in items],
                "ackedCommands": acks,
                "ackedRequests": request_acks,
            },
        )
        # Only after the dashboard has them. If this upload failed, they go again next time.
        self.store.mark_synced(items)
        self._acks = [ack for ack in self._acks if ack not in acks]
        self._request_acks = [ack for ack in self._request_acks if ack not in request_acks]

        for command in response.get("commands", []):
            if self.engine.remote_decide(command["localId"], command["action"]):
                self._acks.append(command["id"])
        for request in response.get("requests", []):
            self._receive(request)

    def _receive(self, request: dict) -> None:
        """A note from a friend. The external id means a repeat delivery can't add it twice."""
        bitmap = request.get("bitmap")
        try:
            if bitmap:
                bitmap_to_image(bitmap)
        except DesignError as exc:
            log.warning("Ignoring a bad note from a friend: %s", exc)
        else:
            self.engine.add_note(
                source="friend",
                sender=str(request.get("sender", ""))[:60],
                title=str(request.get("title", "Note"))[:120],
                detail=str(request.get("detail", ""))[:200],
                bitmap=bitmap,
                external_id=f"request:{request['id']}",
            )
        self._request_acks.append(request["id"])

    def run(self) -> None:
        delay = SYNC_SECONDS
        last_error: Optional[str] = None
        while not self._stop.wait(delay):
            try:
                self.sync_once()
            except AuthError as exc:
                error = f"{exc} Create a new one on the dashboard's Devices page."
            except (urllib.error.URLError, OSError, ValueError, KeyError) as exc:
                error = f"Could not reach the dashboard: {exc}"
            else:
                if last_error:
                    log.info("Dashboard connection restored.")
                last_error, delay = None, SYNC_SECONDS
                continue
            if error != last_error:
                log.warning(error)
            last_error, delay = error, min(delay * 2, MAX_BACKOFF_SECONDS)

    def stop(self) -> None:
        self._stop.set()
