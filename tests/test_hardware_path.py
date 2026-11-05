"""The device and printer code against the SDK's real Board class, with a mock wire."""

from __future__ import annotations

import base64
import json

import pytest
from atech import ActionRejected, Board
from atech.runtime.transport import MockTransport, encode_action
from PIL import Image

from prins.device import AtechDevice, CardView, StatusView, screen_text
from prins.printers import CHUNK_BYTES, AtechPrinter, PrintError
from prins.render import render_note, to_escpos
from prins.store import Item


def _item(**over) -> Item:
    fields = dict(id=1, source="slack", sender="Maria", raw_text="", title="Send the Q3 numbers",
                  detail="One slide.", priority="normal", due="", status="queued", engine="model",
                  created_at=1_700_000_000.0)
    return Item(**{**fields, **over})


# --- screen text --------------------------------------------------------------------


def test_screen_text_is_ascii_and_keeps_norwegian_readable():
    assert screen_text("Blåbærsyltetøy på Grünerløkka") == "Blabaersyltetoy pa Grunerlokka"


def test_screen_text_removes_what_would_break_the_firmware_json_reader():
    out = screen_text('He said "hi" \\ bye 🎉\nnext')
    assert '"' not in out and "\\" not in out and "\n" not in out
    assert out.isascii()


def test_card_payload_survives_the_wire_format_the_firmware_parses():
    view = CardView("email", "Bjørn", 'Reply to "Ærlig" 🎉', "Détail", 7)
    wire = encode_action_line("ui_card", view.payload())
    assert len(wire) < 4096
    assert wire.isascii()
    assert "\\u" not in wire  # The firmware's reader cannot decode these.


def encode_action_line(key: str, value) -> str:
    from atech.runtime.models import Action

    return encode_action(Action(key=key, value=value)).decode()


def test_longest_card_fits_the_firmware_line_limit():
    view = CardView("email", "x" * 200, "y" * 500, "z" * 500, 99999)
    assert len(encode_action_line("ui_card", view.payload())) < 4096


# --- printing bytes -----------------------------------------------------------------


def test_note_renders_at_the_printer_width_in_one_bit():
    image = render_note(_item())
    assert image.width == 384
    assert image.mode == "1"


def test_note_handles_long_words_and_any_language():
    image = render_note(_item(title="Blåbærsyltetøy" * 10, detail="日本語 Ωmega", due="fredag"))
    assert image.width == 384 and image.height > 100


def test_escpos_black_pixels_are_one_bits():
    image = Image.new("1", (16, 1), 1)  # White
    image.putpixel((0, 0), 0)  # One black dot
    data = to_escpos(image, feed_lines=0)
    assert data.startswith(b"\x1b@\x1dv0\x00\x02\x00\x01\x00")
    assert data[10:12] == b"\x80\x00"


def test_escpos_splits_tall_images_into_blocks():
    image = Image.new("1", (384, 450), 1)
    data = to_escpos(image)
    assert data.count(b"\x1dv0\x00") == 3
    assert len(data) == 2 + 3 * 8 + 48 * 450 + 3


# --- the board ----------------------------------------------------------------------


class ScriptedBoard:
    """Records calls, and answers like the firmware."""

    def __init__(self, busy_first: int = 0, pending: list[int] | None = None) -> None:
        self.calls: list[tuple[str, object]] = []
        self.busy_left = busy_first
        self.pending = pending or [0]

    def call(self, key, value="", **_):
        self.calls.append((key, value))
        if key == "printer_write" and self.busy_left:
            self.busy_left -= 1
            raise ActionRejected("the board could not carry out 'printer_write': busy.")

    def query(self, key, value="", *, reply, **_):
        self.calls.append((key, value))
        return self.pending.pop(0) if len(self.pending) > 1 else self.pending[0]


def test_real_board_class_accepts_our_action_and_waits_for_the_ack():
    transport = MockTransport()
    device = AtechDevice(board=Board(transport))
    transport.push_wire(json.dumps({"type": "ack", "payload": {"action": "ui_status", "ok": True}}))
    device.show(StatusView("printing", "Printing..."))
    assert device._last_ok is True


def test_a_silent_board_does_not_crash_the_queue():
    device = AtechDevice(board=Board(MockTransport()))
    device.call = lambda *a, **k: (_ for _ in ()).throw(__import__("atech").NoAcknowledgement("silent"))
    device.show(StatusView("printing", "Printing..."))
    assert device._last_ok is False


def test_printer_chunks_reassemble_to_the_exact_bytes():
    board = ScriptedBoard()
    image = Image.new("1", (384, 400), 0)
    AtechPrinter(board.call, board.query, 9600, 900, sleep=lambda _: None).print_image(image, "x")
    chunks = [base64.b64decode(v) for k, v in board.calls if k == "printer_write"]
    assert all(len(c) <= CHUNK_BYTES for c in chunks)
    assert b"".join(chunks) == to_escpos(image)
    assert board.calls[0][0] == "printer_config"


def test_printer_chunks_fit_the_firmware_line_limit():
    from atech.runtime.models import Action

    encoded = base64.b64encode(b"\xff" * CHUNK_BYTES).decode()
    assert len(encode_action(Action(key="printer_write", value=encoded))) < 4096


def test_printer_retries_when_the_board_says_busy():
    board = ScriptedBoard(busy_first=3)
    printer = AtechPrinter(board.call, board.query, 9600, 900, sleep=lambda _: None)
    printer.print_image(Image.new("1", (384, 10), 1), "x")
    writes = [k for k, _ in board.calls if k == "printer_write"]
    assert len(writes) == 4


def test_printer_waits_until_the_queue_is_empty():
    board = ScriptedBoard(pending=[500, 100, 0])
    AtechPrinter(board.call, board.query, 9600, 900, sleep=lambda _: None).print_image(
        Image.new("1", (384, 10), 1), "x"
    )
    assert [k for k, _ in board.calls].count("printer_status") == 3


def test_printer_turns_a_rejected_action_into_a_print_error():
    def refuse(key, value="", **_):
        raise ActionRejected("unknown action")

    printer = AtechPrinter(refuse, lambda *a, **k: 0, 9600, 900, sleep=lambda _: None)
    with pytest.raises(PrintError):
        printer.print_image(Image.new("1", (384, 10), 1), "x")
