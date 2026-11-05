from __future__ import annotations

import pytest

from prins.device import SimDevice
from prins.engine import Engine
from prins.store import Store
from prins.triage import Triage


class FakeDictation:
    def __init__(self, works: bool = True) -> None:
        self.calls: list[str] = []
        self.works = works

    def toggle(self) -> bool:
        self.calls.append("toggle")
        return self.works

    def cancel(self) -> bool:
        self.calls.append("cancel")
        return True


class FakePrinter:
    def __init__(self) -> None:
        self.printed: list[str] = []
        self.error: Exception | None = None

    def print_image(self, image, label: str) -> str:
        if self.error:
            raise self.error
        self.printed.append(label)
        return "ok"


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


class Rig:
    def __init__(self) -> None:
        self.store = Store(":memory:")
        self.device = SimDevice(output=lambda _text: None)
        self.printer = FakePrinter()
        self.dictation = FakeDictation()
        self.clock = Clock()
        self.engine = Engine(
            store=self.store,
            triage=Triage(None),  # Plain text fallback: no network in tests.
            device=self.device,
            printer=self.printer,
            dictation=self.dictation,
            clock=self.clock,
            synchronous=True,
        )
        self.engine.start()

    def message(self, text: str, source: str = "slack", sender: str = "Maria", external_id=None) -> None:
        self.engine.ingest(source=source, sender=sender, text=text, external_id=external_id)

    def hold_talk(self, seconds: float = 2.0) -> None:
        self.device.press("talk", True)
        self.clock.now += seconds
        self.device.press("talk", False)


@pytest.fixture
def rig() -> Rig:
    return Rig()
