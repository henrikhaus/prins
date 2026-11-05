"""Turns a note into a 312x216 image, then into ESC/POS raster commands."""

from __future__ import annotations

import time

from PIL import Image

from .design.canvas import Canvas, bitmap_to_image
from .store import Item

_MAX_ROWS_PER_BLOCK = 200  # Cheap printers misbehave on longer GS v 0 blocks.


def render_note(item: Item) -> Image.Image:
    """A custom design as it was drawn, or the plain layout for an ordinary note."""
    if item.bitmap:
        return bitmap_to_image(item.bitmap)

    origin = item.source.upper() + (f" - {item.sender}" if item.sender else "")
    footer = f"Due: {item.due}" if item.due else time.strftime("%a %d %b %H:%M", time.localtime(item.created_at))
    body_bottom = 186
    title_height = 150 if item.detail else 160
    canvas = Canvas(external=False)
    canvas.apply_all([
        {"op": "text", "s": origin, "x": 8, "y": 6, "w": 296, "h": 18, "font": "sans", "size": 16, "align": "l", "wrap": False},
        {"op": "shape", "kind": "rect", "x": 8, "y": 25, "w": 296, "h": 2},
        {"op": "text", "s": item.title, "x": 8, "y": 30, "w": 296, "h": title_height - (48 if item.detail else 0), "font": "sans-bold", "align": "l", "valign": "m"},
    ])
    if item.detail:
        canvas.apply({"op": "text", "s": item.detail, "x": 8, "y": 134, "w": 296, "h": body_bottom - 134, "font": "sans", "align": "l", "valign": "m"})
    canvas.apply({"op": "text", "s": footer, "x": 8, "y": 192, "w": 296, "h": 18, "font": "sans", "size": 15, "align": "l", "wrap": False})
    if item.priority == "high":
        canvas.apply({"op": "frame", "name": "thick", "size": 1})
    return canvas.image


def to_escpos(image: Image.Image, feed_lines: int = 3, paper_dots: int = 0) -> bytes:
    """ESC/POS bytes that print `image`, centered on paper `paper_dots` wide. 1 bit = black dot."""
    if image.mode != "1":
        image = image.convert("1")
    if paper_dots > image.width:
        padded = Image.new("1", (paper_dots, image.height), 1)
        padded.paste(image, ((paper_dots - image.width) // 2, 0))
        image = padded
    bytes_per_row = (image.width + 7) // 8
    # Pillow packs mode "1" with 1 = white, so invert it for the printer.
    packed = bytes(b ^ 0xFF for b in image.tobytes())

    out = bytearray(b"\x1b@")  # ESC @: reset
    for start in range(0, image.height, _MAX_ROWS_PER_BLOCK):
        rows = min(_MAX_ROWS_PER_BLOCK, image.height - start)
        out += b"\x1dv0\x00"  # GS v 0, normal size
        out += bytes((bytes_per_row & 0xFF, bytes_per_row >> 8, rows & 0xFF, rows >> 8))
        out += packed[start * bytes_per_row : (start + rows) * bytes_per_row]
    out += b"\x1bd" + bytes((feed_lines,))  # ESC d n: feed so the note clears the cutter bar
    return bytes(out)
