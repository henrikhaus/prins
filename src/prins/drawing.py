"""What the label maker adds around the design engine: quality checks, and the thumbnail.

The engine (src/prins/design/) draws. This module says what is wrong with a finished design,
in words the drawing agent can act on, and makes the picture for the 160x80 screen.
"""

from __future__ import annotations

import io

from PIL import Image

from .design import Canvas

MIN_TEXT_PX = 16     # Smaller text smears on a 203 dpi thermal head.
THUMB_MAX = (116, 80)  # What the 160x80 screen has room for next to its caption.
_MAX_INK = 0.6


def ink_fraction(image: Image.Image) -> float:
    """The fraction of the label that is black."""
    return image.convert("L").histogram()[0] / (image.width * image.height)


def check_design(canvas: Canvas) -> list[str]:
    """Problems the agent can fix before the design is accepted. Empty means fine."""
    ink = ink_fraction(canvas.image)
    if ink < 0.002:
        return ["the label is blank: nothing visible was drawn"]
    warnings: list[str] = []
    if ink > _MAX_INK:
        warnings.append(f"{round(ink * 100)}% of the label is black; use outlines or lighter patterns so it prints lighter")
    for index, op in enumerate(canvas.ops):
        size = op.get("size")
        if op.get("op") == "text" and isinstance(size, (int, float)) and 0 < size < MIN_TEXT_PX:
            warnings.append(f"op {index}: text {str(op.get('s', ''))[:20]!r} is {size:g}px; use at least {MIN_TEXT_PX}px so it prints legibly")
    return warnings


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
