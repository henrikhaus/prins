"""The product logic: the queue, the screen and the three buttons. Everything else plugs in."""

from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional, Protocol

from .device import CardView, Device, StatusView
from .printers import PrintError, Printer
from .render import render_note
from .store import DISMISSED, IGNORED, PRINTED, Item, Store
from .triage import Triage

log = logging.getLogger(__name__)

SHORTEST_DICTATION_S = 0.25  # A shorter press is an accidental tap, so it is cancelled.
LONGEST_DICTATION_S = 180.0
HOOK_WAIT_S = 45.0  # How long a released talk button waits for Handy's transcript.
_NOTICE_S = 4.0


class Dictation(Protocol):
    def toggle(self) -> bool: ...
    def cancel(self) -> bool: ...


class Engine:
    def __init__(
        self,
        store: Store,
        triage: Triage,
        device: Device,
        printer: Printer,
        dictation: Dictation,
        note_width: int = 384,
        clock=time.monotonic,
        synchronous: bool = False,
    ) -> None:
        self.store, self.triage, self.device = store, triage, device
        self.printer, self.dictation = printer, dictation
        self.note_width = note_width
        self.clock = clock
        self._lock = threading.RLock()
        self._current_id: Optional[int] = None
        self._mode = "idle"  # idle | listening | printing
        self._talk_started = 0.0
        self._capture_until = 0.0  # The next transcript belongs to the device until this time.
        self._pending_triage = 0
        self._notice: Optional[StatusView] = None
        self._notice_until = 0.0
        self._synchronous = synchronous
        self._pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="prins")

    # --- lifecycle -----------------------------------------------------------------

    def start(self) -> None:
        self.device.start(self.on_button)
        self.refresh()

    def close(self) -> None:
        self._pool.shutdown(wait=False, cancel_futures=True)
        self.device.close()

    def _submit(self, fn, *args) -> None:
        if self._synchronous:
            fn(*args)
        else:
            self._pool.submit(self._guarded, fn, *args)

    @staticmethod
    def _guarded(fn, *args) -> None:
        try:
            fn(*args)
        except Exception:
            log.exception("Background work failed in %s", getattr(fn, "__name__", fn))

    # --- what comes in ----------------------------------------------------------------

    def ingest(self, *, source: str, sender: str, text: str, external_id: Optional[str] = None) -> None:
        """Called from any connector thread. Returns at once; the model runs in the background."""
        if self.store.seen(source, external_id):
            return
        with self._lock:
            self._pending_triage += 1
        self._submit(self._triage_message, source, sender, text, external_id)

    def _triage_message(self, source: str, sender: str, text: str, external_id: Optional[str]) -> None:
        try:
            result = self.triage.message(source=source, sender=sender, text=text)
            # Source and sender come from the connector, never from the model, so a crafted
            # message cannot pretend to be from someone else on the printed note.
            self.store.add(
                source=source, sender=sender, raw_text=text, title=result.title,
                detail=result.detail, priority=result.priority, due=result.due,
                status="queued" if result.is_task else IGNORED,
                engine=result.engine, external_id=external_id,
            )
        finally:
            with self._lock:
                self._pending_triage -= 1
            self.refresh()

    def hook_transcript(self, text: str) -> str:
        """Called by Handy's hook. Returns what Handy should paste.

        Talk button: the words become notes and nothing is pasted. Handy's own hotkey:
        the words pass straight through, which is the ordinary Wispr-style dictation.
        """
        with self._lock:
            ours = self.clock() < self._capture_until
            if ours:
                self._capture_until = 0.0
        if not ours:
            return text
        self._submit(self._triage_dictation, text)
        return ""

    def _triage_dictation(self, text: str) -> None:
        try:
            for note in self.triage.dictation(text):
                self.store.add(
                    source="voice", sender="", raw_text=text, title=note.title,
                    detail=note.detail, priority=note.priority, due=note.due,
                    engine=note.engine,
                )
        finally:
            with self._lock:
                if self._mode == "thinking":
                    self._mode = "idle"
            self.refresh()

    # --- buttons ----------------------------------------------------------------------

    def on_button(self, button: str, pressed: bool) -> None:
        if button == "talk":
            self._on_talk(pressed)
        elif pressed and button == "confirm":
            self._on_confirm()
        elif pressed and button == "dismiss":
            self._on_dismiss()

    def _on_talk(self, pressed: bool) -> None:
        with self._lock:
            if pressed:
                if self._mode == "printing":
                    return
                if self.dictation.toggle():
                    self._mode = "listening"
                    self._talk_started = self.clock()
                else:
                    self._set_notice("error", "No dictation", "Handy is not running or installed")
            else:
                if self._mode != "listening":
                    return
                if self.clock() - self._talk_started < SHORTEST_DICTATION_S:
                    self.dictation.cancel()
                    self._mode = "idle"
                else:
                    self.dictation.toggle()
                    self._capture_until = self.clock() + HOOK_WAIT_S
                    self._mode = "thinking"
                    # If the transcript never arrives, the refresh below returns to the queue.
        self.refresh()

    def _on_confirm(self) -> None:
        with self._lock:
            if self._mode != "idle" or self._current_id is None:
                return
            item = self.store.get(self._current_id)
            if item is None:
                return
            self._mode = "printing"
        self.refresh()
        self._submit(self._print, item)

    def _print(self, item: Item) -> None:
        try:
            image = render_note(item, self.note_width)
            described = self.printer.print_image(image, f"note-{item.id}")
            self.store.decide(item.id, PRINTED)
            log.info("Printed note %s: %s", item.id, described)
            with self._lock:
                self._current_id = None
        except PrintError as exc:
            # The note stays queued and on the screen, so nothing is lost.
            log.error("Print failed for note %s: %s", item.id, exc)
            with self._lock:
                self._set_notice("error", "Print failed", str(exc))
        finally:
            with self._lock:
                self._mode = "idle"
            self.refresh()

    def _on_dismiss(self) -> None:
        with self._lock:
            if self._mode != "idle" or self._current_id is None:
                return
            self.store.decide(self._current_id, DISMISSED)
            self._current_id = None
        self.refresh()

    # --- the screen -------------------------------------------------------------------

    def _set_notice(self, kind: str, title: str, detail: str = "") -> None:
        self._notice = StatusView(kind, title, detail)
        self._notice_until = self.clock() + _NOTICE_S

    def _pick_current(self) -> Optional[Item]:
        """The card on screen stays until it is decided. If a more urgent note could replace
        it, someone reaching for the button would act on a note they had not read."""
        if self._current_id is not None:
            item = self.store.get(self._current_id)
            if item is not None and item.status == "queued":
                return item
        item = self.store.next_queued()
        self._current_id = item.id if item else None
        return item

    def refresh(self) -> None:
        with self._lock:
            now = self.clock()
            if self._mode == "listening" and now - self._talk_started > LONGEST_DICTATION_S:
                # The release never came, for example because the board reset during a hold.
                self.dictation.cancel()
                self._mode = "idle"
                self._set_notice("error", "Stopped listening", "The talk button was held too long")
            if self._mode == "thinking" and self._capture_until and now >= self._capture_until:
                self._capture_until = 0.0
                self._mode = "idle"
                self._set_notice("error", "No transcript", "Handy did not send any text")
            view = self._view(now)
        self.device.show(view)

    def _view(self, now: float):
        if self._mode == "listening":
            return StatusView("listening", "Listening...", "Release when you are done")
        if self._mode == "thinking":
            return StatusView("thinking", "Thinking...", "Turning that into a note")
        if self._mode == "printing":
            return StatusView("printing", "Printing...")
        if self._notice and now < self._notice_until:
            return self._notice
        self._notice = None

        item = self._pick_current()
        if item is None:
            detail = "Hold the blue button to dictate a note"
            if self._pending_triage:
                detail = "Reading new messages..."
            return CardView("idle", "", "All clear", detail, 0, hint="Blue: hold to talk")
        return CardView(item.source, item.sender, item.title, item.detail, self.store.queue_size())

    def state(self) -> dict:
        with self._lock:
            return {
                "mode": self._mode,
                "current": self._current_id,
                "queue": self.store.queue_size(),
                "stats": self.store.stats(),
            }
