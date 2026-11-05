"""Hold the talk button, hear what the board's microphone heard. No speech engine, no agent.

The board streams audio only while button 5 is held, so playback starts when you let go. Each
take is saved twice: `raw` is exactly what the board sent, `boosted` is what Whisper hears after
`pcm_to_float` has removed the DC offset and raised the level.
"""

from __future__ import annotations

import base64
import binascii
import logging
import math
import shutil
import subprocess
import threading
import time
import wave
from pathlib import Path
from typing import Callable, Optional

from .stt import SAMPLE_RATE, pcm_to_float

log = logging.getLogger(__name__)


def write_wav(path: Path, pcm: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm)


def boosted(pcm: bytes) -> bytes:
    import numpy as np

    return (np.clip(pcm_to_float(pcm), -1.0, 1.0) * 32767).astype("<i2").tobytes()


def describe(pcm: bytes) -> str:
    """Duration and level, with a plain-words verdict on whether anything was picked up."""
    import numpy as np

    samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    if samples.size == 0:
        return "no audio"
    centred = samples - samples.mean()
    peak = float(np.abs(centred).max())
    rms = float(np.sqrt((centred ** 2).mean()))
    clipped = float((np.abs(samples) > 0.99).mean())
    db = lambda v: f"{20 * math.log10(v):.0f} dBFS" if v > 0 else "silence"
    verdict = ("nothing picked up: check the microphone in ports 1-2" if peak < 0.002 else
               "very quiet: speak closer, or expect a lot of gain" if peak < 0.02 else
               "clipping: too loud or too close" if clipped > 0.001 else "good level")
    return f"{samples.size / SAMPLE_RATE:.1f} s, peak {db(peak)}, average {db(rms)}: {verdict}"


class MicTest:
    def __init__(self, out_dir: Path, play: Callable[[Path], None], use_boosted: bool = False,
                 say: Callable[[str], None] = print) -> None:
        self.out_dir, self.play, self.use_boosted, self.say = out_dir, play, use_boosted, say
        self._audio: Optional[bytearray] = None
        self.takes = 0
        self._started = 0.0
        self._last_chunk = 0.0
        self._chunks = 0
        self._bad = 0
        self._worst_gap = 0.0

    def on_event(self, key: str, value) -> None:
        if key == "audio_start":
            self._audio = bytearray()
            self._started = self._last_chunk = time.monotonic()
            self._chunks = self._bad = 0
            self._worst_gap = 0.0
            self.say("Recording... let go to hear it.")
        elif key == "audio" and self._audio is not None:
            now = time.monotonic()
            self._worst_gap = max(self._worst_gap, now - self._last_chunk)
            self._last_chunk = now
            self._chunks += 1
            try:
                self._audio += base64.b64decode(value, validate=True)
            except (binascii.Error, TypeError, ValueError):
                self._bad += 1
        elif key == "audio_end" and self._audio is not None:
            pcm, self._audio = bytes(self._audio), None
            info = value if isinstance(value, dict) else {}
            self._finish(pcm, int(info.get("dropped", 0)), int(info.get("samples", 0)), time.monotonic() - self._started)

    def _finish(self, pcm: bytes, dropped: int, sent: int = 0, elapsed: float = 0.0) -> None:
        if not pcm:
            self.say("Nothing arrived.")
            return
        self.takes += 1
        stamp = time.strftime("%H%M%S")
        raw = self.out_dir / f"take-{stamp}-{self.takes}-raw.wav"
        write_wav(raw, pcm)
        loud = self.out_dir / f"take-{stamp}-{self.takes}-boosted.wav"
        write_wav(loud, boosted(pcm))
        self.say(f"  {describe(pcm)}")
        if elapsed:
            heard = len(pcm) / 2 / SAMPLE_RATE
            self.say(f"  link: {heard:.1f} s of audio arrived over {elapsed:.1f} s of holding the button "
                     f"({self._chunks} chunks, longest gap {self._worst_gap * 1000:.0f} ms, {self._bad} corrupt)")
            self.say(f"  board: sent {sent} samples ({sent / SAMPLE_RATE:.1f} s), dropped {dropped} because its buffer was full")
            if heard < elapsed * 0.8:
                self.say(f"  -> only {heard / elapsed:.0%} of the time reached the Mac: the audio is being lost between the microphone and here")
        self.say(f"  saved {raw}")
        self.play(loud if self.use_boosted else raw)


def afplay(path: Path) -> None:
    player = shutil.which("afplay")
    if player is None:
        print(f"  no afplay here: open {path} yourself")
        return
    subprocess.run([player, str(path)], check=False)


def run(port: str, out_dir: Path, use_boosted: bool) -> None:
    from atech import Board

    test = MicTest(out_dir, play=lambda path: threading.Thread(target=afplay, args=(path,), daemon=True).start(),
                   use_boosted=use_boosted)
    with Board.connect(port=port or None) as board:
        print(f"Hold button 5 and talk. Playing the {'boosted' if use_boosted else 'raw'} sound. Ctrl-C to stop.")
        for event in board.events(keys=["audio_start", "audio", "audio_end"]):
            test.on_event(event.key, event.value)
