"""Talks to the label printer's local web server (printer/server.py), and can start it."""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Optional

from PIL import Image

from .design import HEIGHT as CANVAS_HEIGHT, WIDTH as CANVAS_WIDTH
from .drawing import png_bytes

log = logging.getLogger(__name__)

DEFAULT_URL = "http://127.0.0.1:8110"
PRINTER_DIR = Path(__file__).resolve().parents[2] / "printer"
_PRINT_TIMEOUT_S = 90.0  # Each print reconnects over Bluetooth, about 5 s, and prints are queued.


class PrinterError(Exception):
    """The label did not print. The message is safe to show on the screen."""


class LabelPrinter:
    def __init__(self, url: str = DEFAULT_URL, dry_run: bool = False) -> None:
        self.url = url.rstrip("/")
        self.dry_run = dry_run

    def canvas(self) -> tuple[int, int]:
        """The pixel grid the server prints, or the calibrated default when it is not running."""
        try:
            with urllib.request.urlopen(f"{self.url}/canvas", timeout=3) as response:
                info = json.load(response)
            return int(info["width"]), int(info["height"])
        except (urllib.error.URLError, OSError, ValueError, KeyError):
            return CANVAS_WIDTH, CANVAS_HEIGHT

    def reachable(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/canvas", timeout=2):
                return True
        except (urllib.error.URLError, OSError):
            return False

    def print_image(self, image: Image.Image) -> dict:
        request = urllib.request.Request(
            f"{self.url}/print/png" + ("?dry_run=true" if self.dry_run else ""),
            data=png_bytes(image),
            headers={"Content-Type": "image/png"},
        )
        try:
            with urllib.request.urlopen(request, timeout=_PRINT_TIMEOUT_S) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = str(json.load(exc).get("detail", ""))
            except (ValueError, OSError):
                pass
            if exc.code == 503:
                raise PrinterError(f"Printer not found: {detail or 'is it on and free of the phone app?'}") from exc
            raise PrinterError(f"Printer server said {exc.code}: {detail}") from exc
        except (urllib.error.URLError, OSError) as exc:
            raise PrinterError("Printer server is not running (uv run server.py in printer/)") from exc


class PrinterServer:
    """Starts `uv run server.py` in printer/ unless something already answers on the port."""

    def __init__(self, printer: LabelPrinter, directory: Path = PRINTER_DIR) -> None:
        self.printer = printer
        self.directory = directory
        self.process: Optional[subprocess.Popen] = None

    def start(self, wait_s: float = 120.0) -> None:
        if self.printer.reachable():
            log.info("Printer server already running at %s.", self.printer.url)
            return
        uv = shutil.which("uv")
        if uv is None:
            raise PrinterError("uv is not installed, so the printer server cannot start: https://docs.astral.sh/uv/")
        log.info("Starting the printer server (the first run installs its dependencies)...")
        self.process = subprocess.Popen([uv, "run", "server.py"], cwd=self.directory)
        deadline = time.monotonic() + wait_s
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise PrinterError(f"The printer server exited with code {self.process.returncode}.")
            if self.printer.reachable():
                log.info("Printer server is up.")
                return
            time.sleep(0.5)
        raise PrinterError("The printer server did not start in time.")

    def stop(self) -> None:
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
