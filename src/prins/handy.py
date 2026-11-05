"""Drives Handy, the open-source dictation app, from the talk button.

Handy has no "start" or "stop" command, only a toggle, so this keeps track of whether a
hold is in progress. Its transcript comes back through the hook (see scripts/handy-hook.sh).
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Sequence

log = logging.getLogger(__name__)


class Handy:
    def __init__(self, binary: Path) -> None:
        self.binary = binary

    @property
    def installed(self) -> bool:
        return self.binary.exists()

    def _run(self, *args: Sequence[str]) -> bool:
        if not self.installed:
            log.warning("Handy is not installed at %s. Run scripts/install-handy.sh.", self.binary)
            return False
        try:
            # These flags are forwarded to the running Handy, and the launcher exits quickly.
            subprocess.Popen(
                [str(self.binary), *args],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return True
        except OSError as exc:
            log.error("Could not run Handy: %s", exc)
            return False

    def toggle(self) -> bool:
        return self._run("--toggle-transcription")

    def cancel(self) -> bool:
        return self._run("--cancel")
