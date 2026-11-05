"""Draws a design for the label printer from a list of shapes.

A design is a list of dicts ("ops"), so the model can return it as JSON and we can show it
back to the model next time. Rendering is anti-aliased and then cut to pure black and white at
the same threshold the printer server uses, so the preview is what comes out of the printer.
"""

from __future__ import annotations

import io
from dataclasses import dataclass, field
from typing import Any, Iterable

from PIL import Image, ImageChops, ImageDraw

from .render import _font, _wrap

CANVAS_WIDTH = 312   # printer/server.py GRID_WIDTH
CANVAS_HEIGHT = 216  # printer/server.py GRID_HEIGHT
THRESHOLD = 128      # printer/server.py default
MIN_TEXT_PX = 16     # Smaller text smears on a 203 dpi thermal head.
EDGE_SLACK = 2
THUMB_MAX = (116, 80)  # What the 160x80 screen has room for next to its caption.

_SHAPES = ("rect", "ellipse", "polygon", "polyline")
_FILLS = {"black": 255, "gray": 128, "light": 64}  # coverage of black ink, out of 255


@dataclass
class Rendered:
    image: Image.Image  # mode "1": 1 is white, 0 is black
    warnings: list[str] = field(default_factory=list)
    ink: float = 0.0    # Fraction of the label that is black.


def _pattern(coverage: int, size: tuple[int, int]) -> Image.Image:
    """An "L" mask, 255 where a fill of this coverage puts ink. Solid, checkerboard or sparse dots."""
    if coverage >= 255:
        return Image.new("L", size, 255)
    tile = Image.new("L", (4, 4), 0)
    pixels = tile.load()
    for y in range(4):
        for x in range(4):
            if coverage >= 128:
                on = (x + y) % 2 == 0
            else:
                on = x % 2 == 0 and y % 2 == 0
            pixels[x, y] = 255 if on else 0
    out = Image.new("L", size, 0)
    for y in range(0, size[1], 4):
        for x in range(0, size[0], 4):
            out.paste(tile, (x, y))
    return out


def _num(op: dict, key: str) -> float | None:
    value = op.get(key)
    return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def _stroke(op: dict, filled: bool) -> int:
    """Outline width: what the op asks for, else 3 px for an outline and none under a fill."""
    width = _num(op, "width")
    return int(width) if width is not None else (0 if filled else 3)


def _points(op: dict, need: int) -> list[tuple[float, float]] | None:
    raw = op.get("points")
    if not isinstance(raw, list):
        return None
    try:
        points = [(float(p[0]), float(p[1])) for p in raw]
    except (TypeError, ValueError, IndexError):
        return None
    return points if len(points) >= need else None


def _check_bounds(warnings: list[str], index: int, name: str, box: Iterable[float], size: tuple[int, int]) -> None:
    left, top, right, bottom = box
    width, height = size
    sides = []
    if left < -EDGE_SLACK:
        sides.append(f"left edge by {round(-left)}px")
    if top < -EDGE_SLACK:
        sides.append(f"top edge by {round(-top)}px")
    if right > width + EDGE_SLACK:
        sides.append(f"right edge by {round(right - width)}px")
    if bottom > height + EDGE_SLACK:
        sides.append(f"bottom edge by {round(bottom - height)}px")
    if sides:
        warnings.append(f"op {index} ({name}) runs past the {' and '.join(sides)}; the canvas is {width}x{height}")


def render_design(ops: list[dict[str, Any]], size: tuple[int, int] = (CANVAS_WIDTH, CANVAS_HEIGHT)) -> Rendered:
    """Draw `ops` on a white canvas. Problems the model can fix come back as warnings."""
    width, height = size
    canvas = Image.new("L", size, 255)
    draw = ImageDraw.Draw(canvas)
    warnings: list[str] = []

    def ink(op: dict, key: str = "color") -> int:
        return 255 if op.get(key) == "white" else 0

    def fill_shape(op: dict, paint) -> None:
        """Fill with solid, gray or light ink. `paint(draw, value)` draws the shape in the mask."""
        coverage = _FILLS.get(op.get("fill") or "none")
        if op.get("fill") == "white":
            paint(draw, 255)
        elif coverage:
            mask = Image.new("L", size, 0)
            paint(ImageDraw.Draw(mask), 255)
            canvas.paste(0, mask=ImageChops.multiply(mask, _pattern(coverage, size)))

    for index, op in enumerate(ops):
        kind = op.get("type")
        try:
            if kind == "text":
                text = str(op.get("text") or "")
                x, y = _num(op, "x"), _num(op, "y")
                if not text or x is None or y is None:
                    warnings.append(f"op {index} (text) needs text, x and y")
                    continue
                px = int(_num(op, "size") or 28)
                if px < MIN_TEXT_PX:
                    warnings.append(f"op {index} (text {text[:20]!r}) is {px}px: use at least {MIN_TEXT_PX}px so it prints legibly")
                font = _font(max(8, min(px, 200)), bool(op.get("bold")))
                max_width = _num(op, "max_width")
                if max_width:
                    text = "\n".join(
                        line for paragraph in text.split("\n") for line in (list(_wrap(draw, paragraph, font, int(max_width))) or [""])
                    )
                align = str(op.get("align"))
                if align not in ("left", "center", "right"):
                    align = "left"
                anchor = {"left": "la", "center": "ma", "right": "ra"}[align]
                draw.multiline_text((x, y), text, font=font, fill=ink(op), anchor=anchor, align=align, spacing=4)
                _check_bounds(warnings, index, f"text {text.splitlines()[0][:20]!r}",
                              draw.multiline_textbbox((x, y), text, font=font, anchor=anchor, align=align, spacing=4), size)
            elif kind in ("rect", "ellipse"):
                x, y, w, h = (_num(op, k) for k in ("x", "y", "w", "h"))
                if x is None or y is None or w is None or h is None or w <= 0 or h <= 0:
                    warnings.append(f"op {index} ({kind}) needs x, y, w and h, with w and h above 0")
                    continue
                box = [x, y, x + w - 1, y + h - 1]
                radius = int(_num(op, "radius") or 0)
                if kind == "rect":
                    def paint(d, value, box=box, radius=radius):
                        d.rounded_rectangle(box, radius=radius, fill=value)
                else:
                    def paint(d, value, box=box):
                        d.ellipse(box, fill=value)
                fill_shape(op, paint)
                stroke = _stroke(op, op.get("fill") not in (None, "none"))
                if stroke > 0:
                    if kind == "rect":
                        draw.rounded_rectangle(box, radius=radius, outline=ink(op), width=stroke)
                    else:
                        draw.ellipse(box, outline=ink(op), width=stroke)
                _check_bounds(warnings, index, kind, (x, y, x + w, y + h), size)
            elif kind in ("polygon", "polyline"):
                points = _points(op, 3 if kind == "polygon" else 2)
                if points is None:
                    warnings.append(f"op {index} ({kind}) needs points: a list of [x, y] pairs, at least {3 if kind == 'polygon' else 2}")
                    continue
                if kind == "polygon":
                    fill_shape(op, lambda d, value, points=points: d.polygon(points, fill=value))
                filled = kind == "polygon" and op.get("fill") not in (None, "none")
                stroke = _stroke(op, filled)
                if stroke > 0:
                    line = points + [points[0]] if kind == "polygon" else points
                    draw.line(line, fill=ink(op), width=stroke, joint="curve")
                xs, ys = [p[0] for p in points], [p[1] for p in points]
                _check_bounds(warnings, index, kind, (min(xs), min(ys), max(xs), max(ys)), size)
            else:
                warnings.append(f"op {index} has type {kind!r}; use one of text, {', '.join(_SHAPES)}")
        except (ValueError, TypeError) as exc:
            warnings.append(f"op {index} ({kind}) could not be drawn: {exc}")

    bitmap = canvas.point(lambda v: 255 if v >= THRESHOLD else 0).convert("1")
    black = bitmap.convert("L").histogram()[0]
    coverage = black / (size[0] * size[1])
    if coverage < 0.002:
        warnings.append("the label is blank: nothing visible was drawn")
    elif coverage > 0.6:
        warnings.append(f"{round(coverage * 100)}% of the label is black; use outlines or gray so it prints lighter")
    return Rendered(bitmap, warnings, coverage)


def thumbnail_2bpp(image: Image.Image, limit: tuple[int, int] = THUMB_MAX) -> tuple[int, int, bytes]:
    """The picture for the 160x80 screen: four gray levels, four pixels per byte, first pixel in the high bits."""
    scale = min(limit[0] / image.width, limit[1] / image.height, 1.0)
    width, height = max(1, round(image.width * scale)), max(1, round(image.height * scale))
    small = image.convert("L").resize((width, height), Image.LANCZOS)
    levels = [min(3, round(255 * (v / 255) ** 1.6 / 255 * 3)) for v in small.tobytes()]  # darker mid-tones keep thin text visible
    row = (width + 3) // 4
    out = bytearray(row * height)
    for y in range(height):
        for x in range(width):
            out[y * row + (x >> 2)] |= levels[y * width + x] << (6 - 2 * (x & 3))
    return width, height, bytes(out)


def png_bytes(image: Image.Image) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()
