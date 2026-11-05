"""Prototype poster kit. Pure Python and Pillow, the same stack the project already has."""
from __future__ import annotations

import math
import random
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

W, H = 312, 216
SUP = Path("/System/Library/Fonts/Supplemental")
SYS = Path("/System/Library/Fonts")

FONTS = {
    "impact": (SUP / "Impact.ttf", None),
    "din": (SUP / "DIN Condensed Bold.ttf", None),
    "dina": (SUP / "DIN Alternate Bold.ttf", None),
    "futura": (SUP / "Futura.ttc", "Bold"),
    "futura-med": (SUP / "Futura.ttc", "Medium"),
    "futura-xb": (SUP / "Futura.ttc", "Condensed ExtraBold"),
    "didot": (SUP / "Didot.ttc", "Bold"),
    "didot-reg": (SUP / "Didot.ttc", "Regular"),
    "didot-it": (SUP / "Didot.ttc", "Italic"),
    "hoefler-it": (SUP / "Hoefler Text.ttc", "Italic"),
    "bodoni": (SUP / "Bodoni 72.ttc", "Bold"),
    "rockwell": (SUP / "Rockwell.ttc", "Bold"),
    "phosphate": (SUP / "Phosphate.ttc", "Inline"),
    "phosphate-s": (SUP / "Phosphate.ttc", "Solid"),
    "krung": (SUP / "Krungthep.ttf", None),
    "silom": (SUP / "Silom.ttf", None),
    "black": (SUP / "Arial Black.ttf", None),
    "courier": (SUP / "Courier New Bold.ttf", None),
    "georgia": (SUP / "Georgia Bold.ttf", None),
    "chalk": (SUP / "Chalkduster.ttf", None),
    "typewriter": (SYS / "Supplemental/AmericanTypewriter.ttc", "Bold"),
    "snell": (SUP / "SnellRoundhand.ttc", "Bold"),
    "menlo": (SYS / "Menlo.ttc", "Bold"),
    "helv": (SYS / "Helvetica.ttc", "Bold"),
    "avenir-c": (SYS / "Avenir Next Condensed.ttc", "Heavy"),
    "marker": (SUP / "MarkerFelt.ttc", "Wide"),
}


@lru_cache(maxsize=256)
def font(name: str, size: int) -> ImageFont.FreeTypeFont:
    path, style = FONTS[name]
    if not path.exists():
        for alt in (SUP / path.name, SYS / path.name):
            if alt.exists():
                path = alt
    if style is None:
        return ImageFont.truetype(str(path), size)
    for index in range(32):
        try:
            face = ImageFont.truetype(str(path), size, index=index)
        except OSError:
            break
        if face.getname()[1] == style:
            return face
    return ImageFont.truetype(str(path), size)


def blank(value: int = 255) -> Image.Image:
    return Image.new("L", (W, H), value)


def word(text: str, name: str, w: int | None = None, h: int | None = None, tracking: float = 0, thresh: int = 118) -> Image.Image:
    """Mask of the text's INK, sized exactly. Rendered big and reduced, so outlines stay clean."""
    big = font(name, 300)
    probe = Image.new("L", (2400 + len(text) * 300, 700), 0)
    d = ImageDraw.Draw(probe)
    if tracking:
        x = 40
        for ch in text:
            d.text((x, 120), ch, font=big, fill=255)
            x += big.getlength(ch) + tracking * 300
    else:
        d.text((40, 120), text, font=big, fill=255)
    box = probe.getbbox()
    ink = probe.crop(box)
    ratio = ink.width / ink.height
    if w and not h:
        h = max(1, round(w / ratio))
    elif h and not w:
        w = max(1, round(h * ratio))
    small = ink.resize((w, h), Image.LANCZOS)
    return small.point(lambda v: 255 if v >= thresh else 0)


def line(text: str, name: str, size: int, tracking: int = 0) -> Image.Image:
    """Small text at its natural size, hinted straight to pixels, for captions."""
    f = font(name, size)
    width = int(sum(f.getlength(c) + tracking for c in text)) + 4
    im = Image.new("L", (width, size * 2), 0)
    d = ImageDraw.Draw(im)
    d.fontmode = "1"
    x = 1
    for ch in text:
        d.text((x, 2), ch, font=f, fill=255)
        x += f.getlength(ch) + tracking
    return im.crop(im.getbbox())


def stamp(canvas: Image.Image, mask: Image.Image, x: int, y: int, ink: int = 0) -> None:
    canvas.paste(ink, (int(x), int(y)), mask)


def xor_stamp(canvas: Image.Image, mask: Image.Image, x: int, y: int) -> None:
    layer = Image.new("L", (W, H), 0)
    layer.paste(255, (int(x), int(y)), mask)
    canvas.paste(ImageChops.invert(canvas), (0, 0), layer)


BAYER = [
    [0, 32, 8, 40, 2, 34, 10, 42],
    [48, 16, 56, 24, 50, 18, 58, 26],
    [12, 44, 4, 36, 14, 46, 6, 38],
    [60, 28, 52, 20, 62, 30, 54, 22],
    [3, 35, 11, 43, 1, 33, 9, 41],
    [51, 19, 59, 27, 49, 17, 57, 25],
    [15, 47, 7, 39, 13, 45, 5, 37],
    [63, 31, 55, 23, 61, 29, 53, 21],
]


def bayer(gray: Image.Image) -> Image.Image:
    px = gray.tobytes()
    w, h = gray.size
    out = bytearray(w * h)
    for y in range(h):
        row = BAYER[y % 8]
        for x in range(w):
            out[y * w + x] = 255 if px[y * w + x] / 255 > (row[x % 8] + 0.5) / 64 else 0
    return Image.frombytes("L", (w, h), bytes(out))


def atkinson(gray: Image.Image) -> Image.Image:
    w, h = gray.size
    v = [float(p) for p in gray.tobytes()]
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            i = y * w + x
            new = 255.0 if v[i] >= 128 else 0.0
            out[i] = int(new)
            e = (v[i] - new) / 8
            for dx, dy in ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and ny < h:
                    v[ny * w + nx] += e
    return Image.frombytes("L", (w, h), bytes(out))


def tone(fn, w: int = W, h: int = H) -> Image.Image:
    """fn(x, y) -> 0..1 brightness, as a grayscale image."""
    return Image.frombytes("L", (w, h), bytes(max(0, min(255, int(fn(x, y) * 255))) for y in range(h) for x in range(w)))


def halftone(fn, cell: float = 7, angle: float = 45, w: int = W, h: int = H) -> Image.Image:
    """fn(x, y) -> darkness 0..1. Round dots on a rotated screen, as in real print."""
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            u, v = (x * ca + y * sa) / cell, (-x * sa + y * ca) / cell
            fu, fv = u - math.floor(u) - 0.5, v - math.floor(v) - 0.5
            cx, cy = (math.floor(u) + 0.5) * cell, (math.floor(v) + 0.5) * cell
            sx, sy = cx * ca - cy * sa, cx * sa + cy * ca
            dark = max(0.0, min(1.0, fn(sx, sy)))
            radius = math.sqrt(dark) * 0.76
            out[y * w + x] = 0 if fu * fu + fv * fv < radius * radius else 255
    return Image.frombytes("L", (w, h), bytes(out))


def clip(fill: Image.Image, mask: Image.Image, canvas: Image.Image, x: int = 0, y: int = 0) -> None:
    layer = Image.new("L", (W, H), 0)
    layer.paste(mask, (int(x), int(y)))
    canvas.paste(fill, (0, 0), layer)


def finish(canvas: Image.Image) -> Image.Image:
    return canvas.point(lambda v: 255 if v >= 128 else 0).convert("1", dither=Image.NONE)


def blur(mask: Image.Image, r: float) -> Image.Image:
    return mask.filter(ImageFilter.GaussianBlur(r))


def rng(seed) -> random.Random:
    return random.Random(seed)


def stroke(draw: ImageDraw.ImageDraw, pts, width: int, fill: int) -> None:
    draw.line(pts, fill=fill, width=width, joint="curve")
    r = width / 2
    for x, y in (pts[0], pts[-1]):
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)
