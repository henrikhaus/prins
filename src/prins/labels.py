"""The label maker: hold talk and describe a label, look at it, print it.

Button 5 (talk) records, 6 prints, 4 throws the design away. The board streams the microphone
while talk is held; this module turns the audio into text, asks the drawing agent for a
design, shows it on the board and prints it on request. The lights follow `state`.

Messages from the inbox (src/prins/inbox.py) come in through `incoming`. The agent turns each one
into a task note or a design, or skips it. Finished ones wait in a queue and never replace what is
on the screen: the next one appears when the current one is discarded. Whatever is on the screen,
a message's or your own, can be printed, discarded or changed by voice.
"""

from __future__ import annotations

import base64
import binascii
import logging
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .inbox import Incoming
from .labeldesigner import Design, LabelDesigner
from .labelboard import LabelDevice
from .labelprinter import LabelPrinter, PrinterError
from .stt import SAMPLE_RATE, Transcriber

log = logging.getLogger(__name__)

IDLE, LISTENING, THINKING, READY, PRINTING, ERROR = "idle", "listening", "thinking", "ready", "printing", "error"

_MIN_SECONDS = 0.4          # A shorter hold is a bump, not a sentence.
_MAX_SECONDS = 60.0         # Cap the buffer if the board never says it is done.
_ERROR_SHOWN_S = 8.0
_MAX_QUEUE = 25             # Finished messages waiting. Beyond this the oldest wait outside, in System Zero.
_IDLE_DETAIL = "Hold button 5 and describe a label"

Scheduler = Callable[[float, Callable[[], None]], None]


@dataclass
class _Waiting:
    sender: str
    text: str
    design: Design


def _after(delay: float, fn: Callable[[], None]) -> None:
    timer = threading.Timer(delay, fn)
    timer.daemon = True
    timer.start()


class LabelMaker:
    def __init__(
        self,
        device: LabelDevice,
        stt: Transcriber,
        designer: LabelDesigner,
        printer: LabelPrinter,
        save_dir: Optional[Path] = None,
        synchronous: bool = False,
        schedule: Scheduler = _after,
        max_incoming_per_hour: int = 20,
        clock: Callable[[], float] = time.monotonic,
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
        self.origin = ""               # Who the design on the screen is from, "" for your own.
        self._queue: deque[_Waiting] = deque()
        self._max_incoming_per_hour, self._clock = max_incoming_per_hour, clock
        self._incoming_times: deque[float] = deque()
        self._intake_jobs: queue.Queue = queue.Queue()
        self._intake_thread: Optional[threading.Thread] = None

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
            self._show_ready()

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
                self._show_ready()
            elif self._queue:
                self._present(self._queue.popleft())
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
            self._show_ready("Printed", self._hint(again=True))
            self._schedule(5.0, lambda: self._restore(from_state=READY))

    def _discard(self) -> None:
        with self._lock:
            if self.state in (LISTENING, PRINTING) or (self.design is None and self.state != THINKING):
                return
            self._generation += 1
            self.design, self.history, self.origin, self._audio = None, [], "", bytearray()
            if self._queue:
                self._present(self._queue.popleft())  # Discard moves on to the next message.
            else:
                self._show(IDLE, "Dropped", _IDLE_DETAIL)

    # ---- Messages -------------------------------------------------------------------------

    def incoming(self, message: Incoming) -> None:
        """A message for the person. It becomes a design in the background and waits its turn.

        Over the hourly limit it still arrives, as plain text: nothing is lost, and nothing costs."""
        with self._lock:
            now = self._clock()
            while self._incoming_times and now - self._incoming_times[0] > 3600:
                self._incoming_times.popleft()
            over = len(self._incoming_times) >= self._max_incoming_per_hour
            self._incoming_times.append(now)
        if self.synchronous:
            self._intake(message, over)
            return
        with self._lock:
            if self._intake_thread is None:
                self._intake_thread = threading.Thread(target=self._intake_loop, name="label-intake", daemon=True)
                self._intake_thread.start()
        self._intake_jobs.put((message, over))

    def _intake_loop(self) -> None:
        while True:  # One at a time and in order, so the queue keeps the order the messages came in.
            message, over = self._intake_jobs.get()
            try:
                self._intake(message, over)
            except Exception:
                log.exception("Could not handle a message from %s", message.sender)

    def _intake(self, message: Incoming, over: bool) -> None:
        footer = f"from {message.sender}"
        design: Optional[Design]
        if over:
            log.warning("Over %d messages in an hour: showing the one from %s as plain text.", self._max_incoming_per_hour, message.sender)
            design = Design.plain_note(message.text, footer)
        else:
            try:
                design = self.designer.design_message(message.sender, message.text)
            except Exception:
                log.exception("The agent failed on a message from %s; showing it as plain text", message.sender)
                design = Design.plain_note(message.text, footer)
        if design is None:
            return  # The agent decided it needs nothing on the desk.
        with self._lock:
            if len(self._queue) >= _MAX_QUEUE:
                log.warning("%d messages are already waiting; dropping the oldest.", _MAX_QUEUE)
                self._queue.popleft()
            self._queue.append(_Waiting(message.sender, message.text, design))
            log.info("Message from %s ready (%s): %s", message.sender, design.title, design.summary)
            if self.design is None and self.state == IDLE:
                self._present(self._queue.popleft())
            elif self.state == READY and self.design is not None:
                self._show_ready()  # Only the count of waiting messages changed.

    def _present(self, item: _Waiting) -> None:
        """Put a message's design on the screen. The caller holds the lock."""
        self.design, self.history, self.origin = item.design, [item.text], item.sender
        self.version += 1
        self._save(item.design)
        log.info("Showing the message from %s (%d more waiting).", item.sender, len(self._queue))
        self.device.show_preview(item.design.image)
        self._show_ready()

    def _hint(self, again: bool = False) -> str:
        drop = "4 next" if self._queue else "4 drop"
        more = f" +{len(self._queue)}" if self._queue else ""
        return f"6 {'again' if again else 'print'} 5 edit {drop}{more}"

    def _show_ready(self, title: Optional[str] = None, detail: Optional[str] = None) -> None:
        """The design on the screen. A message's design is titled with who it is from; the right column is six characters wide."""
        shown = title or (self.origin.split()[0][:12] if self.origin.strip() else "Ready")
        self._show(READY, shown, detail or self._hint())

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
