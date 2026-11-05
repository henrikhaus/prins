"""The physical device, or a stand-in for it. The engine only knows this interface."""

from __future__ import annotations

import base64
import logging
import threading
import time
import unicodedata
from dataclasses import dataclass
from typing import Callable, Optional, Protocol

log = logging.getLogger(__name__)

_RESEND_S = 15.0
DESIGN_CHUNK_BYTES = 2400

BUTTONS = ("talk", "confirm", "dismiss")
ButtonHandler = Callable[[str, bool], None]  # (button name, is it now pressed)

# The board's GFX fonts cover ASCII only, and its JSON reader does not decode \uXXXX,
# so the screen gets transliterated text. The printer is unaffected: notes are images.
_TRANSLITERATE = str.maketrans({
    "æ": "ae", "Æ": "AE", "ø": "o", "Ø": "O", "å": "a", "Å": "A", "ß": "ss",
    "“": "'", "”": "'", "‘": "'", "’": "'", '"': "'", "–": "-", "—": "-", "…": "...",
    "\\": "/",
})


def screen_text(text: str, limit: int = 300) -> str:
    text = text.translate(_TRANSLITERATE)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    return " ".join(text.split())[:limit]


def rgb565(r: int, g: int, b: int) -> int:
    return ((r & 0xF8) << 8) | ((g & 0xFC) << 3) | (b >> 3)


ACCENTS = {
    "slack": rgb565(190, 130, 255),
    "email": rgb565(90, 170, 255),
    "voice": rgb565(255, 170, 60),
    "agent": rgb565(80, 220, 140),
    "friend": rgb565(255, 130, 180),
    "idle": rgb565(90, 90, 90),
    "listening": rgb565(255, 90, 90),
    "thinking": rgb565(255, 200, 60),
    "printing": rgb565(80, 220, 140),
    "error": rgb565(255, 60, 60),
}
_DEFAULT_ACCENT = rgb565(200, 200, 200)


@dataclass(frozen=True)
class CardView:
    source: str
    sender: str
    title: str
    detail: str
    queue: int
    hint: str = "Green: print    Red: dismiss"
    bitmap: str = ""  # A custom design: the screen shows the note itself, so you see what you approve.

    def payload(self) -> dict:
        return {
            "source": "PRINS" if self.source == "idle" else screen_text(self.source.upper(), 20),
            "from": screen_text(self.sender, 40),
            "title": screen_text(self.title, 180),
            "detail": screen_text(self.detail, 240),
            "hint": screen_text(self.hint, 60),
            "queue": self.queue,
            "accent": ACCENTS.get(self.source, _DEFAULT_ACCENT),
            "design": 1 if self.bitmap else 0,
        }


@dataclass(frozen=True)
class StatusView:
    kind: str
    title: str
    detail: str = ""

    def payload(self) -> dict:
        return {
            "title": screen_text(self.title, 40),
            "detail": screen_text(self.detail, 200),
            "accent": ACCENTS.get(self.kind, _DEFAULT_ACCENT),
        }


View = CardView | StatusView


class Device(Protocol):
    def start(self, on_button: ButtonHandler) -> None: ...
    def show(self, view: View) -> None: ...
    def close(self) -> None: ...


class AtechDevice:
    """Speaks the JSON protocol from firmware-prins/project.yaml over USB."""

    def __init__(self, port: str = "", board=None) -> None:
        from atech import Board

        self.board = board if board is not None else Board.connect(port=port or None)
        self._lock = threading.Lock()  # One action at a time, as the SDK asks.
        self._stop = threading.Event()
        self._last_ok = True
        self._last_view: Optional[View] = None
        self._last_sent = 0.0

    def call(self, key: str, value="", timeout: float = 3.0) -> None:
        with self._lock:
            self.board.call(key, value, timeout=timeout)

    def query(self, key: str, value="", *, reply: str, timeout: float = 3.0):
        with self._lock:
            return self.board.query(key, value, reply=reply, timeout=timeout)

    def start(self, on_button: ButtonHandler) -> None:
        def pump() -> None:
            for event in self.board.events(keys=list(BUTTONS)):
                if self._stop.is_set():
                    return
                try:
                    on_button(event.key, bool(event.value))
                except Exception:
                    log.exception("Button handler failed")

        threading.Thread(target=pump, name="atech-events", daemon=True).start()

    def show(self, view: View) -> None:
        from atech import ActionError

        # Unchanged views are resent now and then, so the screen recovers after a board reset.
        now = time.monotonic()
        if view == self._last_view and now - self._last_sent < _RESEND_S:
            return
        key = "ui_card" if isinstance(view, CardView) else "ui_status"
        try:
            if isinstance(view, CardView) and view.bitmap:
                self._send_design(view.bitmap)
            self.call(key, view.payload())
            self._last_view, self._last_sent = view, now
            if not self._last_ok:
                log.info("The board is answering again.")
            self._last_ok = True
        except ActionError as exc:
            # A dead screen must not stop the queue. The engine's refresh tries again.
            if self._last_ok:
                log.warning("Could not update the screen: %s", exc)
            self._last_ok = False

    def _send_design(self, bitmap: str) -> None:
        """A note is too big for one line of the protocol, so it goes in pieces."""
        packed = base64.b64decode(bitmap)
        for offset in range(0, len(packed), DESIGN_CHUNK_BYTES):
            piece = base64.b64encode(packed[offset : offset + DESIGN_CHUNK_BYTES]).decode("ascii")
            self.call("ui_design", {"o": offset, "d": piece})

    def close(self) -> None:
        self._stop.set()
        self.board.close()


class SimDevice:
    """No hardware: prints the screen to the terminal. Press buttons with press()."""

    def __init__(self, output: Callable[[str], None] = print) -> None:
        self.output = output
        self.current: Optional[View] = None
        self.on_button: Optional[ButtonHandler] = None

    def start(self, on_button: ButtonHandler) -> None:
        self.on_button = on_button

    def show(self, view: View) -> None:
        if view == self.current:
            return
        self.current = view
        self.output(self.draw(view))

    def press(self, button: str, down: bool = True) -> None:
        assert self.on_button is not None
        self.on_button(button, down)

    def click(self, button: str) -> None:
        self.press(button, True)
        self.press(button, False)

    def close(self) -> None:
        pass

    @staticmethod
    def draw(view: View) -> str:
        width = 46
        if isinstance(view, StatusView):
            lines = [f"  {view.title}", f"  {view.detail}" if view.detail else ""]
            head = view.kind.upper()
        else:
            origin = view.source.upper() + (f" - {view.sender}" if view.sender else "")
            head = f"{origin[:width - 10]:<{width - 10}}[queue {view.queue}]"
            detail = "(custom design)" if view.bitmap else view.detail
            lines = [f"  {view.title}", f"  {detail}" if detail else "", f"  {view.hint}"]
        rule = "+" + "-" * (width + 2) + "+"
        body = "\n".join(f"| {line[:width]:<{width}} |" for line in lines)
        return f"{rule}\n| {head[:width]:<{width}} |\n{rule}\n{body}\n{rule}"
