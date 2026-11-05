"""The label maker: hold talk and describe a label, look at it, print it.

Button 5 (talk) records, 6 prints, 4 throws the design away. The board streams the microphone
while talk is held; this module turns the audio into text, asks the drawing agent for a
design, shows it on the board and prints it on request. The lights follow `state`.
"""

from __future__ import annotations

import base64
import binascii
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from .designer import Design, Designer
from .labelboard import LabelDevice
from .labelprinter import LabelPrinter, PrinterError
from .stt import SAMPLE_RATE, Transcriber

log = logging.getLogger(__name__)

IDLE, LISTENING, THINKING, READY, PRINTING, ERROR = "idle", "listening", "thinking", "ready", "printing", "error"

_MIN_SECONDS = 0.4          # A shorter hold is a bump, not a sentence.
_MAX_SECONDS = 60.0         # Cap the buffer if the board never says it is done.
_ERROR_SHOWN_S = 8.0
_HINTS = "6 print 5 edit 4 drop"
_IDLE_DETAIL = "Hold button 5 and describe a label"

Scheduler = Callable[[float, Callable[[], None]], None]


def _after(delay: float, fn: Callable[[], None]) -> None:
    timer = threading.Timer(delay, fn)
    timer.daemon = True
    timer.start()


class LabelMaker:
    def __init__(
        self,
        device: LabelDevice,
        stt: Transcriber,
        designer: Designer,
        printer: LabelPrinter,
        save_dir: Optional[Path] = None,
        synchronous: bool = False,
        schedule: Scheduler = _after,
    ) -> None:
        self.device, self.stt, self.designer, self.printer = device, stt, designer, printer
        self.save_dir = save_dir
        self.synchronous = synchronous  # Run the slow work in the caller's thread, for tests.
        self._schedule = schedule
        self._lock = threading.RLock()
        self.state = IDLE
        self.design: Optional[Design] = None
        self.history: list[str] = []
        self.version = 0
        self._resume = IDLE            # What listening goes back to when nothing comes of it.
        self._audio = bytearray()
        self._generation = 0           # Bumped by discard, so work that finished too late is dropped.

    # ---- Board events ----------------------------------------------------------------

    def start(self) -> None:
        self.device.start(self.on_event)
        self._show(IDLE, "Prins", _IDLE_DETAIL)

    def on_event(self, key: str, value) -> None:
        if key == "audio_start":
            self._audio_start()
        elif key == "audio":
            self._audio_chunk(value)
        elif key == "audio_end":
            self._audio_end(value)
        elif key == "printbtn" and value:
            self._print()
        elif key == "discard" and value:
            self._discard()

    def _audio_start(self) -> None:
        with self._lock:
            if self.state in (THINKING, PRINTING):
                return  # The board refuses to stream in these states too.
            self._resume = READY if self.design else IDLE
            self.state = LISTENING
            self._audio = bytearray()

    def _audio_chunk(self, value) -> None:
        with self._lock:
            if self.state != LISTENING or len(self._audio) > _MAX_SECONDS * SAMPLE_RATE * 2:
                return
            try:
                self._audio += base64.b64decode(value, validate=True)
            except (binascii.Error, TypeError, ValueError):
                log.warning("Dropped a corrupt audio chunk.")

    def _audio_end(self, value) -> None:
        with self._lock:
            if self.state != LISTENING:
                return
            pcm, self._audio = bytes(self._audio), bytearray()
            seconds = len(pcm) / 2 / SAMPLE_RATE
            dropped = value.get("dropped", 0) if isinstance(value, dict) else 0
            if dropped:
                log.warning("The board dropped %s audio samples; the sentence may be cut.", dropped)
            if seconds < _MIN_SECONDS:
                self._show(self._resume, "Too short", "Hold the button while you talk")
                self._schedule(2.0, lambda: self._restore(from_state=self._resume))
                return
            generation = self._generation
            self._show(THINKING, "Thinking", "Listening back...")
        self._work(lambda: self._make_design(generation, pcm))

    # ---- The slow part: speech, then drawing -------------------------------------------

    def _work(self, job: Callable[[], None]) -> None:
        if self.synchronous:
            job()
        else:
            threading.Thread(target=job, name="label-work", daemon=True).start()

    def _make_design(self, generation: int, pcm: bytes) -> None:
        try:
            text = self.stt.transcribe(pcm)
        except Exception as exc:
            log.exception("Speech to text failed")
            return self._fail(generation, "No speech engine", str(exc))
        if not text:
            return self._back(generation, "Heard nothing", "Try again, closer to the mic")
        with self._lock:
            if generation != self._generation:
                return
            self._show(THINKING, "Drawing", text)
            current, history = self.design, list(self.history)
        try:
            design = self.designer.design(text, current, history)
        except Exception as exc:
            log.exception("The agent failed")
            return self._fail(generation, "No design", str(exc))
        with self._lock:
            if generation != self._generation:
                return  # Discarded while the agent worked.
            self.design = design
            self.history.append(text)
            self.version += 1
            self._save(design)
            if design.warnings:
                log.warning("Design still has problems: %s", "; ".join(design.warnings))
            log.info("Design v%d (%s): %s", self.version, design.title, design.summary)
            self.device.show_preview(design.image)
            self._show(READY, "Ready", _HINTS)

    def _fail(self, generation: int, title: str, detail: str) -> None:
        with self._lock:
            if generation != self._generation:
                return
            self._show(ERROR, title, detail)
            self._schedule(_ERROR_SHOWN_S, lambda: self._restore(from_state=ERROR))

    def _back(self, generation: int, title: str, detail: str) -> None:
        """Nothing came of the recording: say so, then go back to where we were."""
        with self._lock:
            if generation != self._generation:
                return
            self._show(self._resume, title, detail)
            self._schedule(3.0, lambda: self._restore(from_state=self._resume))

    def _restore(self, from_state: str) -> None:
        """Back to the resting screen, unless something else has happened since."""
        with self._lock:
            if self.state != from_state:
                return
            if self.design:
                self.device.show_preview(self.design.image)
                self._show(READY, "Ready", _HINTS)
            else:
                self._show(IDLE, "Prins", _IDLE_DETAIL)

    # ---- Buttons -------------------------------------------------------------------------

    def _print(self) -> None:
        with self._lock:
            if self.state != READY or self.design is None:
                return
            design, generation = self.design, self._generation
            self._show(PRINTING, "Printing", "About ten seconds")
        self._work(lambda: self._send_to_printer(design, generation))

    def _send_to_printer(self, design: Design, generation: int) -> None:
        try:
            self.printer.print_image(design.image)
        except PrinterError as exc:
            log.error("Printing failed: %s", exc)
            return self._fail(generation, "Not printed", str(exc))
        with self._lock:
            if generation != self._generation:
                return
            # The design stays, so a second copy is one more press.
            self._show(READY, "Printed", "6 again 5 edit 4 drop")
            self._schedule(5.0, lambda: self._restore(from_state=READY))

    def _discard(self) -> None:
        with self._lock:
            if self.state in (LISTENING, PRINTING) or (self.design is None and self.state != THINKING):
                return
            self._generation += 1
            self.design, self.history, self._audio = None, [], bytearray()
            self._show(IDLE, "Dropped", _IDLE_DETAIL)

    # ---- Output --------------------------------------------------------------------------

    def _show(self, state: str, title: str, detail: str = "") -> None:
        self.state = state
        self.device.set_state(state, title, detail, design=self.design is not None, preview=state in (READY, PRINTING, ERROR) and self.design is not None)

    def _save(self, design: Design) -> None:
        if self.save_dir is None:
            return
        try:
            self.save_dir.mkdir(parents=True, exist_ok=True)
            path = self.save_dir / f"label-{time.strftime('%Y%m%d-%H%M%S')}-v{self.version}.png"
            design.image.save(path)
        except OSError as exc:
            log.warning("Could not save the design: %s", exc)
