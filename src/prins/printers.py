"""Where confirmed notes go. All three take the same rendered note."""

from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
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

    def __init__(self, port: str, baud: int, bytes_per_sec: int, paper_dots: int = 384) -> None:
        self.port, self.baud, self.bytes_per_sec, self.paper_dots = port, baud, bytes_per_sec, paper_dots

    def print_image(self, image: Image.Image, label: str) -> str:
        import serial

        data = to_escpos(image, paper_dots=self.paper_dots)
        try:
            with serial.Serial(self.port, self.baud, timeout=5, write_timeout=10) as link:
                for start in range(0, len(data), 64):
                    link.write(data[start : start + 64])
                    time.sleep(64 / self.bytes_per_sec)
                link.flush()
        except (serial.SerialException, OSError) as exc:
            raise PrintError(f"printer on {self.port}: {exc}") from exc
        return f"{len(data)} bytes to {self.port}"


class M110Printer:
    """The Clas Ohlson M110 label printer, through the local API in printer/server.py.

    That server owns the Bluetooth connection and the calibrated label geometry: only the last
    312 of the 384 dots land on the label, after 20 blank rows. So notes must go through it and
    not through to_escpos. Its 1bpp format is the same as a note bitmap.
    """

    def __init__(self, url: str = "http://127.0.0.1:8110", dry_run: bool = False) -> None:
        self.url, self.dry_run = url.rstrip("/"), dry_run

    def print_image(self, image: Image.Image, label: str) -> str:
        packed = bytes(b ^ 0xFF for b in image.convert("1").tobytes())
        body = {
            "width": image.width,
            "height": image.height,
            "format": "1bpp",
            "data": base64.b64encode(packed).decode("ascii"),
            "dry_run": self.dry_run,
        }
        request = urllib.request.Request(
            f"{self.url}/print", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"}
        )
        try:
            # A print reconnects over Bluetooth and waits for the printer, which takes seconds.
            with urllib.request.urlopen(request, timeout=60) as response:
                result = json.loads(response.read())
        except urllib.error.HTTPError as exc:
            raise PrintError(_server_error(exc)) from exc
        except (urllib.error.URLError, OSError) as exc:
            raise PrintError("The printer server isn't running: cd printer && uv run server.py") from exc
        return f"{result.get('black_pixels')} black pixels to the M110"

    def reachable(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/canvas", timeout=2) as response:
                return response.status == 200
        except (urllib.error.URLError, OSError):
            return False


def _server_error(exc: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(exc.read()).get("detail", exc))
    except ValueError:
        return str(exc)


class AtechPrinter:
    """A TTL printer on the board's UART port, fed through the thermal_printer module."""

    def __init__(
        self,
        call: Callable[..., None],
        query: Callable[..., object],
        baud: int,
        bytes_per_sec: int,
        sleep: Callable[[float], None] = time.sleep,
        paper_dots: int = 0,
    ) -> None:
        self._call, self._query, self._sleep = call, query, sleep
        self.paper_dots = paper_dots
        self.baud, self.bytes_per_sec = baud, bytes_per_sec

    def print_image(self, image: Image.Image, label: str) -> str:
        from atech import ActionRejected, NoAcknowledgement

        data = to_escpos(image, paper_dots=self.paper_dots)
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
