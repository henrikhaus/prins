"""The board as the label maker sees it: audio and buttons in, screen and lights out.

Speaks the protocol of firmware/project.yaml, documented in docs/LABELS.md.
"""

from __future__ import annotations

import base64
import logging
import threading
from typing import Any, Callable, Protocol

from PIL import Image

from .device import screen_text
from .drawing import thumbnail_2bpp

log = logging.getLogger(__name__)

EVENT_KEYS = ("talk", "printbtn", "discard", "audio_start", "audio", "audio_end")
EventHandler = Callable[[str, Any], None]  # (event key, value)


class LabelDevice(Protocol):
    def start(self, on_event: EventHandler) -> None: ...
    def set_state(self, state: str, title: str, detail: str = "", *, design: bool, preview: bool) -> None: ...
    def show_preview(self, image: Image.Image) -> None: ...
    def close(self) -> None: ...


class LabelBoard:
    def __init__(self, port: str = "", board=None) -> None:
        from atech import Board

        self.board = board if board is not None else Board.connect(port=port or None)
        self._lock = threading.Lock()  # One action at a time, as the SDK asks.
        self._stop = threading.Event()
        self._healthy = True

    def _call(self, key: str, value) -> None:
        from atech import ActionError

        try:
            with self._lock:
                self.board.call(key, value, timeout=3.0)
            if not self._healthy:
                log.info("The board is answering again.")
            self._healthy = True
        except ActionError as exc:
            if self._healthy:
                log.warning("The board did not take %s: %s", key, exc)
            self._healthy = False

    def start(self, on_event: EventHandler) -> None:
        def pump() -> None:
            for event in self.board.events(keys=list(EVENT_KEYS)):
                if self._stop.is_set():
                    return
                try:
                    on_event(event.key, event.value)
                except Exception:
                    log.exception("Handling %s failed", event.key)

        threading.Thread(target=pump, name="atech-events", daemon=True).start()

    def set_state(self, state: str, title: str, detail: str = "", *, design: bool, preview: bool) -> None:
        self._call("ui_state", {
            "state": state,
            "title": screen_text(title, 24),
            "detail": screen_text(detail, 150),
            "design": int(design),
            "preview": int(preview),
        })

    def show_preview(self, image: Image.Image) -> None:
        width, height, data = thumbnail_2bpp(image)
        self._call("ui_preview", f"{width},{height}:{base64.b64encode(data).decode()}")

    def close(self) -> None:
        self._stop.set()
        self.board.close()
