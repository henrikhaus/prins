"""Draws a note as a 1-bit image, then encodes it as ESC/POS raster commands.

Rendering on the laptop means the printer never needs fonts, so any language prints correctly.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from .store import Item

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
_MARGIN = 10
_MAX_ROWS_PER_BLOCK = 200  # Cheap printers misbehave on longer GS v 0 blocks.


def _font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if Path(path).exists():
            # In Helvetica.ttc, face index 1 is bold.
            index = 1 if bold and path.endswith(".ttc") else 0
            return ImageFont.truetype(path, size, index=index)
    return ImageFont.load_default(size)


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int) -> Iterable[str]:
    line = ""
    for word in text.split():
        # A single word wider than the paper is broken by character.
        while draw.textlength(word, font=font) > width:
            cut = len(word) - 1
            while cut > 1 and draw.textlength(word[:cut], font=font) > width:
                cut -= 1
            if line:
                yield line
                line = ""
            yield word[:cut]
            word = word[cut:]
        candidate = f"{line} {word}".strip()
        if draw.textlength(candidate, font=font) <= width:
            line = candidate
        else:
            yield line
            line = word
    if line:
        yield line


def render_note(item: Item, width: int = 384) -> Image.Image:
    """Returns a mode "1" image exactly `width` dots wide, with black text on white."""
    probe = ImageDraw.Draw(Image.new("1", (width, 10)))
    usable = width - 2 * _MARGIN
    small, title_font, body = _font(20), _font(34, bold=True), _font(24)

    origin = item.source.upper() + (f" - {item.sender}" if item.sender else "")
    if probe.textlength(origin, font=small) > usable:
        while origin and probe.textlength(origin + "...", font=small) > usable:
            origin = origin[:-1]
        origin += "..."
    title_lines = list(_wrap(probe, item.title, title_font, usable))
    detail_lines = list(_wrap(probe, item.detail, body, usable)) if item.detail else []
    footer = time.strftime("%a %d %b %H:%M", time.localtime(item.created_at))
    if item.due:
        footer = f"Due: {item.due}"

    height = _MARGIN + 28 + 8 + len(title_lines) * 40 + 8
    height += len(detail_lines) * 30 + (8 if detail_lines else 0) + 28 + _MARGIN

    image = Image.new("1", (width, height), 1)
    draw = ImageDraw.Draw(image)
    y = _MARGIN
    draw.text((_MARGIN, y), origin, font=small, fill=0)
    y += 28
    draw.line((_MARGIN, y, width - _MARGIN, y), fill=0, width=2)
    y += 8
    for line in title_lines:
        draw.text((_MARGIN, y), line, font=title_font, fill=0)
        y += 40
    y += 8
    for line in detail_lines:
        draw.text((_MARGIN, y), line, font=body, fill=0)
        y += 30
    if detail_lines:
        y += 8
    draw.text((_MARGIN, y), footer, font=small, fill=0)
    return image


def to_escpos(image: Image.Image, feed_lines: int = 3) -> bytes:
    """ESC/POS bytes that print `image`. In the raster format, a 1 bit means a black dot."""
    if image.mode != "1":
        image = image.convert("1")
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
