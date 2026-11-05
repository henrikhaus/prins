"""Posters: whatever a small model sends, the note comes out legible, complete and on the grid."""

from __future__ import annotations

import json

import pytest

from prins.design import craft
from prins.design.canvas import Canvas, DesignError, bitmap_to_image, catalog
from prins.design.poster import LOOKS, MIN_CAP, parse, rank, render
from prins.design.tools import TOOLS, BY_NAME, Session, run_tool

FULL = {"say": "Deploy blocked", "sub": "Approve the migration", "big": "14:00", "pic": "🐉", "data": [1, 5, 2, 8, 3], "items": ["ROOM: 4", "WITH: Ida"], "qr": "https://example.com/x"}

AWKWARD = [
    {"say": "x"},
    {"say": "A" * 120},
    {"say": "word " * 200},
    {"say": "Husk å ringe mormor på søndag", "sub": "Øl og blåbær, ß"},
    {"say": "締め切りは金曜日", "sub": "レポート"},
    {"say": "مرحبا بالعالم"},
    {"say": "🎉🎉🎉"},
    {"say": "line\nbreak\ttab"},
    {"say": ["TWO", "LINES"], "sub": "a list of lines"},
    {"say": 12345, "items": "nope", "data": ["x", None, float("nan")], "seed": "z", "big": 7},
    {"say": "Pic that doesn't exist", "pic": "qwertyuiop"},
    {"items": [f"Thing {n}" for n in range(12)]},
    {"data": [5]},
    {"data": [3, 3, 3, 3]},
    {"say": "Long detail", "sub": "word " * 60},
    {"say": "Many", "items": ["a very long item that goes on and on past any line width at all"] * 6},
]


def black(image) -> float:
    return image.convert("L").histogram()[0] / (312 * 216)


# --- the promises every look makes ------------------------------------------------------


@pytest.mark.parametrize("look", LOOKS)
def test_every_look_with_everything_is_on_the_grid_and_safe_to_print(look):
    """Given what it can show, each look draws. Anything extra may send it to another, safely."""
    shown = {key: value for key, value in FULL.items() if key in LOOKS[look].shows or key == "data" and look in ("rain", "ridges")}
    image, report = render({"look": look, **shown})
    assert image.size == (312, 216) and image.mode == "1"
    assert report.look == look, report.summary()
    assert black(image) <= 0.60, f"{black(image):.0%} black trips the label maker's check"
    assert report.min_cap >= MIN_CAP
    assert bitmap_to_image(_bitmap(image)).tobytes() == image.tobytes()


def _bitmap(image) -> str:
    canvas = Canvas()
    canvas.image = image
    return canvas.bitmap()


@pytest.mark.parametrize("look", LOOKS)
@pytest.mark.parametrize("case", AWKWARD, ids=range(len(AWKWARD)))
def test_no_content_can_break_a_look(look, case):
    image, report = render({"look": look, **case})
    assert image.size == (312, 216) and image.mode == "1"
    assert report.look in LOOKS
    assert black(image) <= 0.60
    assert black(image) > 0.002, "a note must never come out blank"


@pytest.mark.parametrize("look", LOOKS)
def test_no_words_are_lost_in_any_look(look):
    """A look that can't show a field moves it somewhere it can. Text that fits is never dropped."""
    fields = {"say": "Launch review", "sub": "Bring the slides", "big": "14:00", "items": ["ROOM: 4", "WITH: Ida"]}
    _, report = render({"look": look, **fields})
    shown = " ".join(report.shown).upper()
    assert not report.warnings or report.look != look or "cut off" not in " ".join(report.warnings)
    for word in ("LAUNCH", "REVIEW", "SLIDES", "14", "IDA"):
        assert word in shown, f"{word} missing from {report.look}: {shown}"


@pytest.mark.parametrize("empty", [{}, {"say": ""}, {"say": "   ", "items": [], "data": []}])
def test_nothing_to_say_is_an_error_the_model_can_fix_never_invented_words(empty):
    with pytest.raises(DesignError, match="something to say"):
        run_tool(Session(), "draw_poster", empty)


def test_an_emoji_in_the_words_becomes_the_picture():
    spec_image, report = render({"look": "picture", "say": "Dragon show 🐉"})
    if craft.assets.emoji_rgba("🐉") is not None:
        assert report.look == "picture"
    assert not any("🐉" in text for text in report.shown)


def test_a_qr_code_outside_a_ticket_is_flagged_not_printed_as_a_url():
    _, report = render({"look": "block", "say": "Join", "qr": "https://example.com"})
    assert "QR" in report.summary() and not any("example.com" in text for text in report.shown)


def test_a_number_a_look_cant_feature_isnt_printed_twice():
    _, report = render({"look": "alarm", "say": "CI failing", "sub": "since 3pm", "big": "3pm"})
    assert " ".join(report.shown).upper().count("3PM") == 1
    _, report = render({"look": "block", "say": "10,000 users", "big": "10,000"})
    assert " ".join(report.shown).count("10,000") == 1


def test_a_long_value_is_never_cut_short():
    _, report = render({"look": "alarm", "say": "Tax return", "big": "April 30"})
    assert "APRIL 30" in " ".join(report.shown).upper()


def test_a_win_features_its_number():
    _, report = render({"look": "monument", "say": "Sales up", "big": "24%"})
    assert report.look == "monument" and "24%" in " ".join(report.shown)


def test_a_ticket_holds_a_date_a_place_and_its_fields():
    _, report = render({"look": "ticket", "say": "Concert", "sub": "Rockefeller", "big": "14 March", "items": ["Doors: 19:30", "Row: 4", "Seat: 12"]})
    assert report.look == "ticket", report.summary()


def test_a_subject_on_a_plain_statement_asks_for_a_picture():
    if craft.assets.emoji_rgba("🦈") is None:
        pytest.skip("this machine has no emoji font")
    assert render({"look": "block", "say": "Bite me", "pic": "🦈"})[1].look == "picture"


def test_the_longer_field_is_the_quote_whichever_way_round():
    _, report = render({"look": "quote", "say": "Seneca", "sub": "We suffer more in imagination than in reality"})
    assert report.look == "quote" and "SENECA" in " ".join(report.shown).upper()


def test_tonight_isnt_about_the_night_sky():
    assert rank(parse({"say": "Feed the starter", "sub": "Tonight", "pic": "🍞"}))[0] == "picture"


def test_a_short_word_isnt_stretched_out_of_shape():
    mask = craft.stack(["OSLO"], "impact", 296, 100)[0]
    natural = craft.aspect("OSLO", "impact")
    assert mask.width / mask.height == pytest.approx(natural / 0.88, rel=0.05)


def test_text_too_long_for_any_note_says_so():
    _, report = render({"say": "word " * 200})
    assert report.look == "quote" and "cut off" in report.summary()


def test_a_look_that_cant_fit_hands_over_and_says_why():
    _, report = render({"look": "relief", "say": "This is far too many words for relief to hold at any size"})
    assert report.look != "relief" and "fewer words" in report.summary().lower()


def test_an_unknown_look_still_makes_a_note():
    image, report = render({"look": "wat", "say": "Hello"})
    assert report.look in LOOKS and "wat" in report.summary() and black(image) > 0


def test_the_same_fields_draw_the_same_pixels_and_a_seed_varies_them():
    fields = {"look": "cover", "say": "Monday", "date": "1 JAN"}
    assert render(fields)[0].tobytes() == render(fields)[0].tobytes()
    assert render(fields)[0].tobytes() != render({**fields, "seed": 2})[0].tobytes()


def test_a_model_cant_say_who_a_note_is_from():
    forged = {"look": "post", "say": "Hi", "date": "1 JAN", "sender": "Your boss", "from": "Your boss"}
    plain = render({"look": "post", "say": "Hi", "date": "1 JAN"})[0]
    assert render(forged)[0].tobytes() == plain.tobytes()
    assert "sender" not in parse(forged).__dict__ or parse(forged).sender == ""
    signed = Canvas(sender="Sam")
    signed.apply({"op": "poster", **forged})
    assert "SAM" in signed.report.shown and "YOUR BOSS" not in signed.report.shown


def test_an_untrusted_design_cant_reach_files_through_a_poster(tmp_path):
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"not an image")
    assert craft.resolve_picture(str(secret)) is None
    canvas = Canvas(external=False)
    canvas.apply({"op": "poster", "look": "picture", "say": "x", "pic": str(secret)})
    assert canvas.report.look != "picture"


# --- pictures of anything ---------------------------------------------------------------


def test_any_language_avoids_missing_glyph_boxes():
    assert craft._face_for("impact", "締切", 40).getname() != craft._open_face("impact", 40).getname()
    assert craft._face_for("impact", "ÆØÅ", 40).getname() == craft._open_face("impact", 40).getname()


@pytest.mark.parametrize("subject", ["🐉", "dragon", "pizza", "tooth", "cat"])
def test_a_subject_can_be_an_emoji_or_a_plain_word(subject):
    if craft.assets.emoji_rgba("🐉") is None:
        pytest.skip("this machine has no emoji font")
    gray, mask = craft.resolve_picture(subject, 80)
    assert gray.size == mask.size and mask.getbbox()


def test_nonsense_finds_no_picture():
    assert craft.resolve_picture("qwertyuiop") is None
    assert craft.resolve_picture("") is None


# --- type -------------------------------------------------------------------------------


def test_lines_break_where_they_fill_the_box():
    assert craft.break_lines("DEPLOY BLOCKED", "impact", 296, 150) == ["DEPLOY", "BLOCKED"]
    assert " ".join(craft.break_lines("one two three four five six", "impact", 296, 150)) == "one two three four five six"


def test_a_word_is_exactly_the_size_asked_for():
    assert craft.word("Hi", "impact", w=120, h=40).size == (120, 40)


# --- choosing ---------------------------------------------------------------------------


@pytest.mark.parametrize("fields,expected", [
    ({"say": "Server down!"}, "alarm"),
    ({"say": "We shipped it"}, "monument"),
    ({"say": "Happy birthday Nora"}, "post"),
    ({"say": "Focus"}, "relief"),
    ({"say": "Dentist 09:30"}, "collide"),
    ({"say": "3 days left"}, "numeral"),
    ({"say": "Goodnight"}, "engraving"),
    ({"say": "Vet visit", "pic": "🐈"}, "picture"),
    ({"say": "Groceries", "items": ["Milk", "Eggs"]}, "list"),
    ({"say": "Train", "items": ["FROM: Oslo", "TO: Bergen"]}, "ticket"),
    ({"say": "Link", "qr": "https://x.no"}, "ticket"),
    ({"big": "147", "say": "commits", "data": [1, 2, 3]}, "ridges"),
    ({"say": "Rain later", "data": [0, 0, 1]}, "rain"),
    ({"say": "Merged"}, "transit"),
    ({"say": "Call Sam back"}, "ransom"),
    ({"say": "Demo tomorrow"}, "stage"),
    ({"say": "Thursday"}, "cover"),
    ({"say": "The best time to plant a tree was twenty years ago, the second best is now"}, "quote"),
    ({"say": "Something plain"}, "block"),
])
def test_without_a_look_the_engine_chooses_well(fields, expected):
    assert rank(parse(fields))[0] == expected
    assert render(fields)[1].look == expected


def test_looks_that_lack_what_they_need_never_come_first():
    assert rank(parse({"say": "Hello there"}))[0] not in ("picture", "list", "numeral", "collide")


# --- the tools --------------------------------------------------------------------------


def test_draw_poster_says_what_it_did_and_what_else_fits():
    session = Session()
    result = run_tool(session, "draw_poster", {"say": "Server down!"})
    assert "alarm" in result.text and "Also fits" in result.text
    assert session.canvas.ops[0]["op"] == "poster" and session.canvas.bitmap()


def test_a_poster_is_an_op_so_it_batches_undoes_and_replays():
    session = Session()
    run_tool(session, "draw_batch", {"ops": [{"op": "poster", "say": "Hi", "date": "1 JAN"}, {"op": "figure", "name": "star", "x": 0, "y": 0, "w": 20, "h": 20}]})
    drawn = session.canvas.image.tobytes()
    replay = Canvas()
    replay.apply_all(session.canvas.ops)
    assert replay.image.tobytes() == drawn
    session.canvas.undo()
    assert session.canvas.image.tobytes() != drawn


def test_compare_shows_looks_without_touching_the_note():
    session = Session()
    result = run_tool(session, "compare_looks", {"say": "Dentist 09:30", "n": 3})
    assert result.png.startswith(b"\x89PNG") and "collide" in result.text
    assert session.canvas.blank


def test_the_catalog_explains_every_look():
    looks = catalog("looks")["looks"]
    assert len(looks) == len(LOOKS) and all(": " in line for line in looks)


def test_the_look_guide_is_in_the_tool_the_model_sees():
    schema = json.dumps(BY_NAME["draw_poster"].schema)
    assert all(name in schema for name in LOOKS)
    assert "compare_looks" not in {tool.name for tool in TOOLS if tool.internal}


def test_a_bad_call_is_a_design_error_not_a_crash():
    with pytest.raises(DesignError):
        run_tool(Session(), "no_such_tool", {})
