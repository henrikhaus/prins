"""The drawing tools. One definition, used by the MCP server and by the internal designer.

Tokens are the budget. Tool definitions stay short because they sit in every request, the names
of figures and fonts live behind `catalog`, and draw_batch does a whole design in one call.
"""

from __future__ import annotations

import io
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Optional, Protocol

from .canvas import Canvas, DesignError, catalog
from .poster import LOOK_GUIDE, compare

GUIDE = """Prins prints notes on a 312x216 black and white pixel grid. Origin is top-left.
Start with draw_poster: it gives the best design for the fewest words. Use the other draw_* tools for details it can't do, then print_note or send_to_friend. draw_batch is the cheapest way to do several steps.
x,y,w,h default to the whole grid. ink is black, white, invert, or a pattern name (dots:6, gray:30).
For a brand logo use draw_logo first. For anything else use draw_svg (path data), draw_image (URL, path, base64) or draw_pixels. Any design is possible.
preview shows the note. Text auto-sizes to fit its box when size is 0."""

_BOX = {
    "x": {"type": "number"},
    "y": {"type": "number"},
    "w": {"type": "number"},
    "h": {"type": "number"},
}
_INK = {"ink": {"type": "string"}, "rot": {"type": "number"}}


def _props(*groups: dict, required: tuple[str, ...] = ()) -> dict:
    merged: dict[str, Any] = {}
    for group in groups:
        merged.update(group)
    schema: dict[str, Any] = {"type": "object", "properties": merged}
    if required:
        schema["required"] = list(required)
    return schema


def _s(description: str = "") -> dict:
    return {"type": "string", "description": description} if description else {"type": "string"}


@dataclass
class Result:
    text: str = "ok"
    png: Optional[bytes] = None


class Output(Protocol):
    """Where finished notes go. The internal designer has none: it only draws."""

    def print_note(self, title: str, bitmap: str) -> str: ...
    def list_friends(self) -> list[dict]: ...
    def send_to_friend(self, friend: str, title: str, bitmap: str) -> str: ...


@dataclass
class Session:
    canvas: Canvas = field(default_factory=Canvas)
    output: Optional[Output] = None
    designs_dir: Optional[Path] = None


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    schema: dict
    run: Callable[[Session, dict], Result]
    internal: bool = True  # The internal designer may use it too.


def _draw(op: str) -> Callable[[Session, dict], Result]:
    def run(session: Session, args: dict) -> Result:
        session.canvas.apply({"op": op, **args})
        return Result()

    return run


def _batch(session: Session, args: dict) -> Result:
    ops = args.get("ops")
    if not isinstance(ops, list):
        raise DesignError("ops must be a list.")
    session.canvas.apply_all(ops)
    return Result()


def _poster(session: Session, args: dict) -> Result:
    session.canvas.apply({"op": "poster", **args})
    report = session.canvas.report
    return Result(report.summary() if report else "ok")


def _compare(session: Session, args: dict) -> Result:
    png, names = compare(args, int(args.get("n", 4) or 4), session.canvas.sender)
    return Result(f"{names}. Pick one and call draw_poster with its look.", png=png)


def _catalog(session: Session, args: dict) -> Result:
    return Result(json.dumps(catalog(args.get("kind")), ensure_ascii=False, separators=(",", ":")))


def _undo(session: Session, args: dict) -> Result:
    session.canvas.undo(int(args.get("n", 1)))
    return Result()


def _clear(session: Session, args: dict) -> Result:
    session.canvas.clear()
    return Result()


def _preview(session: Session, args: dict) -> Result:
    # An image this size costs far fewer tokens than describing the pixels in text.
    buffer = io.BytesIO()
    session.canvas.image.convert("L").save(buffer, "PNG", optimize=True)
    return Result(f"{len(session.canvas.ops)} ops", png=buffer.getvalue())


def _design_path(session: Session, name: str) -> Path:
    if session.designs_dir is None:
        raise DesignError("Saved designs aren't available here.")
    if not re.fullmatch(r"[\w -]{1,60}", name):
        raise DesignError("A design name is letters, numbers, spaces, - and _.")
    return session.designs_dir / f"{name}.json"


def _save(session: Session, args: dict) -> Result:
    path = _design_path(session, str(args.get("name", "")))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(session.canvas.ops, ensure_ascii=False, separators=(",", ":")))
    return Result(f"saved {path.stem}")


def _load(session: Session, args: dict) -> Result:
    path = _design_path(session, str(args.get("name", "")))
    if not path.exists():
        saved = sorted(p.stem for p in path.parent.glob("*.json")) if path.parent.exists() else []
        raise DesignError(f"No design named {path.stem!r}. Saved: {', '.join(saved) or 'none'}.")
    session.canvas.apply_all(json.loads(path.read_text()))
    return Result()


def _finish(session: Session, args: dict) -> tuple[str, str]:
    """A note can be plain text with no drawing at all, which is the cheapest note there is."""
    text = args.get("text")
    if text:
        session.canvas.apply({"op": "text", "s": str(text), "x": 10, "y": 10, "w": 292, "h": 196})
    if session.canvas.blank:
        raise DesignError("The note is blank. Draw something, or pass text.")
    title = str(args.get("title") or text or "Note")[:120]
    return title, session.canvas.bitmap()


def _require_output(session: Session) -> Output:
    if session.output is None:
        raise DesignError("Printing isn't available here.")
    return session.output


def _print(session: Session, args: dict) -> Result:
    output = _require_output(session)
    title, bitmap = _finish(session, args)
    message = output.print_note(title, bitmap)
    session.canvas.clear()
    return Result(message)


def _friends(session: Session, args: dict) -> Result:
    friends = _require_output(session).list_friends()
    return Result(json.dumps(friends, ensure_ascii=False, separators=(",", ":")))


def _send(session: Session, args: dict) -> Result:
    output = _require_output(session)
    friend = args.get("friend")
    if not friend:
        raise DesignError("Say which friend. list_friends shows who you can send to.")
    title, bitmap = _finish(session, args)
    message = output.send_to_friend(str(friend), title, bitmap)
    session.canvas.clear()
    return Result(message)


_POSTER_FIELDS = {
    "say": _s("fewest words that carry it, 1-4"),
    "sub": _s("short detail line"),
    "big": _s("number or time to feature"),
    "pic": _s("subject: an emoji, or logo:brand"),
    "data": {"type": "array", "items": {"type": "number"}},
    "items": {"type": "array", "items": {"type": "string"}},
    "qr": _s(),
    "seed": {"type": "number"},
}

TOOLS: list[Tool] = [
    Tool("draw_poster", "Designs a whole note from its meaning: layout, type and shading. Never invent facts.",
         _props({"look": _s(f"omit to auto-choose. {LOOK_GUIDE}"), **_POSTER_FIELDS}), _poster),
    Tool("compare_looks", "See content in the looks that suit it, as one numbered image. Takes draw_poster's fields, plus n. Changes nothing.",
         _props({"say": _s(), "n": {"type": "number"}}), _compare, internal=False),
    Tool("draw_batch", "Run many ops in one call. Each op is {op:poster|text|figure|pattern|frame|shape|image|svg|logo|pixels|formula|qr|transform|repeat|scatter|clear, ...same args as its draw_ tool}. repeat: {n,dx,dy,ops}. scatter: {n,seed,x,y,w,h,ops}.",
         {"type": "object", "properties": {"ops": {"type": "array", "items": {"type": "object"}}}, "required": ["ops"]}, _batch),
    Tool("draw_text", "Text. size 0 fits the box. align l|c|r, valign t|m|b.",
         _props({"s": _s(), "font": _s("see catalog fonts, default sans-bold"), "size": {"type": "number"}, "align": _s(), "valign": _s(), "wrap": {"type": "boolean"}}, _BOX, _INK, required=("s",)), _draw("text")),
    Tool("draw_figure", "A figure (see catalog figures), or any emoji as name emoji:🎂.",
         _props({"name": _s()}, _BOX, _INK, required=("name",)), _draw("figure")),
    Tool("draw_pattern", "Fill a box with a pattern (see catalog patterns). name:size sets scale, gray:N a flat tone. shape ellipse for a round fill.",
         _props({"name": _s(), "shape": _s()}, _BOX, _INK, required=("name",)), _draw("pattern")),
    Tool("draw_frame", "A border (see catalog frames). Any figure name also repeats around the edge.",
         _props({"name": _s(), "size": {"type": "number"}, "inset": {"type": "number"}}, _BOX, {"ink": _INK["ink"]}), _draw("frame")),
    Tool("draw_shape", "kind: rect, rrect (r), ellipse, line, curve, polygon (pts [[x,y],..]), arc, pie, chord (a0,a1 degrees). fill false for outline, lw line width.",
         _props({"kind": _s(), "pts": {"type": "array"}, "fill": {"type": "boolean"}, "lw": {"type": "number"}, "r": {"type": "number"}, "a0": {"type": "number"}, "a1": {"type": "number"}}, _BOX, {"ink": _INK["ink"]}, required=("kind",)), _draw("shape")),
    Tool("draw_logo", "A brand logo by name (spotify, nike...), from Simple Icons.",
         _props({"name": _s()}, _BOX, _INK, required=("name",)), _draw("logo")),
    Tool("draw_svg", "Any vector. d: SVG path data with vb viewBox (default 0 0 24 24), or svg: full markup, or src: SVG URL or path.",
         _props({"d": _s(), "vb": _s(), "evenodd": {"type": "boolean"}, "svg": _s(), "src": _s()}, _BOX, _INK), _draw("svg")),
    Tool("draw_image", "Any image, dithered to one bit. src: URL, file path, or base64. fit contain|cover|stretch. dither atkinson|floyd|bayer|halftone|threshold.",
         _props({"src": _s(), "fit": _s(), "dither": _s(), "threshold": {"type": "number"}, "invert": {"type": "boolean"}}, _BOX, _INK, required=("src",)), _draw("image"), internal=False),
    Tool("draw_pixels", "Exact pixels. rows: strings where . is off and anything else on, with scale. Or b64: packed bits (1 = black) with w.",
         _props({"rows": {"type": "array", "items": _s()}, "b64": _s(), "x": {"type": "number"}, "y": {"type": "number"}, "w": {"type": "number"}, "scale": {"type": "number"}}, _INK), _draw("pixels")),
    Tool("draw_formula", "Per-pixel math: true paints. Vars x,y,u,v(0-1),r,a(polar),W,H. Funcs sin,cos,tan,atan2,sqrt,abs,floor,hypot,min,max,noise,pow. Example: sin(r/6+a*3)>0",
         _props({"f": _s()}, _BOX, _INK, required=("f",)), _draw("formula")),
    Tool("draw_qr", "A QR code for s.", _props({"s": _s(), "ecc": _s("l|m|q|h")}, _BOX, _INK, required=("s",)), _draw("qr")),
    Tool("transform", "Change a region. kind: invert, flip-h, flip-v, rotate (deg), mirror-h, mirror-v, shift (dx,dy), pixelate (size), outline.",
         _props({"kind": _s(), "deg": {"type": "number"}, "dx": {"type": "number"}, "dy": {"type": "number"}, "size": {"type": "number"}}, _BOX, required=("kind",)), _draw("transform")),
    Tool("catalog", "Names. kind: looks, figures, patterns, frames, fonts, dithers, ops, system_fonts. Omit for most.",
         _props({"kind": _s()}), _catalog),
    Tool("undo", "Undo n steps.", _props({"n": {"type": "number"}}), _undo),
    Tool("clear", "A blank note.", _props(), _clear),
    Tool("preview", "The note as an image.", _props(), _preview, internal=False),
    Tool("save_design", "Save the current note under a name.", _props({"name": _s()}, required=("name",)), _save, internal=False),
    Tool("load_design", "Draw a saved design.", _props({"name": _s()}, required=("name",)), _load, internal=False),
    Tool("print_note", "Print the current note on the user's Prins. text makes a plain note. title labels it.",
         _props({"title": _s(), "text": _s()}), _print, internal=False),
    Tool("list_friends", "Friends, and who accepts notes.", _props(), _friends, internal=False),
    Tool("send_to_friend", "Send the current note to a friend's Prins, which waits for their button. text makes a plain note.",
         _props({"friend": _s("name or id"), "title": _s(), "text": _s()}, required=("friend",)), _send, internal=False),
]

BY_NAME = {tool.name: tool for tool in TOOLS}


def run_tool(session: Session, name: str, args: Optional[dict]) -> Result:
    tool = BY_NAME.get(name)
    if tool is None:
        raise DesignError(f"Unknown tool {name!r}.")
    return tool.run(session, args or {})
