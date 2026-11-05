"""Where confirmed notes go. All three take the same rendered note."""

from __future__ import annotations

import base64
import time
from pathlib import Path
from typing import Callable, Protocol

from PIL import Image

from .render import to_escpos

CHUNK_BYTES = 2400  # Matches ThermalPrinter::MAX_CHUNK_BYTES in the firmware.
_DRAIN_TIMEOUT_S = 90.0


class PrintError(RuntimeError):
    pass


class Printer(Protocol):
    def print_image(self, image: Image.Image, label: str) -> str:
        """Prints and returns a short description. Raises PrintError on failure."""


class PreviewPrinter:
    """No hardware: saves what would have printed as a PNG."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory

    def print_image(self, image: Image.Image, label: str) -> str:
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{time.strftime('%Y%m%d-%H%M%S')}-{label}.png"
        image.save(path)
        return str(path)


class SerialPrinter:
    """A printer that appears as a serial port on the Mac, by USB or paired Bluetooth."""

    def __init__(self, port: str, baud: int, bytes_per_sec: int) -> None:
        self.port, self.baud, self.bytes_per_sec = port, baud, bytes_per_sec

    def print_image(self, image: Image.Image, label: str) -> str:
        import serial

        data = to_escpos(image)
        try:
            with serial.Serial(self.port, self.baud, timeout=5, write_timeout=10) as link:
                for start in range(0, len(data), 64):
                    link.write(data[start : start + 64])
                    time.sleep(64 / self.bytes_per_sec)
                link.flush()
        except (serial.SerialException, OSError) as exc:
            raise PrintError(f"printer on {self.port}: {exc}") from exc
        return f"{len(data)} bytes to {self.port}"


class AtechPrinter:
    """A TTL printer on the board's UART port, fed through the thermal_printer module."""

    def __init__(
        self,
        call: Callable[..., None],
        query: Callable[..., object],
        baud: int,
        bytes_per_sec: int,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._call, self._query, self._sleep = call, query, sleep
        self.baud, self.bytes_per_sec = baud, bytes_per_sec

    def print_image(self, image: Image.Image, label: str) -> str:
        from atech import ActionRejected, NoAcknowledgement

        data = to_escpos(image)
        try:
            self._call("printer_config", {"baud": self.baud, "bytes_per_sec": self.bytes_per_sec})
            for start in range(0, len(data), CHUNK_BYTES):
                self._send_chunk(data[start : start + CHUNK_BYTES])
            self._wait_for_drain()
        except (ActionRejected, NoAcknowledgement) as exc:
            raise PrintError(str(exc)) from exc
        return f"{len(data)} bytes through the board"

    def _send_chunk(self, chunk: bytes) -> None:
        from atech import ActionRejected

        encoded = base64.b64encode(chunk).decode("ascii")
        deadline = time.monotonic() + _DRAIN_TIMEOUT_S
        while True:
            try:
                self._call("printer_write", encoded)
                return
            except ActionRejected as exc:
                if "busy" not in str(exc) or time.monotonic() > deadline:
                    raise
                self._sleep(0.25)  # The queue is full: let the printer catch up.

    def _wait_for_drain(self) -> None:
        deadline = time.monotonic() + _DRAIN_TIMEOUT_S
        while time.monotonic() < deadline:
            if int(self._query("printer_status", reply="printer_pending")) == 0:
                return
            self._sleep(0.25)
        raise PrintError("the printer queue did not empty in time")
