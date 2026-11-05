"""The label maker: drawing, the drawing agent, the state machine and the wire format."""

from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from atech.runtime.models import Action
from atech.runtime.transport import encode_action
from PIL import Image

from prins.designer import Design, Designer, DesignError, DesignOut, Op
from prins.drawing import CANVAS_HEIGHT, CANVAS_WIDTH, render_design, thumbnail_2bpp
from prins.labelboard import LabelBoard
from prins.labelprinter import PrinterError
from prins.labels import ERROR, IDLE, LISTENING, PRINTING, READY, THINKING, LabelMaker

HEADLINE = {"type": "text", "x": 156, "y": 20, "text": "Dentist", "size": 48, "bold": True, "align": "center"}


def wire(key: str, value) -> str:
    return encode_action(Action(key=key, value=value)).decode()


def make_design(ops=None, title="Dentist", summary="Drew it") -> Design:
    ops = ops if ops is not None else [HEADLINE]
    rendered = render_design(ops)
    return Design(ops, title, summary, rendered, rendered.warnings)


# --- drawing ------------------------------------------------------------------------


def test_render_is_one_bit_and_label_sized():
    out = render_design([HEADLINE, {"type": "rect", "x": 4, "y": 4, "w": 304, "h": 208, "radius": 12}])
    assert out.image.mode == "1" and out.image.size == (CANVAS_WIDTH, CANVAS_HEIGHT)
    assert out.warnings == []
    assert 0.02 < out.ink < 0.5


def test_text_running_off_the_label_comes_back_as_a_warning_the_model_can_act_on():
    out = render_design([{"type": "text", "x": 10, "y": 10, "text": "x" * 60, "size": 40}])
    assert any("right edge" in w for w in out.warnings)


def test_tiny_text_blank_labels_and_solid_black_are_flagged():
    assert any("at least" in w for w in render_design([{"type": "text", "x": 5, "y": 5, "text": "tiny", "size": 8}]).warnings)
    assert any("blank" in w for w in render_design([]).warnings)
    assert any("black" in w for w in render_design([{"type": "rect", "x": 0, "y": 0, "w": 312, "h": 216, "fill": "black"}]).warnings)


def test_bad_ops_are_reported_not_raised():
    out = render_design([{"type": "circle"}, {"type": "rect", "x": 1}, {"type": "polygon", "points": "no"}, HEADLINE])
    assert len(out.warnings) == 3


def test_every_shape_draws():
    ops = [
        {"type": "rect", "x": 10, "y": 10, "w": 80, "h": 60, "fill": "gray"},
        {"type": "ellipse", "x": 100, "y": 10, "w": 60, "h": 60, "fill": "light"},
        {"type": "polygon", "points": [[200, 70], [230, 10], [260, 70]], "fill": "black"},
        {"type": "polyline", "points": [[10, 100], [150, 130], [300, 100]], "width": 4},
        {"type": "text", "x": 20, "y": 150, "text": "Blåbær Ærlig Øl", "size": 30},
    ]
    out = render_design(ops)
    assert out.warnings == []


def test_white_text_on_a_black_banner_is_visible():
    plain = render_design([{"type": "rect", "x": 10, "y": 10, "w": 290, "h": 70, "fill": "black"}]).ink
    knocked = render_design([
        {"type": "rect", "x": 10, "y": 10, "w": 290, "h": 70, "fill": "black"},
        {"type": "text", "x": 155, "y": 20, "text": "SALE", "size": 48, "bold": True, "align": "center", "color": "white"},
    ]).ink
    assert knocked < plain


def test_thumbnail_fits_the_screen_and_one_serial_line():
    width, height, data = thumbnail_2bpp(render_design([HEADLINE]).image)
    assert width <= 120 and height <= 80
    assert len(data) == ((width + 3) // 4) * height <= 2400
    line = wire("ui_preview", f"{width},{height}:{base64.b64encode(data).decode()}")
    assert len(line) < 4096 and line.isascii()


def test_thumbnail_keeps_black_black_and_white_white():
    black = thumbnail_2bpp(Image.new("1", (312, 216), 0))[2]
    white = thumbnail_2bpp(Image.new("1", (312, 216), 1))[2]
    assert set(black) == {0x00} and set(white) == {0xFF}


# --- the drawing agent ---------------------------------------------------------------


class FakeClient:
    """Stands in for anthropic.Anthropic: answers each messages.parse call from a script."""

    def __init__(self, *answers: DesignOut) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(parse=self._parse)

    def _parse(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(parsed_output=self.answers.pop(0), stop_reason="end_turn")


def out(*ops: Op, title="Dentist", summary="Drew it") -> DesignOut:
    return DesignOut(title=title, summary=summary, ops=list(ops))


GOOD = Op(type="text", x=156, y=20, text="Dentist", size=48, bold=True, align="center")
TOO_WIDE = Op(type="text", x=10, y=20, text="x" * 60, size=48)


def test_designer_returns_a_clean_first_design_in_one_call():
    client = FakeClient(out(GOOD))
    design = Designer(client).design("a label that says dentist")
    assert len(client.calls) == 1 and design.title == "Dentist" and design.warnings == []
    assert "<spoken_instruction>" in client.calls[0]["messages"][0]["content"][-1]["text"]


def test_designer_shows_the_model_its_problems_and_takes_the_fix():
    client = FakeClient(out(TOO_WIDE), out(GOOD))
    design = Designer(client).design("dentist")
    assert len(client.calls) == 2 and design.warnings == []
    feedback = client.calls[1]["messages"][-1]["content"]
    assert "right edge" in feedback


def test_designer_gives_up_after_three_tries_but_keeps_the_last_design():
    client = FakeClient(out(TOO_WIDE), out(TOO_WIDE), out(TOO_WIDE))
    design = Designer(client).design("dentist")
    assert len(client.calls) == 3 and design.warnings


def test_designer_sends_the_current_design_as_picture_and_shapes_when_revising():
    client = FakeClient(out(GOOD))
    current = make_design()
    Designer(client).design("make it bigger", current, history=["a dentist label"])
    content = client.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert json.dumps(current.ops) in content[-1]["text"] and "a dentist label" in content[-1]["text"]


def test_a_blank_design_is_an_error_and_so_is_no_model():
    with pytest.raises(DesignError):
        Designer(FakeClient(out(), out(), out())).design("nothing")
    with pytest.raises(DesignError):
        Designer(None).design("anything")


# --- the label maker -----------------------------------------------------------------


class FakeDevice:
    def __init__(self) -> None:
        self.states: list[dict] = []
        self.previews = 0
        self.handler = None

    def start(self, on_event) -> None:
        self.handler = on_event

    def set_state(self, state, title, detail="", *, design, preview) -> None:
        self.states.append(dict(state=state, title=title, detail=detail, design=design, preview=preview))

    def show_preview(self, image) -> None:
        self.previews += 1

    def close(self) -> None:
        pass

    @property
    def last(self) -> dict:
        return self.states[-1]


class FakeStt:
    def __init__(self, *texts: str) -> None:
        self.texts = list(texts)
        self.heard: list[int] = []

    def transcribe(self, pcm: bytes) -> str:
        self.heard.append(len(pcm))
        return self.texts.pop(0)


class FakeDesigner:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail: Exception | None = None
        self.before_returning = None

    def design(self, instruction, current=None, history=None) -> Design:
        self.calls.append((instruction, current, list(history or [])))
        if self.before_returning:
            self.before_returning()
        if self.fail:
            raise self.fail
        return make_design(summary=instruction)


class FakePrinter:
    def __init__(self) -> None:
        self.printed: list[Image.Image] = []
        self.error: Exception | None = None

    def print_image(self, image) -> dict:
        if self.error:
            raise self.error
        self.printed.append(image)
        return {"printed": True}


class Rig:
    def __init__(self, *texts: str, tmp_path=None) -> None:
        self.device, self.stt, self.designer, self.printer = FakeDevice(), FakeStt(*texts), FakeDesigner(), FakePrinter()
        self.scheduled: list = []
        self.maker = LabelMaker(self.device, self.stt, self.designer, self.printer, save_dir=tmp_path,
                                synchronous=True, schedule=lambda delay, fn: self.scheduled.append((delay, fn)))
        self.maker.start()

    def speak(self, seconds: float = 2.0, dropped: int = 0) -> None:
        """What the board sends for one hold of the talk button."""
        samples = int(seconds * 16000)
        self.maker.on_event("audio_start", 1)
        pcm = b"\x01\x00" * samples
        for start in range(0, len(pcm), 2400):
            self.maker.on_event("audio", base64.b64encode(pcm[start:start + 2400]).decode())
        self.maker.on_event("audio_end", {"samples": samples, "dropped": dropped})

    def press(self, key: str) -> None:
        self.maker.on_event(key, 1)
        self.maker.on_event(key, 0)

    def run_timers(self) -> None:
        timers, self.scheduled = self.scheduled, []
        for _delay, fn in timers:
            fn()


@pytest.fixture
def rig(tmp_path):
    return Rig("a dentist label", "make it bigger", "start with the date", tmp_path=tmp_path)


def test_starts_idle_with_every_light_waiting(rig):
    assert rig.device.last == dict(state=IDLE, title="Prins", detail="Hold button 5 and describe a label", design=False, preview=False)


def test_talking_makes_a_design_and_shows_it(rig, tmp_path):
    rig.speak()
    assert rig.device.last["state"] == READY and rig.device.last["design"] and rig.device.last["preview"]
    assert rig.device.previews == 1
    assert rig.designer.calls[0][0] == "a dentist label" and rig.designer.calls[0][1] is None
    assert len(list(tmp_path.glob("label-*-v1.png"))) == 1
    states = [s["state"] for s in rig.device.states]
    assert states == [IDLE, THINKING, THINKING, READY]  # Listening is drawn by the board itself.


def test_screen_shows_what_it_heard_while_the_agent_works(rig):
    rig.speak()
    assert any(s["state"] == THINKING and s["detail"] == "a dentist label" for s in rig.device.states)


def test_holding_again_revises_the_design_with_the_history(rig):
    rig.speak()
    first = rig.maker.design
    rig.speak()
    instruction, current, history = rig.designer.calls[1]
    assert instruction == "make it bigger" and current is first and history == ["a dentist label"]
    assert rig.maker.version == 2 and rig.maker.design is not first


def test_a_bump_of_the_button_is_not_a_sentence(rig):
    rig.speak(seconds=0.1)
    assert rig.stt.heard == [] and rig.device.last["title"] == "Too short" and rig.device.last["state"] == IDLE
    rig.run_timers()
    assert rig.device.last["title"] == "Prins"


def test_short_hold_while_a_design_exists_returns_to_ready(rig):
    rig.speak()
    rig.speak(seconds=0.1)
    assert rig.device.last["state"] == READY and rig.device.last["title"] == "Too short"
    rig.run_timers()
    assert rig.device.last["state"] == READY and rig.device.last["title"] == "Ready"


def test_silence_says_so_and_changes_nothing():
    rig = Rig("")
    rig.speak()
    assert rig.device.last["title"] == "Heard nothing" and rig.designer.calls == [] and rig.maker.design is None


def test_print_is_ignored_until_there_is_a_design(rig):
    rig.press("printbtn")
    assert rig.printer.printed == [] and rig.device.last["state"] == IDLE


def test_print_sends_the_design_and_keeps_it_for_another_copy(rig):
    rig.speak()
    design = rig.maker.design
    rig.press("printbtn")
    assert rig.printer.printed == [design.image]
    assert [s["state"] for s in rig.device.states][-2:] == [PRINTING, READY] and rig.device.last["title"] == "Printed"
    rig.press("printbtn")
    assert len(rig.printer.printed) == 2


def test_a_printer_that_is_off_shows_an_error_then_recovers_with_the_design_intact(rig):
    rig.speak()
    rig.printer.error = PrinterError("Printer not found: is it on?")
    rig.press("printbtn")
    assert rig.device.last["state"] == ERROR and "Printer not found" in rig.device.last["detail"] and rig.device.last["preview"]
    rig.run_timers()
    assert rig.device.last["state"] == READY and rig.maker.design is not None


def test_agent_failure_keeps_the_previous_design(rig):
    rig.speak()
    before = rig.maker.design
    rig.designer.fail = DesignError("Model API error 529: overloaded")
    rig.speak()
    assert rig.device.last["state"] == ERROR and "overloaded" in rig.device.last["detail"]
    assert rig.maker.design is before
    rig.run_timers()
    assert rig.device.last["state"] == READY


def test_speech_engine_failure_is_shown(rig):
    rig.stt.transcribe = lambda pcm: (_ for _ in ()).throw(RuntimeError("needs faster-whisper"))
    rig.speak()
    assert rig.device.last["state"] == ERROR and "faster-whisper" in rig.device.last["detail"]


def test_discard_throws_everything_away(rig):
    rig.speak()
    rig.press("discard")
    assert rig.maker.design is None and rig.maker.history == []
    assert rig.device.last["state"] == IDLE and rig.device.last["design"] is False
    rig.speak()
    assert rig.designer.calls[1][1] is None  # Starts from scratch.


def test_discard_with_nothing_to_discard_does_nothing(rig):
    n = len(rig.device.states)
    rig.press("discard")
    assert len(rig.device.states) == n


def test_a_design_finished_after_discard_is_dropped(rig):
    rig.designer.before_returning = lambda: rig.press("discard")
    rig.speak()
    assert rig.maker.design is None and rig.device.last["state"] == IDLE and rig.device.previews == 0


def test_buttons_are_ignored_while_the_agent_works_or_prints(rig):
    rig.designer.before_returning = lambda: (rig.maker.on_event("audio_start", 1), rig.press("printbtn"))
    rig.speak()
    assert rig.maker.state == READY and rig.printer.printed == [] and rig.stt.heard == [64000]


def test_corrupt_audio_chunks_are_skipped_not_fatal(rig):
    rig.maker.on_event("audio_start", 1)
    rig.maker.on_event("audio", "!!not base64!!")
    rig.maker.on_event("audio", base64.b64encode(b"\x01\x00" * 16000).decode())
    rig.maker.on_event("audio_end", {"samples": 16000, "dropped": 0})
    assert rig.stt.heard == [32000]


# --- the board wire format -------------------------------------------------------------


class RecordingBoard:
    def __init__(self) -> None:
        self.sent: list[tuple[str, object]] = []

    def call(self, key, value="", timeout=2.0) -> None:
        self.sent.append((key, value))

    def events(self, keys=None):
        return iter(())

    def close(self) -> None:
        pass


def test_state_is_sent_as_plain_ascii_the_firmware_can_read():
    raw = RecordingBoard()
    LabelBoard(board=raw).set_state("thinking", "Drawing", 'Blåbær "på" Grünerløkka\nny linje ' + "x" * 400, design=True, preview=False)
    key, value = raw.sent[0]
    line = wire(key, value)
    assert key == "ui_state" and line.isascii() and "\\u" not in line and len(line) < 4096
    payload = value
    assert payload["state"] == "thinking" and payload["design"] == 1 and payload["preview"] == 0
    assert len(payload["detail"]) <= 150 and payload["detail"].startswith("Blabaer 'pa' Grunerlokka ny linje")


def test_preview_is_one_line_with_size_up_front():
    raw = RecordingBoard()
    LabelBoard(board=raw).show_preview(render_design([HEADLINE]).image)
    key, value = raw.sent[0]
    head, _, body = value.partition(":")
    width, height = (int(n) for n in head.split(","))
    assert key == "ui_preview" and len(base64.b64decode(body)) == ((width + 3) // 4) * height
    assert len(wire(key, value)) < 4096


# --- the microphone test -------------------------------------------------------------


def test_mic_test_saves_both_takes_and_plays_the_raw_one(tmp_path):
    from prins.mictest import MicTest, describe

    played, said = [], []
    test = MicTest(tmp_path, played.append, say=said.append)
    tone = b"".join(int(8000 * __import__("math").sin(i / 5)).to_bytes(2, "little", signed=True) for i in range(16000))
    test.on_event("audio", base64.b64encode(tone).decode())  # Before audio_start: ignored.
    test.on_event("audio_start", 1)
    test.on_event("audio", base64.b64encode(tone).decode())
    test.on_event("audio_end", {"samples": 16000, "dropped": 0})
    assert [p.name.endswith("-raw.wav") for p in played] == [True]
    assert len(list(tmp_path.glob("*.wav"))) == 2
    assert "1.0 s" in describe(tone) and "good level" in describe(tone)


def test_mic_test_tells_you_when_the_microphone_hears_nothing():
    from prins.mictest import describe

    assert "nothing picked up" in describe(b"\x00\x00" * 16000)
