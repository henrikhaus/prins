"""Frames: decorative borders that fill a box's edge."""

from __future__ import annotations

from typing import Callable

from PIL import Image, ImageDraw

from .figures import figure_mask

Box = tuple[int, int, int, int]


def _rect(draw: ImageDraw.ImageDraw, box: Box, inset: int = 0, width: int = 1, radius: int = 0) -> None:
    x0, y0, x1, y1 = box
    shape = [x0 + inset, y0 + inset, x1 - inset, y1 - inset]
    if radius:
        draw.rounded_rectangle(shape, radius=radius, outline=1, width=width)
    else:
        draw.rectangle(shape, outline=1, width=width)


def _along_edges(box: Box, step: int) -> list[tuple[int, int]]:
    x0, y0, x1, y1 = box
    points = [(x, y) for x in range(x0, x1 + 1, step) for y in (y0, y1)]
    points += [(x, y) for y in range(y0, y1 + 1, step) for x in (x0, x1)]
    return points


def _dashed(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    for x in range(x0, x1 + 1, s * 2):
        draw.rectangle([x, y0, min(x + s - 1, x1), y0 + 1], fill=1)
        draw.rectangle([x, y1 - 1, min(x + s - 1, x1), y1], fill=1)
    for y in range(y0, y1 + 1, s * 2):
        draw.rectangle([x0, y, x0 + 1, min(y + s - 1, y1)], fill=1)
        draw.rectangle([x1 - 1, y, x1, min(y + s - 1, y1)], fill=1)


def _dotted(draw, box: Box, s: int) -> None:
    for x, y in _along_edges(box, s * 2):
        draw.ellipse([x - 1, y - 1, x + 1, y + 1], fill=1)


def _ticket(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    r = s * 3
    draw.rectangle(box, outline=1, width=2)
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=0)
        draw.arc([cx - r, cy - r, cx + r, cy + r], 0, 360, fill=1, width=2)


def _stamp(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle(box, fill=1)
    draw.rectangle([x0 + s * 3, y0 + s * 3, x1 - s * 3, y1 - s * 3], fill=0)
    for x, y in _along_edges(box, s * 3):
        draw.ellipse([x - s, y - s, x + s, y + s], fill=0)


def _film(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    band = s * 5
    for top in (y0, y1 - band):
        draw.rectangle([x0, top, x1, top + band], fill=1)
        for x in range(x0 + s, x1 - s, s * 3):
            draw.rectangle([x, top + s + 1, x + s, top + band - s - 1], fill=0)


def _checker(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    for x, y in [(x, y) for x in range(x0, x1 + 1, s) for y in range(y0, y1 + 1, s)]:
        edge = x < x0 + s * 2 or x > x1 - s * 2 or y < y0 + s * 2 or y > y1 - s * 2
        if edge and ((x - x0) // s + (y - y0) // s) % 2 == 0:
            draw.rectangle([x, y, min(x + s - 1, x1), min(y + s - 1, y1)], fill=1)


def _zigzag(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    step = s * 2
    top = [(x, y0 + (s if (x - x0) // step % 2 else 0)) for x in range(x0, x1 + 1, step)]
    bottom = [(x, y1 - (s if (x - x0) // step % 2 else 0)) for x in range(x0, x1 + 1, step)]
    left = [(x0 + (s if (y - y0) // step % 2 else 0), y) for y in range(y0, y1 + 1, step)]
    right = [(x1 - (s if (y - y0) // step % 2 else 0), y) for y in range(y0, y1 + 1, step)]
    for line in (top, bottom, left, right):
        draw.line(line, fill=1, width=2)


def _scallop(draw, box: Box, s: int) -> None:
    r = s * 2
    for x, y in _along_edges(box, r * 2):
        draw.ellipse([x - r, y - r, x + r, y + r], outline=1, width=2)


def _brackets(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    arm = s * 6
    for cx, sx in ((x0, 1), (x1, -1)):
        for cy, sy in ((y0, 1), (y1, -1)):
            draw.line([(cx + sx * arm, cy), (cx, cy), (cx, cy + sy * arm)], fill=1, width=3)


def _ornate(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    _rect(draw, box, 0, 2)
    _rect(draw, box, s + 2, 1)
    r = s * 3
    for cx, cy in ((x0, y0), (x1, y0), (x0, y1), (x1, y1)):
        cx = cx + r if cx == x0 else cx - r
        cy = cy + r if cy == y0 else cy - r
        draw.rectangle([cx - r, cy - r, cx + r, cy + r], fill=0, outline=1)
        draw.polygon([(cx, cy - r + 2), (cx + r - 2, cy), (cx, cy + r - 2), (cx - r + 2, cy)], fill=1)


def _shadow(draw, box: Box, s: int) -> None:
    x0, y0, x1, y1 = box
    draw.rectangle([x0 + s, y0 + s, x1, y1], fill=1)
    draw.rectangle([x0, y0, x1 - s, y1 - s], fill=0, outline=1, width=2)


FRAMES: dict[str, Callable[[ImageDraw.ImageDraw, Box, int], None]] = {
    "line": lambda d, b, s: _rect(d, b, 0, max(1, s // 2)),
    "thick": lambda d, b, s: _rect(d, b, 0, s * 2),
    "double": lambda d, b, s: (_rect(d, b, 0, 2), _rect(d, b, s + 3, 1)),
    "rounded": lambda d, b, s: _rect(d, b, 0, 2, s * 4),
    "dashed": _dashed,
    "dotted": _dotted,
    "ticket": _ticket,
    "stamp": _stamp,
    "film": _film,
    "checker": _checker,
    "zigzag": _zigzag,
    "scallop": _scallop,
    "brackets": _brackets,
    "ornate": _ornate,
    "shadow": _shadow,
}


def frame_mask(name: str, canvas_size: tuple[int, int], box: Box, size: int) -> Image.Image:
    """Any figure name also works as a frame: `heart`, `star` and so on repeat around the edge."""
    mask = Image.new("1", canvas_size, 0)
    if name in FRAMES:
        FRAMES[name](ImageDraw.Draw(mask), box, size)
        return mask

    tile = size * 3
    stamp = figure_mask(name, tile, tile)
    x0, y0, x1, y1 = box
    columns = max(1, (x1 - x0 - tile) // (tile + 2))
    rows = max(1, (y1 - y0 - tile) // (tile + 2))
    for i in range(columns + 1):
        x = x0 + i * (x1 - x0 - tile) // columns
        mask.paste(1, (x, y0), stamp)
        mask.paste(1, (x, y1 - tile), stamp)
    for j in range(rows + 1):
        y = y0 + j * (y1 - y0 - tile) // rows
        mask.paste(1, (x0, y), stamp)
        mask.paste(1, (x1 - tile, y), stamp)
    return mask
