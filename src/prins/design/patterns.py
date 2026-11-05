"""Patterns: each decides, for one pixel, whether it is black. Use as a fill anywhere via ink."""

from __future__ import annotations

import math
from typing import Callable

from PIL import Image

_BAYER_8 = [
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
]


def bayer(x: int, y: int, darkness: float) -> bool:
    """Ordered dithering: darkness 0 is white and 1 is black."""
    return (_BAYER_8[y % 8][x % 8] + 0.5) / 64 < darkness


def _hash(x: int, y: int) -> float:
    value = (x * 374761393 + y * 668265263) & 0xFFFFFFFF
    value = ((value ^ (value >> 13)) * 1274126177) & 0xFFFFFFFF
    return (value ^ (value >> 16)) / 0xFFFFFFFF


def noise(x: float, y: float) -> float:
    """Stable random value from 0 to 1 for a pixel."""
    return _hash(int(x), int(y))


Pattern = Callable[[int, int, int, int, int], bool]  # x, y, size, canvas width, canvas height

PATTERNS: dict[str, Pattern] = {
    "checker": lambda x, y, s, w, h: (x // s + y // s) % 2 == 0,
    "stripes": lambda x, y, s, w, h: (x + y) % (s * 2) < s,
    "stripes-back": lambda x, y, s, w, h: (x - y) % (s * 2) < s,
    "hlines": lambda x, y, s, w, h: y % (s * 2) < s,
    "vlines": lambda x, y, s, w, h: x % (s * 2) < s,
    "grid": lambda x, y, s, w, h: x % (s * 2) == 0 or y % (s * 2) == 0,
    "dots": lambda x, y, s, w, h: (x % (s * 2) - s) ** 2 + (y % (s * 2) - s) ** 2 < (s * 0.55) ** 2,
    "polka": lambda x, y, s, w, h: ((x + (y // (s * 2) % 2) * s) % (s * 2) - s) ** 2 + (y % (s * 2) - s) ** 2 < (s * 0.6) ** 2,
    "hatch": lambda x, y, s, w, h: (x + y) % (s * 2) == 0,
    "crosshatch": lambda x, y, s, w, h: (x + y) % (s * 2) == 0 or (x - y) % (s * 2) == 0,
    "brick": lambda x, y, s, w, h: y % (s * 2) == 0 or (x + (y // (s * 2) % 2) * s * 2) % (s * 4) == 0,
    "waves": lambda x, y, s, w, h: (y + math.sin(x / (s * 1.6)) * s * 1.5) % (s * 3) < s,
    "zigzag": lambda x, y, s, w, h: (y + abs(x % (s * 4) - s * 2)) % (s * 3) < s,
    "scales": lambda x, y, s, w, h: abs(math.hypot((x + (y // (s * 2) % 2) * s) % (s * 2) - s, y % (s * 2)) - s * 0.95) < 1,
    "diamonds": lambda x, y, s, w, h: abs(x % (s * 2) - s) + abs(y % (s * 2) - s) < s * 0.7,
    "plaid": lambda x, y, s, w, h: x % (s * 4) < s or y % (s * 4) < s or (x + y) % 4 == 0,
    "weave": lambda x, y, s, w, h: ((x // s + y // s) % 2 == 0) == (x % s < s / 2 if (x // s) % 2 else y % s < s / 2),
    "confetti": lambda x, y, s, w, h: _hash(x // s, y // s) < 0.14,
    "noise": lambda x, y, s, w, h: _hash(x // s, y // s) < 0.5,
    "rings": lambda x, y, s, w, h: math.hypot(x - w / 2, y - h / 2) % (s * 2) < s,
    "rays": lambda x, y, s, w, h: (math.atan2(y - h / 2, x - w / 2) + math.pi) * s % 2 < 1,
    "spiral": lambda x, y, s, w, h: (math.hypot(x - w / 2, y - h / 2) / s + math.atan2(y - h / 2, x - w / 2) / math.pi * 2) % 2 < 1,
    "moire": lambda x, y, s, w, h: math.hypot(x - w * 0.35, y - h / 2) % (s * 2) < s != (math.hypot(x - w * 0.65, y - h / 2) % (s * 2) < s),
    "fade-right": lambda x, y, s, w, h: bayer(x, y, x / max(w - 1, 1)),
    "fade-left": lambda x, y, s, w, h: bayer(x, y, 1 - x / max(w - 1, 1)),
    "fade-down": lambda x, y, s, w, h: bayer(x, y, y / max(h - 1, 1)),
    "fade-up": lambda x, y, s, w, h: bayer(x, y, 1 - y / max(h - 1, 1)),
    "glow": lambda x, y, s, w, h: bayer(x, y, 1 - min(1, math.hypot(x - w / 2, y - h / 2) / (math.hypot(w, h) / 2))),
    "vignette": lambda x, y, s, w, h: bayer(x, y, min(1, math.hypot(x - w / 2, y - h / 2) / (math.hypot(w, h) / 2))),
}


def has_pattern(spec: str) -> bool:
    name = spec.split(":")[0]
    return name == "gray" or name in PATTERNS


def pattern_image(spec: str, width: int, height: int) -> Image.Image:
    """`name` or `name:size`. `gray:30` is a flat 30% tone. Returns a mode "1" image, 255 = black."""
    name, _, argument = spec.partition(":")
    try:
        size = max(1, int(argument)) if argument else (50 if name == "gray" else 4)
    except ValueError as exc:
        raise ValueError(f"Bad pattern size in {spec!r}") from exc

    if name == "gray":
        level = min(size, 100) / 100
        test: Callable[[int, int], bool] = lambda x, y: bayer(x, y, level)
    else:
        pattern = PATTERNS[name]
        test = lambda x, y: pattern(x, y, size, width, height)

    image = Image.new("1", (width, height), 0)
    image.putdata([255 if test(x, y) else 0 for y in range(height) for x in range(width)])
    return image
