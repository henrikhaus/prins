"""Ready-made figures, drawn in a 100x100 space so they stay crisp at any size.

A figure is a list of steps. Lowercase paints and uppercase erases:
  e/E x0 y0 x1 y1        ellipse
  r/R x0 y0 x1 y1        rectangle
  p/P x y x y ...        polygon
  l/L width x y x y ...  line
"""

from __future__ import annotations

import math

from PIL import Image, ImageDraw


def _star(points: int, inner: float = 0.42, cx: float = 50, cy: float = 52, radius: float = 50) -> tuple:
    coords: list[float] = []
    for i in range(points * 2):
        r = radius if i % 2 == 0 else radius * inner
        angle = -math.pi / 2 + i * math.pi / points
        coords += [cx + r * math.cos(angle), cy + r * math.sin(angle)]
    return ("p", *coords)


def _regular(sides: int) -> tuple:
    coords: list[float] = []
    for i in range(sides):
        angle = -math.pi / 2 + i * 2 * math.pi / sides
        coords += [50 + 50 * math.cos(angle), 50 + 50 * math.sin(angle)]
    return ("p", *coords)


def _heart() -> tuple:
    coords: list[float] = []
    for i in range(64):
        t = i / 64 * 2 * math.pi
        coords += [50 + 3 * 16 * math.sin(t) ** 3, 46 - 3 * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t))]
    return ("p", *coords)


def _spiral() -> tuple:
    coords: list[float] = []
    for i in range(160):
        angle = i / 160 * 6 * math.pi
        radius = 2 + i / 160 * 46
        coords += [50 + radius * math.cos(angle), 50 + radius * math.sin(angle)]
    return ("l", 5, *coords)


def _rays(count: int, inner: float, outer: float, width: float) -> list[tuple]:
    steps = []
    for i in range(count):
        angle = i * 2 * math.pi / count
        steps.append(("l", width, 50 + inner * math.cos(angle), 50 + inner * math.sin(angle), 50 + outer * math.cos(angle), 50 + outer * math.sin(angle)))
    return steps


FIGURES: dict[str, list[tuple]] = {
    "heart": [_heart()],
    "star": [_star(5)],
    "star4": [_star(4, 0.25)],
    "star6": [_star(6, 0.55)],
    "sparkle": [_star(4, 0.14, 50, 50)],
    "burst": [_star(16, 0.68, 50, 50)],
    "circle": [("e", 0, 0, 100, 100)],
    "ring": [("e", 0, 0, 100, 100), ("E", 18, 18, 82, 82)],
    "target": [("e", 0, 0, 100, 100), ("E", 14, 14, 86, 86), ("e", 28, 28, 72, 72), ("E", 40, 40, 60, 60)],
    "square": [("r", 0, 0, 100, 100)],
    "diamond": [("p", 50, 0, 100, 50, 50, 100, 0, 50)],
    "triangle": [("p", 50, 4, 100, 96, 0, 96)],
    "hexagon": [_regular(6)],
    "octagon": [_regular(8)],
    "plus": [("r", 35, 0, 65, 100), ("r", 0, 35, 100, 65)],
    "cross": [("l", 20, 10, 10, 90, 90), ("l", 20, 90, 10, 10, 90)],
    "check": [("l", 18, 8, 55, 38, 85, 92, 18)],
    "arrow-right": [("r", 0, 38, 60, 62), ("p", 55, 12, 100, 50, 55, 88)],
    "arrow-left": [("r", 40, 38, 100, 62), ("p", 45, 12, 0, 50, 45, 88)],
    "arrow-up": [("r", 38, 40, 62, 100), ("p", 12, 45, 50, 0, 88, 45)],
    "arrow-down": [("r", 38, 0, 62, 60), ("p", 12, 55, 50, 100, 88, 55)],
    "sun": [("e", 26, 26, 74, 74), *_rays(12, 34, 49, 6)],
    "moon": [("e", 8, 4, 96, 92), ("E", 34, -4, 112, 74)],
    "cloud": [("e", 2, 44, 42, 84), ("e", 26, 22, 72, 68), ("e", 58, 40, 98, 84), ("r", 22, 60, 78, 84)],
    "rain": [("e", 2, 22, 42, 58), ("e", 26, 4, 72, 46), ("e", 58, 20, 98, 58), ("r", 22, 38, 78, 58), ("l", 6, 28, 68, 20, 92), ("l", 6, 52, 68, 44, 92), ("l", 6, 76, 68, 68, 92)],
    "bolt": [("p", 58, 0, 18, 56, 46, 56, 34, 100, 84, 38, 54, 38)],
    "drop": [("p", 50, 0, 80, 52, 20, 52), ("e", 18, 36, 82, 100)],
    "flame": [("p", 52, 0, 84, 48, 76, 40, 66, 24), ("e", 18, 36, 84, 100), ("p", 18, 62, 34, 22, 52, 50), ("E", 38, 64, 64, 92)],
    "leaf": [("p", 96, 4, 88, 56, 50, 86, 16, 84, 14, 50, 44, 16), ("l", 4, 6, 96, 60, 40)],
    "tree": [("p", 50, 0, 84, 40, 66, 40, 92, 76, 8, 76, 34, 40, 16, 40), ("r", 42, 76, 58, 100)],
    "flower": [("e", 34, 0, 66, 36), ("e", 34, 64, 66, 100), ("e", 0, 34, 36, 66), ("e", 64, 34, 100, 66), ("e", 8, 8, 40, 40), ("e", 60, 8, 92, 40), ("e", 8, 60, 40, 92), ("e", 60, 60, 92, 92), ("E", 34, 34, 66, 66), ("e", 40, 40, 60, 60)],
    "mountain": [("p", 0, 92, 36, 22, 54, 54, 70, 34, 100, 92)],
    "wave": [("l", 8, 0, 50, 12, 34, 25, 30, 38, 34, 50, 50, 62, 66, 75, 70, 88, 66, 100, 50)],
    "smile": [("e", 0, 0, 100, 100), ("E", 26, 28, 40, 46), ("E", 60, 28, 74, 46), ("L", 7, 24, 62, 36, 74, 50, 78, 64, 74, 76, 62)],
    "frown": [("e", 0, 0, 100, 100), ("E", 26, 28, 40, 46), ("E", 60, 28, 74, 46), ("L", 7, 24, 78, 36, 66, 50, 62, 64, 66, 76, 78)],
    "wink": [("e", 0, 0, 100, 100), ("L", 7, 24, 38, 40, 38), ("E", 60, 28, 74, 46), ("L", 7, 24, 62, 36, 74, 50, 78, 64, 74, 76, 62)],
    "skull": [("e", 12, 0, 88, 72), ("r", 30, 60, 70, 96), ("E", 24, 30, 44, 52), ("E", 56, 30, 76, 52), ("P", 50, 54, 44, 66, 56, 66), ("R", 39, 78, 43, 96), ("R", 57, 78, 61, 96), ("R", 48, 78, 52, 96)],
    "ghost": [("e", 14, 0, 86, 72), ("p", 14, 36, 86, 36, 86, 100, 74, 86, 62, 100, 50, 86, 38, 100, 26, 86, 14, 100), ("E", 30, 26, 44, 44), ("E", 56, 26, 70, 44)],
    "cat": [("e", 12, 26, 88, 94), ("p", 14, 44, 16, 2, 44, 28), ("p", 86, 44, 84, 2, 56, 28), ("E", 28, 48, 42, 62), ("E", 58, 48, 72, 62), ("P", 44, 68, 56, 68, 50, 76)],
    "fish": [("e", 4, 22, 76, 78), ("p", 66, 50, 100, 22, 100, 78), ("E", 18, 38, 28, 48)],
    "bird": [("e", 14, 28, 78, 82), ("e", 52, 12, 92, 52), ("p", 88, 28, 100, 34, 88, 40), ("p", 22, 56, 0, 40, 6, 78), ("E", 70, 24, 78, 32)],
    "crown": [("p", 0, 28, 25, 56, 50, 8, 75, 56, 100, 28, 90, 86, 10, 86)],
    "bell": [("e", 22, 8, 78, 64), ("p", 22, 36, 78, 36, 92, 80, 8, 80), ("e", 40, 78, 60, 98), ("r", 46, 0, 54, 12)],
    "gift": [("r", 6, 38, 94, 100), ("r", 0, 22, 100, 42), ("R", 44, 22, 56, 100), ("l", 6, 50, 22, 28, 4, 40, 22, 50, 22), ("l", 6, 50, 22, 72, 4, 60, 22, 50, 22)],
    "cake": [("r", 8, 50, 92, 94), ("r", 0, 92, 100, 100), ("R", 8, 66, 92, 72), ("r", 28, 26, 36, 50), ("r", 46, 26, 54, 50), ("r", 64, 26, 72, 50), ("e", 27, 12, 37, 26), ("e", 45, 12, 55, 26), ("e", 63, 12, 73, 26)],
    "balloon": [("e", 16, 0, 84, 78), ("p", 42, 76, 58, 76, 50, 86), ("l", 3, 50, 86, 44, 94, 54, 100)],
    "trophy": [("p", 22, 0, 78, 0, 74, 40, 58, 58, 42, 58, 26, 40), ("r", 45, 58, 55, 80), ("r", 26, 80, 74, 100), ("l", 6, 22, 8, 4, 8, 8, 34, 28, 40), ("l", 6, 78, 8, 96, 8, 92, 34, 72, 40)],
    "flag": [("r", 10, 0, 18, 100), ("p", 18, 4, 92, 4, 74, 28, 92, 52, 18, 52)],
    "shield": [("p", 50, 0, 92, 14, 92, 52, 72, 82, 50, 100, 28, 82, 8, 52, 8, 14)],
    "key": [("e", 0, 22, 50, 72), ("E", 14, 36, 36, 58), ("r", 46, 42, 100, 54), ("r", 74, 54, 84, 72), ("r", 90, 54, 100, 66)],
    "lock": [("r", 12, 44, 88, 100), ("e", 26, 0, 74, 60), ("E", 38, 12, 62, 56), ("r", 12, 44, 88, 60), ("E", 42, 62, 58, 78), ("R", 46, 72, 54, 90)],
    "mail": [("r", 0, 16, 100, 84), ("L", 6, 2, 20, 50, 56, 98, 20)],
    "house": [("p", 50, 2, 100, 50, 86, 50, 86, 98, 14, 98, 14, 50, 0, 50), ("R", 40, 62, 60, 98)],
    "rocket": [("p", 50, 0, 70, 30, 70, 74, 30, 74, 30, 30), ("p", 30, 48, 10, 80, 30, 74), ("p", 70, 48, 90, 80, 70, 74), ("p", 38, 74, 62, 74, 50, 100), ("E", 41, 28, 59, 46)],
    "coffee": [("r", 14, 36, 72, 92), ("e", 62, 44, 94, 76), ("E", 70, 52, 86, 68), ("r", 6, 92, 80, 100), ("l", 5, 30, 28, 34, 18, 28, 8), ("l", 5, 54, 28, 58, 18, 52, 8)],
    "music": [("e", 2, 68, 34, 96), ("e", 60, 58, 92, 86), ("r", 26, 14, 34, 82), ("r", 84, 4, 92, 72), ("p", 26, 14, 92, 4, 92, 24, 26, 34)],
    "eye": [("p", 0, 50, 22, 26, 50, 18, 78, 26, 100, 50, 78, 74, 50, 82, 22, 74), ("E", 28, 26, 72, 74), ("e", 38, 36, 62, 60)],
    "pin": [("e", 18, 0, 82, 64), ("p", 26, 48, 74, 48, 50, 100), ("E", 38, 20, 62, 44)],
    "spiral": [_spiral()],
    "infinity": [("l", 10, 50, 50, 36, 28, 18, 28, 6, 50, 18, 72, 36, 72, 50, 50, 64, 28, 82, 28, 94, 50, 82, 72, 64, 72, 50, 50)],
}


def figure_mask(name: str, width: int, height: int) -> Image.Image:
    """A mode "1" mask. Figures keep their proportions and are centered in the box."""
    side = min(width, height)
    scale = side / 100
    dx, dy = (width - side) / 2, (height - side) / 2
    mask = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(mask)

    def at(coords) -> list[tuple[float, float]]:
        return [(dx + coords[i] * scale, dy + coords[i + 1] * scale) for i in range(0, len(coords), 2)]

    for step in FIGURES[name]:
        kind, args = step[0], step[1:]
        value = 1 if kind.islower() else 0
        lower = kind.lower()
        if lower == "e":
            draw.ellipse([*at(args[:2])[0], *at(args[2:4])[0]], fill=value)
        elif lower == "r":
            draw.rectangle([*at(args[:2])[0], *at(args[2:4])[0]], fill=value)
        elif lower == "p":
            draw.polygon(at(args), fill=value)
        elif lower == "l":
            points = at(args[1:])
            line_width = max(1, round(args[0] * scale))
            draw.line(points, fill=value, width=line_width, joint="curve")
            for x, y in (points[0], points[-1]):
                r = line_width / 2
                draw.ellipse([x - r, y - r, x + r, y + r], fill=value)
    return mask
