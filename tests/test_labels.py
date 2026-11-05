"""The label maker: the drawing agent, the state machine and the wire format."""

from __future__ import annotations

import base64
import json
import socket
from types import SimpleNamespace

import pytest
from atech.runtime.models import Action
from atech.runtime.transport import encode_action
from PIL import Image

from prins.design import Canvas, DesignError, assets
from prins.drawing import check_design, thumbnail_2bpp
from prins.labelboard import LabelBoard
from prins.labeldesigner import Design, LabelDesigner, LabelDesignError
from prins.labelprinter import PrinterError
from prins.labels import ERROR, IDLE, LISTENING, PRINTING, READY, THINKING, LabelMaker

HEADLINE = {"op": "text", "s": "Dentist", "x": 8, "y": 20, "w": 296, "h": 60, "align": "c"}
TINY = {"op": "text", "s": "tiny print " * 6, "x": 4, "y": 4, "w": 304, "h": 60, "size": 10}
BOX = {"op": "shape", "kind": "rrect", "x": 4, "y": 4, "w": 304, "h": 208, "r": 12, "fill": False, "lw": 4}


def wire(key: str, value) -> str:
    return encode_action(Action(key=key, value=value)).decode()


def make_design(ops=None, title="Dentist", summary="Drew it") -> Design:
    return Design.from_ops(ops if ops is not None else [HEADLINE], title, summary)


# --- checks and thumbnail ---------------------------------------------------------------


def test_a_normal_design_passes_the_checks():
    canvas = Canvas(external=False)
    canvas.apply_all([HEADLINE, BOX])
    assert check_design(canvas) == []


def test_blank_solid_black_and_tiny_text_are_flagged():
    blank = Canvas(external=False)
    assert any("blank" in w for w in check_design(blank))
    black = Canvas(external=False)
    black.apply({"op": "shape", "kind": "rect", "fill": True})
    assert any("black" in w for w in check_design(black))
    tiny = Canvas(external=False)
    tiny.apply(TINY)
    assert any("at least" in w for w in check_design(tiny))


def test_thumbnail_fits_the_screen_and_one_serial_line():
    width, height, data = thumbnail_2bpp(make_design().image)
    assert width <= 120 and height <= 80
    assert len(data) == ((width + 3) // 4) * height <= 2400
    line = wire("ui_preview", f"{width},{height}:{base64.b64encode(data).decode()}")
    assert len(line) < 4096 and line.isascii()


def test_thumbnail_keeps_black_black_and_white_white():
    black = thumbnail_2bpp(Image.new("1", (312, 216), 0))[2]
    white = thumbnail_2bpp(Image.new("1", (312, 216), 1))[2]
    assert set(black) == {0x00} and set(white) == {0xFF}


# --- the web guard --------------------------------------------------------------------


@pytest.mark.parametrize("url", [
    "http://127.0.0.1:8110/canvas",
    "http://localhost/x",
    "http://10.0.0.5/x",
    "http://192.168.1.1/x",
    "http://169.254.169.254/latest/meta-data",
    "http://[::1]/x",
    "http://example.com:8080/x",
    "http://user:pw@example.com/x",
    "ftp://example.com/x",
    "file:///etc/hosts",
])
def test_the_web_guard_refuses_anything_that_is_not_a_public_web_address(url, monkeypatch):
    with pytest.raises(assets.AssetError):
        assets.check_public_url(url)


def test_a_public_address_passes_and_a_name_that_resolves_inside_does_not(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assets.check_public_url("https://example.com/logo.svg")
    monkeypatch.setattr(socket, "getaddrinfo", lambda host, port, **kw: [(2, 1, 6, "", ("192.168.0.9", 443))])
    with pytest.raises(assets.AssetError):
        assets.check_public_url("https://innocent.example.com/logo.svg")


def test_a_redirect_to_the_local_network_is_refused(monkeypatch):
    handler = assets._GuardedRedirects()
    with pytest.raises(assets.AssetError):
        handler.redirect_request(SimpleNamespace(), None, 302, "Found", {}, "http://127.0.0.1:8737/v1/messages")


def test_web_mode_loads_no_files_and_the_plain_untrusted_mode_loads_no_network():
    web = Canvas(external=False, web=True)
    with pytest.raises(DesignError):
        web.apply({"op": "image", "src": "/etc/hosts"})
    with pytest.raises(DesignError):
        web.apply({"op": "image", "src": "http://127.0.0.1:8110/canvas"})
    plain = Canvas(external=False)
    with pytest.raises(DesignError):
        plain.apply({"op": "image", "src": "https://example.com/a.png"})


# --- the drawing agent ---------------------------------------------------------------


def call(name: str, **args) -> SimpleNamespace:
    call.n = getattr(call, "n", 0) + 1
    return SimpleNamespace(type="tool_use", id=f"toolu_{call.n}", name=name, input=args)


def reply(*blocks, stop="tool_use") -> SimpleNamespace:
    return SimpleNamespace(stop_reason=stop, content=list(blocks))


def finish(title="Dentist", summary="Drew it") -> SimpleNamespace:
    return call("finish", title=title, summary=summary)


class FakeClient:
    """Stands in for anthropic.Anthropic: answers each messages.create call from a script."""

    def __init__(self, *answers) -> None:
        self.answers = list(answers)
        self.calls: list[dict] = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kwargs):
        self.calls.append({**kwargs, "messages": list(kwargs["messages"])})
        return self.answers.pop(0)

    def tool_names(self, n: int = 0) -> set[str]:
        return {t["name"] for t in self.calls[n]["tools"]}


def draw(*ops) -> SimpleNamespace:
    return call("draw_batch", ops=list(ops))


def test_the_agent_draws_then_finishes():
    client = FakeClient(reply(draw(HEADLINE)), reply(finish()))
    design = LabelDesigner(client).design("a label that says dentist")
    assert len(client.calls) == 2 and design.title == "Dentist" and design.summary == "Drew it" and design.warnings == []
    assert design.ops == [HEADLINE] and design.image.mode == "1"
    first = client.calls[0]["messages"][0]["content"][-1]["text"]
    assert "<spoken_instruction>" in first and "a label that says dentist" in first


def test_the_agent_can_search_and_fetch_the_web_but_not_print_or_read_files():
    client = FakeClient(reply(draw(HEADLINE)), reply(finish()))
    LabelDesigner(client).design("dentist")
    names = client.tool_names()
    assert {"web_search", "web_fetch", "draw_batch", "draw_logo", "draw_image", "preview", "finish"} <= names
    assert not names & {"print_note", "send_to_friend", "list_friends", "save_design", "load_design"}
    searches = {t["name"]: t for t in client.calls[0]["tools"]}
    assert searches["web_search"]["max_uses"] == 3 and searches["web_fetch"]["max_uses"] == 3
    assert searches["web_fetch"]["url_sources"] == {"client_tool_results": {"type": "none"}}


def test_web_can_be_turned_off():
    client = FakeClient(reply(draw(HEADLINE)), reply(finish()))
    LabelDesigner(client, web=False).design("dentist")
    assert not client.tool_names() & {"web_search", "web_fetch"}


def test_finish_is_sent_back_with_problems_and_the_fix_is_taken():
    tiny = TINY
    client = FakeClient(reply(draw(tiny), finish()), reply(call("clear"), draw(HEADLINE)), reply(finish()))
    design = LabelDesigner(client).design("dentist")
    assert len(client.calls) == 3 and design.warnings == [] and design.ops == [HEADLINE]
    feedback = client.calls[1]["messages"][-1]["content"]
    assert any("at least" in str(block["content"]) and block.get("is_error") for block in feedback)


def test_the_agent_gets_two_fixes_then_what_it_drew_is_accepted_with_the_problems_noted():
    tiny = TINY
    client = FakeClient(reply(draw(tiny), finish()), reply(finish()), reply(finish()))
    design = LabelDesigner(client).design("dentist")
    assert len(client.calls) == 3 and design.warnings


def test_a_paused_search_turn_is_resumed_without_adding_a_user_message():
    paused = reply(SimpleNamespace(type="server_tool_use", id="srv_1", name="web_search", input={"query": "x"}), stop="pause_turn")
    client = FakeClient(paused, reply(draw(HEADLINE)), reply(finish()))
    LabelDesigner(client).design("the Oslo marathon")
    resumed = client.calls[1]["messages"]
    assert resumed[-1]["role"] == "assistant" and resumed[-1]["content"] == paused.content


def test_assistant_turns_are_sent_back_exactly_as_received():
    first = reply(SimpleNamespace(type="text", text="Looking that up"), draw(HEADLINE))
    client = FakeClient(first, reply(finish()))
    LabelDesigner(client).design("dentist")
    assert client.calls[1]["messages"][1] == {"role": "assistant", "content": first.content}


def test_revising_puts_the_current_design_back_and_shows_the_agent_picture_and_shapes():
    current = make_design([HEADLINE])
    box = BOX
    client = FakeClient(reply(draw(box)), reply(finish("Dentist", "Added a frame")))
    design = LabelDesigner(client).design("add a frame", current, history=["a dentist label"])
    content = client.calls[0]["messages"][0]["content"]
    assert content[0]["type"] == "image"
    assert "a dentist label" in content[-1]["text"] and '"op":"text"' in content[-1]["text"]
    assert design.ops == [HEADLINE, box]


def test_a_design_that_cannot_be_replayed_is_kept_as_its_picture():
    base = make_design([HEADLINE])
    broken = Design([{"op": "image", "src": "http://127.0.0.1/gone.png"}], "x", "", base.image, [])
    client = FakeClient(reply(finish()))
    design = LabelDesigner(client).design("keep it", broken)
    assert design.image.tobytes() == base.image.tobytes()


def test_a_tool_the_agent_may_not_use_or_a_bad_call_comes_back_as_an_error_not_a_crash():
    client = FakeClient(reply(call("print_note", title="x"), call("draw_logo"), draw(HEADLINE)), reply(finish()))
    design = LabelDesigner(client).design("dentist")
    results = client.calls[1]["messages"][-1]["content"]
    assert [r.get("is_error") for r in results] == [True, True, None]
    assert design.ops == [HEADLINE]


def test_no_key_a_refusal_and_an_empty_label_are_errors():
    with pytest.raises(LabelDesignError):
        LabelDesigner(None).design("anything")
    with pytest.raises(LabelDesignError):
        LabelDesigner(FakeClient(reply(stop="refusal"))).design("anything")
    with pytest.raises(LabelDesignError):
        LabelDesigner(FakeClient(reply(finish()), reply(finish()), reply(finish()))).design("nothing drawn")


def test_if_the_agent_forgets_to_finish_what_it_drew_is_still_used():
    client = FakeClient(reply(draw(HEADLINE)), reply(SimpleNamespace(type="text", text="done"), stop="end_turn"))
    design = LabelDesigner(client).design("dentist")
    assert design.title == "Label" and design.ops == [HEADLINE]


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
    LabelBoard(board=raw).show_preview(make_design().image)
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
