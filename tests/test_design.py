from __future__ import annotations

import base64
import json

import pytest
from PIL import Image

from prins.design.assets import AssetError
from prins.design.canvas import BITMAP_BYTES, HEIGHT, WIDTH, Canvas, DesignError, bitmap_to_image, catalog, image_to_bitmap
from prins.design.figures import FIGURES
from prins.design.formula import FormulaError, compile_formula
from prins.design.frames import FRAMES
from prins.design.patterns import PATTERNS
from prins.design.tools import TOOLS, Session, run_tool
from prins.render import render_note, to_escpos
from prins.store import Item


def black(canvas: Canvas) -> int:
    return canvas.image.convert("L").histogram()[0]


def drawn(*ops) -> Canvas:
    canvas = Canvas()
    canvas.apply_all(ops)
    return canvas


def test_the_grid_is_exactly_312_by_216():
    assert (WIDTH, HEIGHT) == (312, 216)
    assert BITMAP_BYTES == 8424
    assert Canvas().image.size == (312, 216)


def test_bitmap_round_trip_keeps_every_pixel():
    canvas = drawn({"op": "formula", "f": "(x*7+y*3)%5<2"})
    bitmap = canvas.bitmap()
    assert len(base64.b64decode(bitmap)) == 8424
    assert bitmap_to_image(bitmap).tobytes() == canvas.image.tobytes()


def test_bitmap_bits_mean_1_is_black():
    canvas = drawn({"op": "pixels", "rows": ["#"], "x": 0, "y": 0})
    packed = base64.b64decode(canvas.bitmap())
    assert packed[0] == 0x80
    assert sum(packed) == 0x80


@pytest.mark.parametrize("bad", ["", "not base64!!", base64.b64encode(b"short").decode()])
def test_bad_bitmaps_are_refused(bad):
    with pytest.raises(DesignError):
        bitmap_to_image(bad)


def test_wrong_size_images_are_refused():
    with pytest.raises(DesignError):
        image_to_bitmap(Image.new("1", (100, 100)))


@pytest.mark.parametrize("name", sorted(FIGURES))
def test_every_figure_draws_inside_its_box(name):
    canvas = drawn({"op": "figure", "name": name, "x": 100, "y": 50, "w": 80, "h": 80})
    assert black(canvas) > 30, name


@pytest.mark.parametrize("name", sorted(PATTERNS))
def test_every_pattern_draws(name):
    assert 0 < black(drawn({"op": "pattern", "name": f"{name}:5"})) < 312 * 216, name


@pytest.mark.parametrize("name", sorted(FRAMES))
def test_every_frame_draws(name):
    assert black(drawn({"op": "frame", "name": name, "inset": 4})) > 100, name


def test_a_figure_works_as_a_frame():
    assert black(drawn({"op": "frame", "name": "heart", "size": 4})) > 200


def test_gray_tone_has_about_the_right_darkness():
    assert abs(black(drawn({"op": "pattern", "name": "gray:25"})) / (312 * 216) - 0.25) < 0.02


@pytest.mark.parametrize("font", catalog("fonts")["fonts"])
def test_every_font_prints_text(font):
    assert black(drawn({"op": "text", "s": "Hello 123", "font": font})) > 100


def test_text_auto_size_fills_more_of_a_bigger_box():
    small = black(drawn({"op": "text", "s": "Hi", "w": 60, "h": 30}))
    big = black(drawn({"op": "text", "s": "Hi", "w": 300, "h": 200}))
    assert big > small * 4


def test_long_text_stays_in_its_box():
    canvas = drawn({"op": "text", "s": "word " * 400, "x": 50, "y": 50, "w": 100, "h": 60})
    assert canvas.image.convert("L").point(lambda v: 255 - v).getbbox()[1] >= 45
    box = Image.eval(canvas.image.convert("L"), lambda v: 255 - v).getbbox()
    assert box[0] >= 50 and box[2] <= 150 and box[1] >= 50 and box[3] <= 112


def test_ink_white_and_invert_and_pattern():
    base = {"op": "shape", "kind": "rect", "x": 0, "y": 0, "w": 100, "h": 100}
    assert black(drawn(base)) == 100 * 100
    assert black(drawn(base, {**base, "ink": "white"})) == 0
    assert black(drawn(base, {**base, "w": 50, "ink": "invert"})) == 50 * 100
    assert black(drawn({**base, "ink": "invert"})) == 100 * 100  # White turns black too.
    assert 0 < black(drawn({**base, "ink": "dots:4"})) < 100 * 100


def test_shapes_all_draw():
    for op in (
        {"kind": "rect", "w": 50, "h": 50}, {"kind": "rrect", "w": 50, "h": 50}, {"kind": "ellipse", "w": 50, "h": 50},
        {"kind": "line", "pts": [[0, 0], [100, 100]], "lw": 3}, {"kind": "curve", "pts": [0, 0, 50, 90, 100, 0]},
        {"kind": "polygon", "pts": [[0, 0], [90, 0], [0, 90]]}, {"kind": "arc", "w": 50, "h": 50, "a1": 180},
        {"kind": "pie", "w": 50, "h": 50, "a1": 90}, {"kind": "chord", "w": 50, "h": 50, "a1": 200},
    ):
        assert black(drawn({"op": "shape", **op})) > 10, op


def test_pixel_art_lands_exactly_where_asked():
    canvas = drawn({"op": "pixels", "rows": ["#.#", ".#."], "x": 10, "y": 20, "scale": 2})
    pixels = canvas.image.load()
    assert pixels[10, 20] == 0 and pixels[11, 21] == 0
    assert pixels[12, 20] != 0
    assert pixels[14, 20] == 0
    assert black(canvas) == 3 * 4


def test_full_raw_bitmap_gives_total_control():
    source = drawn({"op": "formula", "f": "x%3==0"})
    packed = bytes(b ^ 0xFF for b in source.image.tobytes())
    copy = drawn({"op": "pixels", "b64": base64.b64encode(packed).decode(), "w": 312})
    assert copy.image.tobytes() == source.image.tobytes()


def test_svg_path_draws_crisply():
    canvas = drawn({"op": "svg", "d": "M0 0H24V24H0Z", "x": 10, "y": 10, "w": 48, "h": 48})
    assert black(canvas) == 48 * 48


def test_full_svg_markup_and_inline_images(tmp_path):
    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><circle cx="5" cy="5" r="5"/></svg>'
    assert black(drawn({"op": "svg", "svg": svg, "w": 50, "h": 50})) > 1500

    path = tmp_path / "gray.png"
    Image.linear_gradient("L").resize((64, 64)).save(path)
    from_file = drawn({"op": "image", "src": str(path), "w": 64, "h": 64})
    assert 500 < black(from_file) < 3600
    inline = base64.b64encode(path.read_bytes()).decode()
    assert black(drawn({"op": "image", "src": inline, "w": 64, "h": 64})) == black(from_file)


@pytest.mark.parametrize("dither", ["atkinson", "floyd", "bayer", "halftone", "threshold"])
def test_every_dither_gives_a_black_and_white_picture(tmp_path, dither):
    path = tmp_path / "gray.png"
    Image.linear_gradient("L").resize((100, 100)).save(path)
    canvas = drawn({"op": "image", "src": str(path), "w": 100, "h": 100, "dither": dither})
    assert 0 < black(canvas) < 100 * 100
    top = canvas.image.crop((0, 0, 100, 20)).convert("L").histogram()[0]
    bottom = canvas.image.crop((0, 80, 100, 100)).convert("L").histogram()[0]
    assert bottom < top  # linear_gradient runs dark to light, so tone survives.


def test_qr_code_is_drawn_with_a_scale_of_whole_pixels():
    canvas = drawn({"op": "qr", "s": "https://example.com", "x": 10, "y": 10, "w": 150, "h": 150})
    assert black(canvas) > 2000
    with pytest.raises(DesignError):
        drawn({"op": "qr", "s": "x" * 300, "w": 20, "h": 20})


def test_transforms():
    base = drawn({"op": "shape", "kind": "rect", "x": 0, "y": 0, "w": 50, "h": 216})
    for op in ({"kind": "invert"}, {"kind": "flip-h"}, {"kind": "flip-v"}, {"kind": "rotate", "deg": 90}, {"kind": "mirror-h"}, {"kind": "mirror-v"}, {"kind": "shift", "dx": 10}, {"kind": "pixelate", "size": 8}, {"kind": "outline"}):
        base2 = drawn(*base.ops, {"op": "transform", **op})
        assert base2.image.size == (312, 216), op
    assert black(drawn(*base.ops, {"op": "transform", "kind": "invert"})) == 262 * 216
    assert black(drawn(*base.ops, {"op": "transform", "kind": "mirror-h"})) == 100 * 216


def test_repeat_and_scatter():
    square = {"op": "shape", "kind": "rect", "w": 10, "h": 10}
    assert black(drawn({"op": "repeat", "n": 5, "dx": 20, "ops": [square]})) == 5 * 100
    one = drawn({"op": "scatter", "n": 30, "seed": 3, "ops": [square]})
    two = drawn({"op": "scatter", "n": 30, "seed": 3, "ops": [square]})
    assert one.image.tobytes() == two.image.tobytes() and black(one) > 500


def test_undo_returns_the_previous_picture():
    canvas = drawn({"op": "figure", "name": "heart", "w": 80, "h": 80})
    before = canvas.image.tobytes()
    canvas.apply({"op": "pattern", "name": "checker"})
    canvas.undo()
    assert canvas.image.tobytes() == before


@pytest.mark.parametrize("bad", [
    {"op": "nope"}, {"s": "no op"}, {"op": "figure", "name": "nope"}, {"op": "pattern", "name": "nope"},
    {"op": "frame", "name": "nope"}, {"op": "text", "s": "x", "font": "no-such-font"}, {"op": "text", "s": "x", "ink": "nope"},
    {"op": "text", "s": "x", "w": 0}, {"op": "shape", "kind": "nope"}, {"op": "shape", "kind": "line", "pts": [[1, 1]]},
    {"op": "image", "src": "/no/such/file.png"}, {"op": "svg"}, {"op": "pixels"}, {"op": "svg", "d": 'M0"><script>'},
    {"op": "formula", "f": "__import__('os')"}, {"op": "transform", "kind": "nope"}, {"op": "text", "s": "x", "x": "abc"},
])
def test_bad_ops_give_a_clear_error_and_change_nothing(bad):
    canvas = drawn({"op": "figure", "name": "star", "w": 50, "h": 50})
    before = canvas.image.tobytes()
    with pytest.raises(DesignError):
        canvas.apply(bad)
    assert canvas.image.tobytes() == before
    assert len(canvas.ops) == 1


@pytest.mark.parametrize("attack", [
    "__import__('os').system('true')", "().__class__", "open('/etc/passwd')", "x.real", "[i for i in (1,)]",
    "(lambda: 1)()", "eval('1')", "getattr(x,'real')", "'text'", "x if y else __builtins__", "f'{x}'",
])
def test_formulas_cant_escape_the_whitelist(attack):
    with pytest.raises(FormulaError):
        compile_formula(attack)


def test_formula_math_errors_just_paint_nothing():
    assert compile_formula("1/(x-5)>0")(5, 0, 10, 10) is False
    assert compile_formula("x>y")(5, 1, 10, 10) is True


def test_untrusted_designs_cant_read_files_or_the_network(tmp_path):
    path = tmp_path / "secret.png"
    Image.new("L", (8, 8)).save(path)
    canvas = Canvas(external=False)
    for op in ({"op": "image", "src": str(path)}, {"op": "image", "src": "https://example.com/x.png"},
               {"op": "svg", "src": "https://example.com/x.svg"}, {"op": "text", "s": "x", "font": str(path)}):
        with pytest.raises(DesignError):
            canvas.apply(op)


def test_a_private_svg_cant_pull_in_a_local_file(tmp_path):
    secret = tmp_path / "secret.png"
    Image.new("L", (40, 40), 0).save(secret)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 40 40"><image width="40" height="40" xlink:href="{secret}"/></svg>'
    canvas = Canvas(external=False)
    for attack in (svg, svg.replace("xlink:href", "href"), '<svg xmlns="http://www.w3.org/2000/svg"><style>@import "x";</style></svg>'):
        with pytest.raises(DesignError):
            canvas.apply({"op": "svg", "svg": attack, "w": 40, "h": 40})
    assert black(canvas) == 0
    # Links inside the SVG itself are fine.
    canvas.apply({"op": "svg", "svg": '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 10 10"><defs><circle id="c" cx="5" cy="5" r="5"/></defs><use xlink:href="#c"/></svg>', "w": 40, "h": 40})
    assert black(canvas) > 500


def test_plain_notes_are_exactly_note_sized_however_long_they_are():
    for title, detail, priority in (("Hi", "", "normal"), ("word " * 80, "more " * 80, "high"), ("Blåbær 日本語", "é", "low")):
        item = Item(id=1, source="slack", sender="Maria" * 30, raw_text="", title=title, detail=detail, priority=priority, due="", status="queued", engine="m", created_at=1.7e9)
        assert render_note(item).size == (312, 216)


def test_a_custom_design_prints_exactly_as_drawn():
    canvas = drawn({"op": "formula", "f": "x%2==y%2"})
    item = Item(id=1, source="agent", sender="", raw_text="", title="t", detail="", priority="normal", due="", status="queued", engine="d", created_at=1.7e9, bitmap=canvas.bitmap())
    assert render_note(item).tobytes() == canvas.image.tobytes()


def test_the_note_is_centered_on_wider_paper():
    image = Image.new("1", (312, 216), 0)  # All black.
    data = to_escpos(image, feed_lines=0, paper_dots=384)
    assert data[6:8] == bytes((48, 0))  # 48 bytes per row, for 384 dots.
    first_row = data[10:58]
    # (384 - 312) / 2 = 36 white dots on each side, so byte 4 is half white, half black.
    assert first_row[0] == 0 and first_row[4] == 0x0F and first_row[5] == 0xFF
    assert first_row[-1] == 0


# --- the tools ------------------------------------------------------------------------


def test_every_tool_has_a_schema_and_short_definitions():
    for tool in TOOLS:
        assert tool.schema["type"] == "object", tool.name
        assert len(tool.description) < 350, tool.name
    defs = json.dumps([{"name": t.name, "description": t.description, "input_schema": t.schema} for t in TOOLS])
    assert len(defs) < 9000, f"{len(defs)} characters of tool definitions"


def test_batch_and_single_tools_draw_the_same():
    one = Session()
    run_tool(one, "draw_figure", {"name": "heart", "w": 80, "h": 80})
    run_tool(one, "draw_text", {"s": "Hi", "x": 90, "w": 100, "h": 50})
    many = Session()
    run_tool(many, "draw_batch", {"ops": [{"op": "figure", "name": "heart", "w": 80, "h": 80}, {"op": "text", "s": "Hi", "x": 90, "w": 100, "h": 50}]})
    assert one.canvas.image.tobytes() == many.canvas.image.tobytes()


def test_preview_returns_a_small_png():
    session = Session()
    run_tool(session, "draw_figure", {"name": "star"})
    result = run_tool(session, "preview", {})
    assert result.png.startswith(b"\x89PNG") and len(result.png) < 8000


def test_catalog_lists_names_compactly():
    text = run_tool(Session(), "catalog", {"kind": "figures"}).text
    assert "heart" in text and len(text) < 800


def test_saved_designs_reuse_for_free(tmp_path):
    session = Session(designs_dir=tmp_path)
    run_tool(session, "draw_figure", {"name": "star"})
    run_tool(session, "save_design", {"name": "my star"})
    picture = session.canvas.image.tobytes()
    run_tool(session, "clear", {})
    run_tool(session, "load_design", {"name": "my star"})
    assert session.canvas.image.tobytes() == picture
    with pytest.raises(DesignError):
        run_tool(session, "load_design", {"name": "../../etc/passwd"})
    with pytest.raises(DesignError):
        run_tool(session, "load_design", {"name": "missing"})


class FakeOutput:
    def __init__(self) -> None:
        self.printed: list = []
        self.sent: list = []

    def print_note(self, title, bitmap):
        self.printed.append((title, bitmap))
        return "queued"

    def list_friends(self):
        return [{"id": "1", "name": "Sam", "canSend": True}]

    def send_to_friend(self, friend, title, bitmap):
        self.sent.append((friend, title, bitmap))
        return "sent"


def test_print_sends_the_canvas_and_starts_fresh():
    output = FakeOutput()
    session = Session(output=output)
    run_tool(session, "draw_figure", {"name": "star"})
    bitmap = session.canvas.bitmap()
    assert run_tool(session, "print_note", {"title": "Star"}).text == "queued"
    assert output.printed == [("Star", bitmap)]
    assert session.canvas.blank


def test_a_plain_text_note_needs_no_drawing():
    output = FakeOutput()
    run_tool(Session(output=output), "print_note", {"text": "Buy milk"})
    title, bitmap = output.printed[0]
    assert title == "Buy milk" and bitmap_to_image(bitmap).convert("L").histogram()[0] > 100


def test_printing_nothing_is_refused():
    with pytest.raises(DesignError):
        run_tool(Session(output=FakeOutput()), "print_note", {})


def test_send_to_friend_needs_a_friend():
    output = FakeOutput()
    session = Session(output=output)
    with pytest.raises(DesignError):
        run_tool(session, "send_to_friend", {"text": "hi"})
    run_tool(session, "send_to_friend", {"friend": "Sam", "text": "hi"})
    assert output.sent[0][0] == "Sam"


def test_the_internal_designer_gets_no_printing_files_or_friends():
    internal = {tool.name for tool in TOOLS if tool.internal}
    assert not internal & {"print_note", "send_to_friend", "list_friends", "draw_image", "save_design", "load_design", "preview"}
    assert {"draw_batch", "draw_logo", "draw_svg", "catalog"} <= internal
