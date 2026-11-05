"""Speech to text on this Mac. The audio never leaves it.

The board streams 16-bit mono PCM at 16 kHz. Whisper runs through faster-whisper
(`pip install -e ".[labels]"`); the model downloads from Hugging Face the first time it is used.
"""

from __future__ import annotations

import logging
import threading
from typing import Protocol

log = logging.getLogger(__name__)

SAMPLE_RATE = 16000
_TARGET_PEAK = 0.7
_MAX_GAIN = 40.0  # The board's microphone is quiet; more gain than this only amplifies noise.


class Transcriber(Protocol):
    def transcribe(self, pcm: bytes) -> str: ...


def pcm_to_float(pcm: bytes):
    """int16 little-endian bytes to float32 in [-1, 1], with the DC offset removed and the level raised."""
    import numpy as np

    samples = np.frombuffer(pcm[: len(pcm) // 2 * 2], dtype="<i2").astype(np.float32) / 32768.0
    if samples.size == 0:
        return samples
    samples -= samples.mean()
    peak = float(np.abs(samples).max())
    if peak > 0:
        samples *= min(_TARGET_PEAK / peak, _MAX_GAIN)
    return samples


class WhisperTranscriber:
    def __init__(self, model: str = "turbo", language: str = "") -> None:
        self.model_name = model
        self.language = language or None  # None: Whisper detects the language
        self._model = None
        self._lock = threading.Lock()

    def warm(self) -> None:
        """Load the model now, so the first sentence is not slowed down by it."""
        self._load()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    from faster_whisper import WhisperModel
                except ImportError as exc:
                    raise RuntimeError('Speech to text needs faster-whisper: pip install -e ".[labels]"') from exc
                log.info("Loading Whisper model %r (downloads on first use)...", self.model_name)
                self._model = WhisperModel(self.model_name, device="cpu", compute_type="int8")
                log.info("Whisper is ready.")
            return self._model

    def transcribe(self, pcm: bytes) -> str:
        audio = pcm_to_float(pcm)
        if audio.size < SAMPLE_RATE // 4:
            return ""
        model = self._load()
        segments, info = model.transcribe(audio, language=self.language, beam_size=1, vad_filter=True,
                                          condition_on_previous_text=False)
        text = " ".join(segment.text.strip() for segment in segments).strip()
        log.info("Heard (%s): %s", info.language, text)
        return text
