"""Posters: a small model says what a note means, and this module does the designing.

A model drawing by coordinates, at low effort, with no look at its result, produces a frame, an
icon and some text. So the model only fills in meaning (`say`, `sub`, `big`, `pic`, `data`,
`items`) and may name a `look`. Every look takes the same fields, solves its own layout for
whatever text arrives, and never loses any of it. If a look can't hold the text legibly it
hands over to one that can, and the report says so.

A look is a way of designing, not a template: type is sized from the words themselves, pictures
come from any subject, and the seed varies composition and detail.
"""

from __future__ import annotations

import hashlib
import io
import json
import math
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter

from . import craft
from .craft import H, W, caption, paste, smallest, stack, word

MAX_INK = 0.59  # The label maker asks for at most 60% black, for the sake of the print head.
MIN_CAP = 11    # Capital height of 16 px text, the smallest that prints legibly.
_MAX_TEXT = 400


class _NoFit(Exception):
    """This look can't hold this content legibly. The next best look gets to try."""


@dataclass
class Spec:
    look: str = ""
    say: str = ""
    lines: Optional[list[str]] = None  # Line breaks, when the model chose them.
    sub: str = ""
    big: str = ""
    pic: str = ""
    data: list[float] = field(default_factory=list)
    items: list[str] = field(default_factory=list)
    qr: str = ""
    seed: int = 0
    sender: str = ""  # From the connector or the device's owner. Never from the model.
    date: str = ""

    def rng(self) -> random.Random:
        key = json.dumps([self.say, self.sub, self.big, self.seed], ensure_ascii=False)
        return random.Random(hashlib.sha256(key.encode()).hexdigest())


@dataclass
class Report:
    look: str
    alternatives: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    shown: list[str] = field(default_factory=list)
    min_cap: int = 999

    def summary(self) -> str:
        text = f"Drew look {self.look}."
        if self.alternatives:
            text += f" Also fits: {', '.join(self.alternatives)}."
        return " ".join([text, *self.warnings])


class _Page:
    """The canvas, plus a record of what text went on it and how small."""

    def __init__(self, report: Report, value: int = 255) -> None:
        self.image = Image.new("L", (W, H), value)
        self.draw = ImageDraw.Draw(self.image)
        self.report = report

    def text(self, mask: Image.Image, x: float, y: float, source: str, ink: int = 0) -> None:
        paste(self.image, mask, x, y, ink)
        self.mark(source, mask.height)

    def mark(self, source: str, height: int) -> None:
        self.report.shown.append(source)
        self.report.min_cap = min(self.report.min_cap, height)

    def stack(self, lines: list[str], face: str, x: int, y: int, width: int, height: int, gap: int = 6, ink: int = 0, center: bool = True, stretch: float = 1.6) -> int:
        """Sets lines full width. Returns the y just past the last one."""
        masks = stack(lines, face, width, height, gap, stretch)
        if smallest(masks) < MIN_CAP:
            raise _NoFit
        total = sum(m.height for m in masks) + gap * (len(masks) - 1)
        top = y + ((height - total) // 2 if center else 0)
        for line, mask in zip(lines, masks):
            self.text(mask, x + (width - mask.width) // 2, top, line, ink)
            top += mask.height + gap
        return top - gap

    def fit_line(self, text: str, face: str, x: int, y: int, width: int, height: int, ink: int = 0, align: str = "l") -> int:
        """One line, as large as fits the box. Returns its height. Too small to read raises _NoFit."""
        ratio = craft.aspect(text, face)
        h = min(height, round(width / max(0.05, ratio)))
        if h < MIN_CAP:
            raise _NoFit
        mask = word(text, face, w=min(width, round(h * ratio)), h=h)
        left = {"l": x, "c": x + (width - mask.width) // 2, "r": x + width - mask.width}[align]
        self.text(mask, left, y, text, ink)
        return mask.height

    def block_text(self, text: str, face: str, x: int, y: int, width: int, height: int, ink: int = 0, gap: int = 5) -> int:
        """Words filling a box left aligned at a size that fits, wrapping as needed. Returns the bottom."""
        if not text:
            return y
        for size in (26, 22, 18, craft.MIN_TEXT_PX):
            lines = craft.wrap_caption(text, width, face, size)
            total = sum(m.height for m in lines) + gap * (len(lines) - 1)
            if total <= height:
                break
        else:
            raise _NoFit
        for line in lines:
            self.text(line, x, y, text, ink)
            y += line.height + gap
        return y - gap


# --- reading the fields -------------------------------------------------------------------


def _string(value: Any) -> str:
    return " ".join(str(value).split())[:_MAX_TEXT] if value not in (None, "") else ""


def parse(op: dict) -> Spec:
    """Forgiving by design: a small model's odd arguments still make a note. Sender is not read here."""
    raw_say = op.get("say", op.get("s", ""))
    lines = None
    if isinstance(raw_say, list):
        lines = [_string(line) for line in raw_say if _string(line)][:8]
        say = " ".join(lines)
    else:
        say = _string(raw_say)
    data: list[float] = []
    if isinstance(op.get("data"), list):
        for value in op["data"][:64]:
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            if math.isfinite(number):
                data.append(number)
    raw_items = op.get("items")
    items = [_string(item) for item in raw_items if _string(item)][:12] if isinstance(raw_items, list) else []
    try:
        seed = int(op.get("seed") or 0)
    except (TypeError, ValueError):
        seed = 0
    return Spec(
        look=_string(op.get("look")).lower(), say=say, lines=lines, sub=_string(op.get("sub")),
        big=_string(op.get("big"))[:12], pic=_string(op.get("pic"))[:40], data=data, items=items,
        qr=str(op.get("qr") or "")[:300], seed=seed, date=_string(op.get("date")),
    )


_EMOJI = re.compile("[\U0001F000-\U0001FAFF\u2600-\u27BF\u2B00-\u2BFF\uFE0F\u200D]+")


def _move_emoji(spec: Spec) -> None:
    found = _EMOJI.findall(f"{spec.say} {spec.sub}")
    if not found:
        return
    if not spec.pic:
        spec.pic = found[0]
    spec.say, spec.sub = " ".join(_EMOJI.sub(" ", spec.say).split()), " ".join(_EMOJI.sub(" ", spec.sub).split())
    spec.lines = None


_NUMBER = re.compile(r"\d{1,2}[:.]\d{2}|\d+(?:[.,]\d+)?%?")


def _pull_number(spec: Spec) -> str:
    """The number the note is about. Takes it out of `say` so it isn't printed twice."""
    if spec.big:
        return spec.big
    match = _NUMBER.search(spec.say)
    if not match or len(match.group()) > 6:
        return ""
    big = match.group()
    spec.say = " ".join((spec.say[:match.start()] + " " + spec.say[match.end():]).split())
    spec.lines = None
    return big


def _lines_for(spec: Spec, text: str, face: str, width: int, height: int, gap: int = 6, most: int = 6) -> list[str]:
    if spec.lines and " ".join(spec.lines) == spec.say and text.upper() == spec.say.upper():
        return [line.upper() if text.isupper() else line for line in spec.lines]
    return craft.break_lines(text, face, width, height, gap, most)


def _display(spec: Spec) -> str:
    """Display faces read best in capitals. `upper` also gets ß and Ø right."""
    text = spec.say or spec.big
    if not text:
        raise _NoFit
    return text.upper()


def _picture(spec: Spec, width: int, height: int, default: str = "") -> Optional[tuple[Image.Image, Image.Image]]:
    found = craft.resolve_picture(spec.pic or default, max(width, height) * 2)
    if found is None:
        return None
    gray, mask = found
    return craft.fit(gray, width, height), craft.fit(mask, width, height).point(lambda v: 255 if v >= 128 else 0)


def _footer(page: _Page, spec: Spec, x: int, y: int, width: int, height: int, ink: int = 0) -> None:
    """The small line. Set as large as it fits, wrapping when it needs to."""
    if not spec.sub:
        return
    if height >= MIN_CAP and craft.aspect(spec.sub, "din") * min(height, 26) <= width * 1.35:
        h = min(height, 26, round(width / max(0.05, craft.aspect(spec.sub, "din"))))
        if h >= MIN_CAP:
            mask = word(spec.sub, "din", w=min(width, round(h * craft.aspect(spec.sub, "din"))), h=h)
            page.text(mask, x, y + (height - mask.height) // 2, spec.sub, ink)
            return
    page.block_text(spec.sub, "din", x, y, width, height, ink)


# --- the looks ----------------------------------------------------------------------------


def _block(page: _Page, spec: Spec, alarm: bool = False) -> None:
    """Every line set to the full measure, with one reversed out of a black band."""
    draw, rng = page.draw, spec.rng()
    margin = 8
    top = 0
    if alarm:
        hazard = craft.tone(lambda x, y: 1 if (x + y) % 28 < 14 else 0, W, 14)
        page.image.paste(hazard, (0, 0))
        draw.rectangle([0, H - 6, W, H], fill=0)
        top = 20
    bottom = H - (10 if alarm else 8)
    if spec.sub:
        sub_h = 25
        if craft.aspect(spec.sub, "din") * sub_h > W - margin * 2 and craft.aspect(spec.sub, "din") * MIN_CAP > W - margin * 2:
            sub_h = 46  # A long line wraps to two.
        _footer(page, spec, margin, bottom - sub_h, W - margin * 2, sub_h)
        bottom -= sub_h + 8
    area = bottom - top
    text = _display(spec)
    lines = _lines_for(spec, text, "impact", W - margin * 2, area - 12, 12, most=5)
    masks = stack(lines, "impact", W - margin * 2, area - 12 * len(lines), 12, stretch=1.7)
    if smallest(masks) < MIN_CAP * 2 and len(text) > 40:
        raise _NoFit
    if smallest(masks) < MIN_CAP:
        raise _NoFit
    reverse = len(lines) - 1 if len(lines) < 3 else rng.randrange(1, len(lines))
    room = area - sum(m.height for m in masks)
    gap = max(6, min(16, room // len(lines)))
    y = top + (area - sum(m.height for m in masks) - gap * (len(lines) - 1)) // 2
    if len(lines) == 1:  # One line is all band, up to the height that keeps the ink safe.
        band = min(area, masks[0].height + 24, 136)
        y = top + (area - band) // 2
        draw.rectangle([0, y, W, y + band - 1], fill=0)
        y += (band - masks[0].height) // 2
    for index, (line, mask) in enumerate(zip(lines, masks)):
        reversed_line = len(lines) == 1 or index == reverse
        if reversed_line and len(lines) > 1:
            draw.rectangle([0, y - gap // 2, W, y + mask.height + gap // 2 - 1], fill=0)
        page.text(mask, (W - mask.width) // 2, y, line, 255 if reversed_line else 0)
        y += mask.height + gap


def _alarm(page: _Page, spec: Spec) -> None:
    _block(page, spec, alarm=True)


def _relief(page: _Page, spec: Spec) -> None:
    """A word lifts out of ruled lines. Nothing draws it: only a height map knows it is there."""
    text = _display(spec)
    if len(text) > 16:
        raise _NoFit
    strip = 34 if spec.sub else 0
    area = H - strip - 36
    lines = _lines_for(spec, text, "impact", 284, area, 8, most=2)
    if len(lines) > 2:
        raise _NoFit
    source = Image.new("L", (W, H), 0)
    masks = stack(lines, "impact", 284, area, 8, stretch=1.9)
    if smallest(masks) < 28:  # Stripes eat fine detail, so this look only suits big type.
        raise _NoFit
    total = sum(m.height for m in masks) + 8 * (len(masks) - 1)
    y = 22 + (area - total) // 2
    for line, mask in zip(lines, masks):
        source.paste(mask, ((W - mask.width) // 2, y))
        page.mark(line, mask.height)
        y += mask.height + 8
    height = source.filter(ImageFilter.GaussianBlur(1.3)).load()
    image = page.image
    image.paste(0, (0, 0, W, H))
    draw = ImageDraw.Draw(image)
    for row in range(4, H + 16, 4):
        sample = min(H - 1, row)
        points = [(x, row - height[min(W - 1, max(0, x)), sample] / 255 * 11) for x in range(-1, W + 2)]
        draw.polygon(points + [(W + 2, H + 20), (-1, H + 20)], fill=0)
        for x in range(W):
            draw.line([(x, points[x + 1][1]), (x + 1, points[x + 2][1])], fill=255, width=3 if height[x, sample] > 120 else 1)
    if strip:
        draw.rectangle([0, H - strip, W, H], fill=255)
        _footer(page, spec, 12, H - strip + 6, W - 24, strip - 12)


def _monument(page: _Page, spec: Spec) -> None:
    """Solid type receding to a vanishing point, under rays. Depth is free once the engine owns it."""
    rng = spec.rng()
    if spec.big and spec.big.casefold() not in spec.say.casefold():
        spec.say, spec.big = f"{spec.big} {spec.say}".strip(), ""
        spec.lines = None
    text = _display(spec)
    if len(text) > 26:
        raise _NoFit
    vp = (rng.randrange(120, 192), 18)
    base = craft.bayer(craft.tone(lambda x, y: 0.7 if (math.atan2(y - vp[1], x - vp[0]) * 28 / math.pi) % 2 < 1 else 1.0))
    page.image.paste(base)
    area = 112
    lines = _lines_for(spec, text, "impact", 292, area, 6, most=2)
    masks = stack(lines, "impact", 292, area, 6, stretch=1.7)
    if smallest(masks) < 30:
        raise _NoFit
    face = Image.new("L", (W, H), 0)
    y = H - 8 - sum(m.height for m in masks) - 6 * (len(masks) - 1)
    for line, mask in zip(lines, masks):
        face.paste(mask, ((W - mask.width) // 2, y))
        page.mark(line, mask.height)
        y += mask.height + 6
    for depth in range(62, 0, -1):
        scale = 1 - depth * 0.0098
        size = (max(1, round(W * scale)), max(1, round(H * scale)))
        shrunk = face.resize(size, Image.NEAREST)
        layer = Image.new("L", (W, H), 0)
        layer.paste(shrunk, (round(vp[0] - vp[0] * scale), round(vp[1] - vp[1] * scale)))
        page.image.paste(0 if depth % 20 else 255, (0, 0), layer)
    page.image.paste(0, (0, 0), face.filter(ImageFilter.MaxFilter(5)))
    page.image.paste(255, (0, 0), face)
    if spec.sub:
        lines_sub = craft.wrap_caption(spec.sub, 280, "din", 18)
        height = sum(m.height + 4 for m in lines_sub) + 8
        page.draw.rectangle([0, 0, W, height], fill=255)
        y = 6
        for mask in lines_sub:
            page.text(mask, (W - mask.width) // 2, y, spec.sub)
            y += mask.height + 4


_RANSOM_FACES = ("impact", "didot", "rockwell", "courier", "futura", "typewriter", "black", "bodoni", "krungthep", "georgia")


def _ransom(page: _Page, spec: Spec) -> None:
    """Every letter cut from a different page."""
    rng = spec.rng()
    text = _display(spec)
    if len(text) > 28:
        raise _NoFit
    page.image.paste(craft.bayer(craft.tone(lambda x, y: 0.93)))
    strip = 28 if spec.sub else 0
    available = H - strip - 10
    words = text.split()
    best: list[str] = []
    for rows in (1, 2, 3, 4):
        if rows > len(words):
            break
        candidate = _even_rows(words, rows)
        if not best or _tile_size(candidate, available) > _tile_size(best, available):
            best = candidate
    size = _tile_size(best, available)
    if size < 26:
        raise _NoFit
    faces = list(_RANSOM_FACES)
    rng.shuffle(faces)
    total = len(best) * size + (len(best) - 1) * 4
    y = 5 + (available - total) // 2
    index = 0
    for row in best:
        widths = [round(size * rng.uniform(0.84, 1.02)) if c != " " else size // 3 for c in row]
        fitted = min(1.0, (W - 12 - (len(row) - 1) * 3) / max(1, sum(widths)))
        widths = [max(10, int(w * fitted)) for w in widths]
        x = (W - sum(widths) - 3 * (len(row) - 1)) // 2
        for char, width in zip(row, widths):
            if char != " ":
                _tile(page, char, faces[index % len(faces)], x, y + rng.randint(-2, 2), width, size, rng)
                index += 1
            x += width + 3
        y += size + 4
        page.mark(row, size // 2)
    if strip:
        page.draw.rectangle([0, H - strip, W, H], fill=255)
        _footer(page, spec, 10, H - strip + 5, W - 20, strip - 10)


def _even_rows(words: list[str], rows: int) -> list[str]:
    """Greedy rows whose lengths are as close as possible."""
    target = sum(len(w) for w in words) / rows
    out: list[str] = []
    current = ""
    for i, item in enumerate(words):
        remaining_rows = rows - len(out) - 1
        words_left = len(words) - i
        if current and (len(current) + 1 + len(item) > target * 1.25 or words_left <= remaining_rows) and remaining_rows > 0:
            out.append(current)
            current = item
        else:
            current = f"{current} {item}".strip()
    out.append(current)
    return out


def _tile_size(rows: list[str], available: int) -> int:
    by_height = (available - (len(rows) - 1) * 4) // len(rows)
    by_width = min((W - 12 - (len(r) - 1) * 3) / max(0.3, sum(0.93 if c != " " else 0.33 for c in r)) for r in rows)
    return int(min(by_height, by_width, 76))


def _tile(page: _Page, char: str, face: str, x: int, y: int, w: int, h: int, rng: random.Random) -> None:
    style = rng.choice(("black", "white", "white", "black", "gray"))
    tile = Image.new("L", (w, h), 0 if style == "black" else 255)
    if style == "gray":
        tile = craft.bayer(craft.tone(lambda a, b: 0.62, w, h))
    drawing = ImageDraw.Draw(tile)
    drawing.rectangle([0, 0, w - 1, h - 1], outline=0)
    glyph = word(char, face, h=max(8, int(h * rng.uniform(0.62, 0.78))))
    if glyph.width > w - 8:
        glyph = word(char, face, w=max(4, w - 8))
    if style == "gray":
        drawing.rectangle([4, 4, w - 5, h - 5], fill=255)
    tile.paste(255 if style == "black" else 0, ((w - glyph.width) // 2, (h - glyph.height) // 2), glyph)
    angle = rng.uniform(-7, 7)
    pad = 12
    big = Image.new("L", (w + pad * 2, h + pad * 2), 255)
    alpha = Image.new("L", big.size, 0)
    big.paste(tile, (pad, pad))
    alpha.paste(255, (pad, pad, pad + w, pad + h))
    turned, turned_alpha = big.rotate(angle, Image.NEAREST), alpha.rotate(angle, Image.NEAREST)
    page.image.paste(0, (x + 3 - pad, y + 3 - pad), turned_alpha)
    page.image.paste(turned, (x - pad, y - pad), turned_alpha)


def _numeral(page: _Page, spec: Spec) -> None:
    """One number, set absurdly large in a high-contrast face, printed through a halftone screen."""
    big = _pull_number(spec)
    if not big:
        raise _NoFit
    screen = craft.halftone(craft.tone(lambda x, y: 1 - (0.42 + 0.72 * min(1.0, y / 210))), cell=5)
    words = spec.say
    if len(big) <= 2:
        ratio = craft.aspect(big, "bodoni")
        height = 236 if len(big) == 1 else 200
        width = min(round(height * ratio), 186)
        height = round(width / ratio)
        mask = word(big, "bodoni", w=width, h=height)
        craft.fill_mask(page.image, screen, mask, 2 if len(big) == 2 else 4, (H - height) // 2)
        page.mark(big, height)
        left = width + 16
        room = W - left - 10
        foot = 26 if spec.sub else 0
        if words:
            lines = _lines_for(spec, words, "didot-italic", room, H - 40 - foot, 12, most=4)
            masks = [word(line, "didot-italic", w=room, heavy=True) for line in lines]
            if smallest(masks) < MIN_CAP or sum(m.height for m in masks) + 12 * len(masks) > H - 24 - foot:
                masks = stack(lines, "didot-italic", room, H - 40 - foot, 12)
                if smallest(masks) < MIN_CAP:
                    raise _NoFit
            y = 20
            for i, (line, m) in enumerate(zip(lines, masks)):
                page.text(m, left, y, line)
                y += m.height + 6
                if i < len(lines) - 1:
                    page.draw.rectangle([left, y, W - 10, y + 1], fill=0)
                    y += 8
        if spec.sub:
            _footer(page, spec, left, H - foot - 8, room, foot)
    else:
        mask = word(big, "bodoni", w=296, h=112 if words or spec.sub else 196)
        craft.fill_mask(page.image, screen, mask, 8, 8)
        page.mark(big, mask.height)
        y = 8 + mask.height + 8
        room = H - y - 8
        foot = 24 if spec.sub else 0
        if words:
            page.fit_line(words, "didot-italic", 8, y, 296, room - foot - (4 if foot else 0))
        if spec.sub:
            _footer(page, spec, 8, H - foot - 6, 296, foot)


def _collide(page: _Page, spec: Spec) -> None:
    """Two shapes and a numeral, overlapped with XOR. The overlap does the design."""
    big = _pull_number(spec)
    if not big:
        raise _NoFit
    draw = page.draw
    tail = ""
    match = re.fullmatch(r"(\d{1,2})([:.]\d{2})", big)
    if match:
        big, tail = match.group(1), match.group(2)
    draw.ellipse([-66, -2, 152, 218], fill=0)
    if tail or spec.sub:
        draw.rectangle([226, 108, W, H], fill=0)
        draw.pieslice([226, 66, W, 150], 180, 360, fill=0)
    width = min(196, round(122 * craft.aspect(big, "futura")))
    number = word(big, "futura", w=width)
    if number.height > 150:
        number = word(big, "futura", h=150)
    craft.xor(page.image, number, 14, (H - number.height) // 2)
    page.mark(big, number.height)
    heading = spec.say
    if heading:
        room = 44 if tail or spec.sub else 120
        lines = _lines_for(spec, heading.upper(), "futura", 84, room, 4, most=4)
        masks = stack(lines, "futura", 84, room, 4, stretch=1.3)
        if smallest(masks) < MIN_CAP:
            raise _NoFit
        y = 12
        for line, mask in zip(lines, masks):
            page.text(mask, 222, y, line)
            y += mask.height + 4
    y = 118
    if tail:
        mask = word(tail, "futura", w=68)
        page.text(mask, 235, y, tail, 255)
        y += mask.height + 10
    if spec.sub:
        page.block_text(spec.sub, "din", 234, y, 72, H - y - 6, 255, gap=3)


def _moon(size: int, seed: random.Random) -> tuple[Image.Image, Image.Image]:
    """A lit sphere with craters, in copperplate lines. Returned as (one-bit drawing, mask)."""
    radius = size / 2
    craters = [(seed.uniform(-0.9, 0.9), seed.uniform(-0.9, 0.9), seed.uniform(0.05, 0.2)) for _ in range(26)]
    craters = [c for c in craters if c[0] ** 2 + c[1] ** 2 < 0.9]
    lx, ly, lz = -0.62, -0.46, 0.63
    tilt = math.radians(-24)
    ct, st = math.cos(tilt), math.sin(tilt)
    out = bytearray(size * size)
    for y in range(size):
        for x in range(size):
            u, v = (x - radius) / radius, (y - radius) / radius
            d2 = u * u + v * v
            if d2 >= 1:
                continue
            nz = math.sqrt(1 - d2)
            nx, ny = u, v
            albedo = 1.0
            for cu, cv, cr in craters:
                du, dv = u - cu, v - cv
                dist = math.sqrt(du * du + dv * dv)
                if dist < cr * 1.25:
                    t = dist / cr
                    slope = 0.75 * (1 - t) if t < 1 else -1.6 * (t - 1)
                    if dist > 1e-4:
                        nx -= du / dist * slope * 0.8
                        ny -= dv / dist * slope * 0.8
                    if t < 0.9:
                        albedo *= 0.82
            if math.sin(u * 3.1 + v * 1.7 + 1.0) + math.sin(v * 4.3 - u * 1.1) * 0.7 > 0.75:
                albedo *= 0.72
            length = math.sqrt(nx * nx + ny * ny + nz * nz)
            lambert = max(0.0, (nx * lx + ny * ly + nz * lz) / length)
            bright = min(1.0, 0.1 + lambert ** 0.82 * albedo * 1.15)
            ru, rv = u * ct - v * st, u * st + v * ct
            lat = math.asin(max(-1.0, min(1.0, rv))) / (math.pi / 2)
            lon = ru / max(0.05, math.sqrt(1 - rv * rv))
            phase = (lat * 25 * size / 192 + 0.12 * math.sin(lon * 7)) % 1
            out[y * size + x] = 0 if abs(phase - 0.5) < 0.5 * (1 - bright) ** 0.8 * 1.02 else 255
    drawing = Image.frombytes("L", (size, size), bytes(out))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse([0, 0, size - 1, size - 1], fill=255)
    return drawing, mask


_SPHERES = {"moon", "🌙", "🌕", "🌑", "🌝", "🌚", "🌛", "🌜", "planet", "ball"}
_NIGHT = re.compile(r"\b(good ?night|night|natt|god natt|sleep\w*|moon|sove|dreams?|bedtime)\b", re.I)


def _engraving(page: _Page, spec: Spec) -> None:
    """Elegant words beside a subject drawn in swelling lines, like a banknote. Black, with stars."""
    rng = spec.rng()
    subject = spec.pic.lower() or ("moon" if _NIGHT.search(spec.say + " " + spec.sub) else "")
    if not subject:
        raise _NoFit
    dusk = craft.bayer(craft.tone(lambda x, y: min(0.5, max(0.0, (x - 118) / 420 + (y - 40) / 420))))
    page.image.paste(dusk)
    pixels = page.image.load()
    for _ in range(90):
        pixels[rng.randrange(W), rng.randrange(H)] = 255
    picture_left = 118
    if subject in _SPHERES:
        size = 192
        drawing, mask = _moon(size, rng)
        page.image.paste(drawing, (picture_left + 2, 8), mask)
    else:
        found = _picture(spec, 186, 196)
        if found is None:
            raise _NoFit
        gray, mask = found
        lifted = gray.point(lambda v: 95 + v * 160 // 255)  # Lines on black need more light to read.
        drawing = craft.engrave(lifted, spacing=3.4, wobble=craft.inflate(mask))
        page.image.paste(drawing, (picture_left + (190 - gray.width) // 2, (H - gray.height) // 2), mask)
    # Clear a little night around the words, so the stars never touch the letters.
    page.draw.rectangle([0, 0, picture_left - 1, H], fill=0)
    foot = 30 if spec.sub else 0
    text = spec.say
    if not text:
        raise _NoFit
    area = H - 28 - foot
    lines = _lines_for(spec, text, "didot-italic", 104, area, 10, most=4)
    masks = [word(line, "didot-italic", w=104, heavy=True) for line in lines]
    if sum(m.height for m in masks) + 10 * (len(masks) - 1) > area:
        masks = stack(lines, "didot-italic", 104, area, 8)
    if smallest(masks) < MIN_CAP:
        raise _NoFit
    y = 14
    for line, mask in zip(lines, masks):
        page.text(mask, 10, y, line, 255)
        y += mask.height + 10
    if spec.sub:
        lines_sub = craft.wrap_caption(spec.sub, 104, "din", 18)
        y = H - 8 - sum(m.height + 3 for m in lines_sub)
        for mask in lines_sub:
            page.text(mask, 10, y, spec.sub, 255)
            y += mask.height + 3


def _stage(page: _Page, spec: Spec) -> None:
    """A real ray trace: checkered floor, black sky, and a mirror ball or any subject on stage."""
    found = _picture(spec, 150, 130) if spec.pic else None
    scale = 2
    width, height = W * scale, H * scale
    cam = (0.0, 1.5, -4.8)
    ball = (1.15, 1.2, -1.0)
    radius = 1.2 if found is None else 0.0
    sun = (-0.55, 0.75, -0.4)
    norm = math.sqrt(sum(v * v for v in sun))
    sun = tuple(v / norm for v in sun)

    def floor(px: float, pz: float) -> float:
        check = (math.floor(px * 0.95) + math.floor(pz * 0.95)) % 2
        base = 0.96 if check else 0.03
        dx, dz = px - ball[0] - 0.55, pz - ball[2] - 0.2
        distance = math.sqrt(dx * dx + dz * dz * 0.7)
        base *= 0.08 + 0.92 * min(1.0, max(0.0, (distance - 0.75) / 0.95))
        fog = min(1.0, max(0.0, (pz - 1) / 20))
        return base * (1 - fog) + 0.34 * fog

    def trace(origin, direction, depth=0) -> float:
        if radius:
            oc = tuple(origin[i] - ball[i] for i in range(3))
            b = sum(a * e for a, e in zip(oc, direction))
            disc = b * b - (sum(a * a for a in oc) - radius * radius)
            if disc > 0 and depth < 2:
                t = -b - math.sqrt(disc)
                if t > 1e-3:
                    p = tuple(origin[i] + direction[i] * t for i in range(3))
                    n = tuple((p[i] - ball[i]) / radius for i in range(3))
                    dn = sum(direction[i] * n[i] for i in range(3))
                    reflected = tuple(direction[i] - 2 * dn * n[i] for i in range(3))
                    colour = trace(p, reflected, depth + 1)
                    glint = max(0.0, sum(reflected[i] * sun[i] for i in range(3))) ** 60
                    rim = min(1.0, max(0.0, (-dn - 0.08) / 0.2))
                    return min(1.0, colour * rim + glint * 1.6)
        if direction[1] < -1e-4:
            t = -origin[1] / direction[1]
            return floor(origin[0] + direction[0] * t, origin[2] + direction[2] * t)
        if depth:  # What the ball sees is a bright studio, not the black behind it.
            return 0.25 + 0.75 * min(1.0, max(0.0, 1 - direction[1] * 1.15))
        return max(0.0, 0.42 - direction[1] * 1.5)  # The sky glows a little at the horizon.

    data = bytearray(width * height)
    for j in range(height):
        for i in range(width):
            x, y = (i + 0.5 - width / 2) / (height * 0.82), (height / 2 - j - 0.5) / (height * 0.82) - 0.16
            length = math.sqrt(x * x + y * y + 1)
            data[j * width + i] = max(0, min(255, int(trace(cam, (x / length, y / length, 1 / length)) * 255)))
    gray = Image.frombytes("L", (width, height), bytes(data)).resize((W, H), Image.BOX)
    page.image.paste(craft.atkinson(gray))
    draw = ImageDraw.Draw(page.image)
    if found is not None:
        picture, mask = found
        x, y = W - picture.width - 14, 158 - picture.height
        drawing = craft.atkinson(picture)
        # A spotlight keeps the subject clear of the checkerboard, as on a real stage.
        cx, cy = x + picture.width // 2, y + picture.height // 2
        rx, ry = picture.width // 2 + 18, picture.height // 2 + 18
        draw.ellipse([cx - rx, cy - ry, cx + rx, cy + ry], fill=255, outline=0, width=2)
        page.image.paste(0, (x, y), mask.filter(ImageFilter.MaxFilter(3)))
        page.image.paste(drawing, (x, y), mask)
    text = _display(spec) if not spec.say else spec.say.upper()
    lines = _lines_for(spec, text, "futura", 122, 72, 5, most=3)
    masks = stack(lines, "futura", 122, 72, 5, stretch=1.25)
    if smallest(masks) < MIN_CAP:
        raise _NoFit
    head = sum(m.height + 5 for m in masks)
    draw.rectangle([0, 0, 146, 12 + head + (34 if spec.sub else 0)], fill=0)
    y = 12
    for line, mask in zip(lines, masks):
        page.text(mask, 12, y, line, 255)
        y += mask.height + 5
    if spec.sub:
        lines_sub = craft.wrap_caption(spec.sub, 126, "din", 18)
        total = sum(m.height + 3 for m in lines_sub) + 8
        draw.rectangle([6, y, 142, y + total], fill=0)
        y += 5
        for mask in lines_sub:
            page.text(mask, 12, y, spec.sub, 255)
            y += mask.height + 3


def _series(spec: Spec, default: int = 9) -> list[float]:
    """The numbers, scaled from 0 to 1. Without any, a shape that starts low and builds."""
    if len(spec.data) >= 2:
        low, high = min(spec.data), max(spec.data)
        span = high - low or 1.0
        return [(v - low) / span for v in spec.data]
    return [min(1.0, max(0.0, (i - default * 0.4) / (default * 0.5))) for i in range(default)]


def _rain(page: _Page, spec: Spec) -> None:
    """Strokes as dense as the numbers say. The empty stretch of the series is where the words go."""
    rng = spec.rng()
    series = _series(spec)
    draw = page.draw
    page.image.paste(0, (0, 0, W, H))

    def level(x: float) -> float:
        pos = x / W * (len(series) - 1)
        i = min(len(series) - 2, int(pos))
        return series[i] + (series[i + 1] - series[i]) * (pos - i)

    for _ in range(3000):
        x, y = rng.uniform(0, W + 20), rng.uniform(-12, 200)
        if rng.random() < level(min(W - 1, x)) ** 1.2:
            length = 6 + 14 * level(min(W - 1, x))
            draw.line([(x, y), (x - length * 0.34, y + length)], fill=255)
    labels = spec.items[:9]
    draw.rectangle([0, 184 if labels else 200, W, H], fill=255)
    ticks = max(len(labels), len(series))
    for i in range(ticks):
        x = 8 + i * (W - 16) / max(1, ticks - 1)
        draw.line([(x, 184 if labels else 200), (x, 189 if labels else 205)], fill=0)
    if labels:
        step = 1 if len(labels) <= 5 else 2
        for i, label in enumerate(labels[::step]):
            mask = caption(label, "din", 17)
            x = 8 + i * step * (W - 16) / max(1, len(labels) - 1)
            page.text(mask, min(W - mask.width - 4, max(4, x - mask.width / 2)), 194, label)
    # The driest stretch of the width that the words need.
    width = 134
    best_x, best_level = 0, float("inf")
    for x in range(0, W - width - 8, 8):
        average = sum(level(x + k) for k in range(0, width, 6)) / (width / 6)
        if average < best_level:
            best_x, best_level = x, average
    x = best_x + 12
    area = 150 - (24 if spec.sub else 0)
    text = _display(spec)
    lines = _lines_for(spec, text, "impact", width - 12, area, 6, most=4)
    masks = stack(lines, "impact", width - 12, area, 6, stretch=1.5)
    if smallest(masks) < MIN_CAP:
        raise _NoFit
    total = sum(m.height for m in masks) + 6 * (len(masks) - 1)
    draw.rectangle([x - 8, 4, x + width - 4, 12 + total + (30 if spec.sub else 0)], fill=0)
    y = 12
    for line, mask in zip(lines, masks):
        page.text(mask, x, y, line, 255)
        y += mask.height + 6
    if spec.sub:
        mask = caption(spec.sub, "din", 18, width - 12)
        page.text(mask, x, y + 2, spec.sub, 255)


def _ridges(page: _Page, spec: Spec) -> None:
    """Real numbers as a mountain range. A chart nobody has to read."""
    rng = spec.rng()
    big = _pull_number(spec)
    series = _series(spec, 7)

    def curve(x: float) -> float:
        pos = x / W * (len(series) - 1)
        i = min(len(series) - 2, int(pos))
        t = pos - i
        t = t * t * (3 - 2 * t)
        return series[i] * (1 - t) + series[i + 1] * t

    page.image.paste(craft.bayer(craft.tone(lambda x, y: 1 - max(0.0, 0.34 - y / 380))))
    draw = page.draw
    sun_x = rng.randrange(40, 240)
    draw.ellipse([sun_x, 14, sun_x + 58, 72], fill=255, outline=0, width=2)
    for k in range(5):
        phase = rng.random() * 9
        base, amp, shade = 62 + k * 20, 40 - k * 3, 0.84 - k * 0.19

        def ridge(x: int) -> float:
            value = curve((x + k * 41) % W)
            return base - value * amp + math.sin(x / (21 - k) + phase) * 7 + math.sin(x / 6.3 + phase * 2) * 2.2

        tops = [ridge(x) for x in range(W)]
        layer = craft.bayer(craft.tone(lambda x, y: shade - (y - tops[x]) * 0.0022 if y >= tops[x] else 1))
        mask = craft.tone(lambda x, y: 1 if y >= tops[x] else 0)
        page.image.paste(layer, (0, 0), mask)
        draw.line([(x, tops[x]) for x in range(W)], fill=0)
    front = [150 - curve(x) * 18 + math.sin(x / 11) * 1.5 for x in range(W)]
    draw.polygon([(x, front[x]) for x in range(W)] + [(W, H), (0, H)], fill=0)
    left = 12
    if big:
        mask = word(big, "impact", h=52)
        if mask.width > 150:
            mask = word(big, "impact", w=150, h=52)
        page.text(mask, left, 154, big, 255)
        left += mask.width + 10
    words = spec.say.upper()
    room = W - left - 12
    if words and spec.sub:
        page.fit_line(words, "din", left, 154, room, 24, 255)
        page.fit_line(spec.sub.upper(), "din", left, 183, room, 23, 255)
    elif words:
        page.stack(_lines_for(spec, words, "din", room, 52, 4, most=2), "din", left, 154, room, 52, 4, 255, center=True, stretch=1.3)
    elif spec.sub:
        page.fit_line(spec.sub.upper(), "din", left, 166, room, 28, 255)


def _transit(page: _Page, spec: Spec) -> None:
    """The concept is the picture: branches physically become one line. Items name the branches."""
    rng = spec.rng()
    branches = (spec.items or [spec.sub or "A", "B"])[:3]
    if len(branches) == 1:
        branches.append("")
    scale = 4
    big = Image.new("L", (W * scale, H * scale), 255)
    draw = ImageDraw.Draw(big)
    merge_y = 62
    starts = [26, 98] if len(branches) == 2 else [24, 62, 100]

    def line(points: list[tuple[float, float]], width: float) -> None:
        scaled = [(x * scale, y * scale) for x, y in points]
        draw.line(scaled, fill=0, width=int(width * scale), joint="curve")
        radius = width * scale / 2
        for x, y in (scaled[0], scaled[-1]):
            draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=0)

    def dot(x: float, y: float, radius: float, fill: int) -> None:
        draw.ellipse([(x - radius) * scale, (y - radius) * scale, (x + radius) * scale, (y + radius) * scale], fill=fill)

    for start in starts:
        curve = [(66 + (182 - 66) * t / 120, start + (merge_y - start) * ((t / 120) ** 2 * (3 - 2 * t / 120))) for t in range(121)]
        line([(-10, start), (66, start), *curve], 9)
        for k in range(rng.randint(2, 3)):
            x = 12 + k * 20
            dot(x, start, 8, 0)
            dot(x, start, 5, 255)
    line([(178, merge_y), (262, merge_y)], 17)
    dot(276, merge_y, 28, 0)
    dot(276, merge_y, 18, 255)
    dot(276, merge_y, 9, 0)
    page.image.paste(big.resize((W, H), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0))
    for start, name in zip(starts, branches):
        if name:
            mask = caption(name, "menlo", 16, 184)
            y = start - 21 if start < merge_y else start + 8
            page.text(mask, 62, y, name)
    text = _display(spec)
    top = 125
    room = 58 if spec.sub else 82
    lines = _lines_for(spec, text, "futura", 292, room, 4, most=2)
    bottom = page.stack(lines, "futura", 10, top, 292, room, 4, center=False, stretch=1.15)
    if spec.sub:
        _footer(page, spec, 10, H - 28, 292, 24)


def _facts(spec: Spec) -> list[tuple[str, str]]:
    facts = []
    for item in spec.items:
        key, separator, value = item.partition(":")
        if separator and value.strip() and len(key) <= 12:
            facts.append((key.strip().upper(), value.strip().upper()))
        else:
            facts.append(("", item.upper()))
    return facts


def _ticket(page: _Page, spec: Spec) -> None:
    """A real object, not a layout. Items become printed fields, and a QR code can sit on the stub."""
    rng = spec.rng()
    draw = page.draw
    draw.rounded_rectangle([3, 3, W - 4, H - 4], radius=10, outline=0, width=2)
    draw.rounded_rectangle([3, 3, W - 4, 34], radius=10, fill=0)
    draw.rectangle([3, 16, W - 4, 34], fill=0)
    if spec.say:
        page.fit_line(spec.say.upper(), "din", 14, 11, W - 30, 17, 255)
    stub = 210
    for y in range(44, H - 12, 7):
        draw.rectangle([stub, y, stub + 1, y + 3], fill=0)
    for cy in (35, H - 4):
        draw.ellipse([stub - 6, cy - 6, stub + 7, cy + 6], fill=255, outline=0, width=2)

    facts = _facts(spec)
    if spec.big:
        facts.insert(0, ("", spec.big.upper()))
    if spec.sub:
        facts.insert(0, ("", spec.sub.upper()))
    if not facts and not spec.qr:
        raise _NoFit
    stub_fact = None
    if not spec.qr and len(facts) >= 2:
        stub_fact = facts.pop()

    def field_at(key: str, value: str, x: int, y: int, width: int, height: int) -> None:
        if key:
            page.text(caption(key, "din", 16, width), x, y, key)
            y += 16
            height -= 16
        page.fit_line(value, "din", x, y, width, height)

    # Short values share a row. A long one gets the whole width, or it would be too small to read.
    rows: list[list[tuple[str, str]]] = []
    for fact in facts:
        wide = craft.aspect(fact[1], "din") * 22 > 88
        if rows and not wide and len(rows[-1]) == 1 and craft.aspect(rows[-1][0][1], "din") * 22 <= 88:
            rows[-1].append(fact)
        else:
            rows.append([fact])
    if len(rows) > 3:
        raise _NoFit
    row_height = min(58, 124 // max(1, len(rows)))
    y = 40
    for row in rows:
        width = (186 - 10 * (len(row) - 1)) // len(row)
        for i, (key, value) in enumerate(row):
            field_at(key, value, 14 + i * (width + 10), y, width, row_height - 4)
        y += row_height
        if row is not rows[-1]:
            draw.rectangle([14, y - 3, 200, y - 2], fill=0)
    if y < 166:
        x = 14
        while x < 200:
            bar = rng.choice((1, 1, 2, 3))
            draw.rectangle([x, max(y + 2, 170), min(x + bar - 1, 200), 202], fill=0)
            x += bar + rng.choice((1, 2, 2, 3))

    if spec.qr:
        import segno

        code = segno.make(spec.qr, error="m", boost_error=False)
        matrix = code.matrix
        side = len(matrix)
        module = 88 // side
        if module < 2:
            page.report.warnings.append("That QR text is too long to scan at this size. Shorten the link.")
        module = max(1, module)
        x0, y0 = 218 + (86 - side * module) // 2, 46
        for j, row in enumerate(matrix):
            for i, cell in enumerate(row):
                if cell:
                    draw.rectangle([x0 + i * module, y0 + j * module, x0 + (i + 1) * module - 1, y0 + (j + 1) * module - 1], fill=0)
        page.mark(spec.qr, 99)
    below_fact = 46
    if stub_fact is not None:
        key, value = stub_fact
        y = 148 if spec.qr else 46
        field_at(key, value, 220, y, 80, 44 if not spec.qr else H - y - 12)
        below_fact = 100
    if spec.pic and not spec.qr:
        found = _picture(spec, 80, H - below_fact - 16)
        if found is not None:
            gray, mask = found
            page.image.paste(craft.atkinson(gray), (218 + (84 - gray.width) // 2, below_fact + (H - below_fact - 12 - gray.height) // 2), mask)


def _post(page: _Page, spec: Spec) -> None:
    """A note that arrives as post: airmail edge, a stamp of the subject, and a postmark."""
    draw = page.draw
    for i in range(-20, W + 20, 12):
        ink = 0 if (i // 12) % 2 else 255
        draw.polygon([(i, 0), (i + 6, 0), (i, 8), (i - 6, 8)], fill=ink)
        draw.polygon([(i, H - 8), (i + 6, H - 8), (i, H), (i - 6, H)], fill=ink)
    sx, sy, sw, sh = 214, 16, 86, 104
    draw.rectangle([sx, sy, sx + sw, sy + sh], fill=0)
    for x in range(sx, sx + sw + 1, 8):
        for y in (sy, sy + sh):
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=255)
    for y in range(sy, sy + sh + 1, 8):
        for x in (sx, sx + sw):
            draw.ellipse([x - 3, y - 3, x + 3, y + 3], fill=255)
    draw.rectangle([sx + 7, sy + 7, sx + sw - 7, sy + sh - 7], fill=255)
    default = "🎂" if re.search(r"birthday|bursdag|fødselsdag", spec.say, re.I) else "💌"
    found = _picture(spec, sw - 18, sh - 18, default) or _picture(Spec(pic="heart"), sw - 18, sh - 18)
    if found is not None:
        gray, mask = found
        page.image.paste(craft.atkinson(gray), (sx + 9 + (sw - 18 - gray.width) // 2, sy + 9 + (sh - 18 - gray.height) // 2), mask)
    px, py = 214, 150
    mark = Image.new("L", (W, H), 0)
    ring = ImageDraw.Draw(mark)
    ring.ellipse([px - 34, py - 34, px + 34, py + 34], outline=255, width=3)
    ring.ellipse([px - 25, py - 25, px + 25, py + 25], outline=255)
    for k in range(5):
        ring.line([(x, py - 22 + k * 11 + math.sin(x / 9) * 3) for x in range(px + 36, W + 2, 2)], fill=255, width=2)
    page.image.paste(ImageChops.invert(page.image), (0, 0), mark)
    draw.ellipse([px - 24, py - 24, px + 24, py + 24], fill=255)
    date = spec.date or time.strftime("%-d %b").upper()
    paste(page.image, word("PRINS", "din", w=34), px - 17, py - 15)
    paste(page.image, word(date[:8], "din", w=34), px - 17, py + 3)
    column, top = 158, 18
    foot = 26 if spec.sender else 0
    extra = 28 if spec.sub else 0
    area = H - top - 14 - foot - extra
    text = spec.say
    if not text:
        raise _NoFit
    lines = _lines_for(spec, text, "didot-italic", column, area, 8, most=3)
    masks = [word(line, "didot-italic", w=min(column, round(44 * craft.aspect(line, "didot-italic"))), heavy=True) for line in lines]
    if sum(m.height for m in masks) + 8 * (len(masks) - 1) > area:
        masks = [word(line, "didot-italic", h=max(8, (area - 8 * (len(lines) - 1)) // len(lines)), heavy=True) for line in lines]
        masks = [m if m.width <= column else word(line, "didot-italic", w=column, heavy=True) for line, m in zip(lines, masks)]
    if smallest(masks) < MIN_CAP:
        raise _NoFit
    y = top
    for line, mask in zip(lines, masks):
        page.text(mask, 14, y, line)
        y += mask.height + 8
    if spec.sub:
        page.block_text(spec.sub, "din", 14, min(y + 2, H - 12 - foot - extra), column, extra)
    if spec.sender:
        y = H - 12 - foot
        label = caption("FROM", "din", 16)
        page.text(label, 14, y + 4, "FROM")
        page.fit_line(spec.sender.upper(), "din", 14 + label.width + 8, y, column - label.width - 8, 22)


def _cover(page: _Page, spec: Spec) -> None:
    """Generative tiles behind a plate. The words seed the pattern, so no two are the same."""
    rng = spec.rng()
    scale = 3
    big = Image.new("L", (W * scale, H * scale), 255)
    draw = ImageDraw.Draw(big)
    cell = rng.choice((24, 26, 28)) * scale
    band = int(cell * 0.34)
    half = cell // 2
    for gy in range(0, H * scale, cell):
        for gx in range(0, W * scale + cell, cell):
            mode = rng.random()
            if mode < 0.46:
                draw.arc([gx - half, gy - half, gx + half, gy + half], 0, 90, fill=0, width=band)
                draw.arc([gx + half, gy + half, gx + cell + half, gy + cell + half], 180, 270, fill=0, width=band)
            elif mode < 0.92:
                draw.arc([gx + half, gy - half, gx + cell + half, gy + half], 90, 180, fill=0, width=band)
                draw.arc([gx - half, gy + half, gx + half, gy + cell + half], 270, 360, fill=0, width=band)
            else:
                draw.line([(gx + half, gy), (gx + half, gy + cell)], fill=0, width=band)
                draw.line([(gx, gy + half), (gx + cell, gy + half)], fill=0, width=band)
    page.image.paste(big.resize((W, H), Image.LANCZOS).point(lambda v: 255 if v >= 128 else 0))
    text = _display(spec)
    width = 196
    lines = _lines_for(spec, text, "futura", width, 60, 6, most=3)
    masks = stack(lines, "futura", width, 60, 6, stretch=1.2)
    if smallest(masks) < MIN_CAP:
        raise _NoFit
    head = sum(m.height for m in masks) + 6 * (len(masks) - 1)
    sub_masks = craft.wrap_caption(spec.sub, width, "din", 22) if spec.sub else []
    sub_h = sum(m.height + 4 for m in sub_masks)
    total = head + sub_h + (8 if sub_masks else 0) + 24
    top = (H - total) // 2
    page.draw.rectangle([44, top - 4, W - 44, top + total + 4], fill=255)
    page.draw.rectangle([48, top, W - 48, top + total], fill=0)
    y = top + 12
    for line, mask in zip(lines, masks):
        page.text(mask, 58, y, line, 255)
        y += mask.height + 6
    y += 2
    for mask in sub_masks:
        page.text(mask, 58, y, spec.sub, 255)
        y += mask.height + 4


def _list(page: _Page, spec: Spec) -> None:
    """A title band and ruled lines to tick off. Rows share out whatever height is left."""
    items = spec.items or ([spec.sub] if spec.sub else [])
    if not items:
        raise _NoFit
    draw = page.draw
    head = 44 if spec.say else 0
    if spec.say:
        draw.rectangle([0, 0, W, head - 1], fill=0)
        lines = [spec.say.upper()]
        ratio = craft.aspect(lines[0], "impact")
        height = min(30, round(296 / ratio))
        if height < MIN_CAP:
            raise _NoFit
        mask = word(lines[0], "impact", w=min(296, round(height * ratio)), h=height)
        page.text(mask, 8, (head - mask.height) // 2, lines[0], 255)
    foot = 24 if spec.sub and spec.items else 0
    columns = 2 if len(items) > 5 else 1
    per_column = math.ceil(len(items) / columns)
    room = H - head - foot - 8
    row = room // per_column
    if row < 20:
        raise _NoFit
    width = (W - 16 - 10 * (columns - 1)) // columns
    size = max(craft.MIN_TEXT_PX, min(34, row - 8))
    for index, item in enumerate(items):
        column = index // per_column
        x = 8 + column * (width + 10)
        y = head + 4 + (index % per_column) * row
        box = max(10, min(row - 10, 18))
        top = y + (row - box) // 2
        draw.rectangle([x, top, x + box, top + box], outline=0, width=2)
        mask = caption(item, "din", size, width - box - 8)
        page.text(mask, x + box + 8, y + (row - mask.height) // 2, item)
        if (index % per_column) < per_column - 1:
            draw.line([(x, y + row - 1), (x + width, y + row - 1)], fill=0)
    if foot:
        _footer(page, spec, 8, H - foot - 2, W - 16, foot - 4)


def _quote(page: _Page, spec: Spec) -> None:
    """Longer words, set like a page. The last resort too, so it always fits, and says if it can't."""
    if spec.say and len(spec.sub) > len(spec.say) * 1.5:
        spec.say, spec.sub = spec.sub, spec.say  # The longer one is the quote; the other, who said it.
    text = spec.say or spec.sub or spec.big or " ".join(spec.items) or spec.pic or spec.qr
    draw = page.draw
    foot = 28 if spec.sub and spec.say else 0
    draw.rectangle([10, 10, 13, H - 12 - foot], fill=0)
    x, width = 22, W - 34
    area = H - 22 - foot
    chosen: list[Image.Image] = []
    for size in (60, 52, 44, 38, 32, 28, 24, 21, 18, craft.MIN_TEXT_PX):
        face = "didot-italic" if size >= 38 else "georgia"
        lines = craft.wrap_caption(text, width, face, size)
        gap = max(3, size // 6)
        total = sum(m.height for m in lines) + gap * (len(lines) - 1)
        if total <= area:
            chosen = lines
            break
    if not chosen:
        size = craft.MIN_TEXT_PX
        gap = 3
        lines = craft.wrap_caption(text, width, "georgia", size)
        kept, total = [], 0
        for mask in lines:
            if total + mask.height + gap > area:
                break
            kept.append(mask)
            total += mask.height + gap
        chosen = kept
        page.report.warnings.append("The text was too long to fit, so the end was cut off. Shorten it.")
    y = 10 + (area - sum(m.height for m in chosen) - gap * (len(chosen) - 1)) // 2
    for mask in chosen:
        page.text(mask, x, y, text)
        y += mask.height + gap
    if foot:
        _footer(page, spec, x, H - foot - 2, width, foot - 6)


def _picture_look(page: _Page, spec: Spec) -> None:
    """The subject, huge and printed, with stacked type beside it. For any picture someone asks for."""
    rng = spec.rng()
    found = _picture(spec, 172, 204)
    if found is None:
        raise _NoFit
    gray, mask = found
    finish = rng.choice(("atkinson", "halftone"))
    drawing = craft.finish_picture(gray, mask, finish)
    words_left = rng.random() < 0.5
    text_w = W - gray.width - 26
    if text_w < 100:
        gray, mask = craft.fit(gray, 170, 190), craft.fit(mask, 170, 190).point(lambda v: 255 if v >= 128 else 0)
        drawing = craft.finish_picture(gray, mask, finish)
        text_w = W - gray.width - 26
    pic_x = W - gray.width - 8 if words_left else 8
    text_x = 8 if words_left else gray.width + 18
    cx, cy = pic_x + gray.width / 2, H / 2
    rays = rng.randrange(14, 24)
    behind = craft.tone(lambda x, y: 0.72 if (math.atan2(y - cy, x - cx) * rays / math.pi) % 2 < 1 else 1.0)
    panel = craft.bayer(behind)
    left_edge = pic_x - 8 if words_left else 0
    right_edge = W if words_left else pic_x + gray.width + 8
    page.image.paste(panel.crop((left_edge, 0, right_edge, H)), (left_edge, 0))
    page.image.paste(0, (pic_x, (H - gray.height) // 2), mask.filter(ImageFilter.MaxFilter(5)))
    page.image.paste(drawing, (pic_x, (H - gray.height) // 2), mask)
    sub_lines = craft.wrap_caption(spec.sub, text_w, "din", 20) if spec.sub else []
    foot = sum(m.height + 4 for m in sub_lines)
    if foot > 80:
        raise _NoFit
    top = 8
    if spec.say:
        text = spec.say.upper()
        room = H - 18 - foot - (6 if foot else 0)
        lines = _lines_for(spec, text, "impact", text_w, room, 6, most=5)
        masks = stack(lines, "impact", text_w, room, 6, stretch=1.3)
        if smallest(masks) < MIN_CAP:
            raise _NoFit
        total = sum(m.height for m in masks) + 6 * (len(masks) - 1)
        top = (H - total - foot - (6 if foot else 0)) // 2
        for line, mask in zip(lines, masks):
            page.text(mask, text_x + (text_w - mask.width) // 2, top, line)
            top += mask.height + 6
    else:
        top = (H - foot) // 2
    for mask in sub_lines:
        page.text(mask, text_x + (text_w - mask.width) // 2, top, spec.sub)
        top += mask.height + 4


@dataclass(frozen=True)
class Look:
    run: Callable[[_Page, Spec], None]
    when: str   # One line for the model: when this look is the right one.
    shows: frozenset[str]
    needs: str = ""


def _shows(*names: str) -> frozenset[str]:
    return frozenset({"say", "sub", *names})


LOOKS: dict[str, Look] = {
    "block": Look(_block, "loud statement", _shows()),
    "alarm": Look(_alarm, "urgent, broken, blocked", _shows()),
    "relief": Look(_relief, "one calm word", _shows()),
    "monument": Look(_monument, "a win, a launch", _shows("big")),
    "ransom": Look(_ransom, "playful nag, under 5 words", _shows()),
    "numeral": Look(_numeral, "countdown, key number", _shows("big"), "a number"),
    "collide": Look(_collide, "appointment at a time", _shows("big"), "a time or number"),
    "picture": Look(_picture_look, "a thing or creature", _shows("pic"), "pic"),
    "engraving": Look(_engraving, "night, quiet, elegant", _shows("pic"), "pic, unless about night"),
    "stage": Look(_stage, "event, show", _shows("pic")),
    "post": Look(_post, "greeting, thanks, birthday", _shows("pic")),
    "ticket": Look(_ticket, "meeting, trip: items KEY: VALUE", _shows("big", "items", "qr", "pic"), "items"),
    "rain": Look(_rain, "weather, trend: data, items label it", _shows("data", "items")),
    "ridges": Look(_ridges, "a total: big, data", _shows("big", "data")),
    "transit": Look(_transit, "merge, route: items name lines", _shows("items")),
    "cover": Look(_cover, "start of a day", _shows()),
    "list": Look(_list, "several items", _shows("items"), "items"),
    "quote": Look(_quote, "sentences, poem", _shows()),
}

LOOK_GUIDE = "; ".join(f"{name}={look.when}" for name, look in LOOKS.items())


# --- choosing -----------------------------------------------------------------------------

_URGENT = re.compile(r"!|\b(urgent|asap|blocked|broken|down|failed|failing|outage|deadline|overdue|stop|now|haster|nede|feil)\b", re.I)
_WIN = re.compile(r"\b(ship|shipped|launched|released|done|won|winner|congrat\w*|hooray|finally|gratulerer|ferdig)\b", re.I)
_GREET = re.compile(r"\b(happy|birthday|thanks|thank you|welcome|hello|hi|love|miss you|takk|bursdag|gratulerer|hei|merry|sorry)\b", re.I)
_CALM = re.compile(r"\b(focus|breathe|rest|quiet|calm|relax|pause|silence|fokus|pust|ro)\b", re.I)
_MERGE = re.compile(r"\b(merged?|branch|route|line|journey|train|metro|commute)\b", re.I)
_NAG = re.compile(r"\b(call|reply|pay|remember|don'?t forget|ring|svar|husk)\b", re.I)
_DAY = re.compile(r"\b(mon|tues|wednes|thurs|fri|satur|sun)day\b|\b(mandag|tirsdag|onsdag|torsdag|fredag|lørdag|søndag|good morning|god morgen|today|i dag)\b", re.I)
_EVENT = re.compile(r"\b(demo|show|party|concert|gig|launch party|premiere|festival|talk)\b", re.I)
_WEATHER = re.compile(r"\b(rain|snow|storm|wind|forecast|weather|regn|snø|vær)\b", re.I)
_TIME = re.compile(r"\b\d{1,2}[:.]\d{2}\b")
_COUNT = re.compile(r"\b\d+\s*(days?|hours?|weeks?|left|dager?|timer?|uker?|igjen)\b|^\d+%?$", re.I)


def rank(spec: Spec) -> list[str]:
    """The looks most likely to suit this content, best first. Cheap: no drawing, no model."""
    text = f"{spec.say} {spec.sub}"
    words = len(spec.say.split())
    score: dict[str, float] = {name: 0.0 for name in LOOKS}
    score["block"] = 1.0

    def add(*pairs: tuple[str, float]) -> None:
        for name, value in pairs:
            score[name] += value

    if len(spec.say) > 44 or words > 8:
        add(("quote", 9), ("block", -1))
    if spec.pic:
        add(("picture", 4), ("engraving", 2), ("stage", 1), ("post", 1))
    if spec.items:
        kv = sum(":" in item for item in spec.items)
        add(("ticket", 6 if kv >= 2 else 0), ("list", 5 if kv < 2 else 1), ("transit", 1))
    if spec.qr:
        add(("ticket", 8))
    if spec.data:
        add(("ridges", 5 if (spec.big or _NUMBER.search(spec.say)) else 3), ("rain", 4))
    if _WEATHER.search(text):
        add(("rain", 5 if spec.data else 3), ("picture", 1))
    if _URGENT.search(text):
        add(("alarm", 5))
    if _WIN.search(text):
        add(("monument", 5))
    if _GREET.search(text):
        add(("post", 6))
    if _CALM.search(text) and words <= 2:
        add(("relief", 6))
    if _MERGE.search(text):
        add(("transit", 5))
    if _NAG.search(text) and words <= 5:
        add(("ransom", 4))
    if _DAY.search(text):
        add(("cover", 4))
    if _EVENT.search(text):
        add(("stage", 4))
    if _NIGHT.search(text):
        add(("engraving", 5))
    if (_COUNT.search(spec.say) or (spec.big and not _TIME.fullmatch(spec.big))) and not spec.data:
        add(("numeral", 5))
    if _TIME.search(text) or (spec.big and _TIME.fullmatch(spec.big)):
        add(("collide", 4))
    if words == 1 and not spec.pic:
        add(("relief", 1), ("monument", 0.5))

    # Looks missing what they need sit at the back, so they can never be picked first by accident.
    if not spec.items:
        add(("list", -9))
        if not spec.sub:
            add(("ticket", -3))
    if not spec.pic:
        add(("picture", -9))
        if not _NIGHT.search(text):
            add(("engraving", -9))
    if not (spec.big or _NUMBER.search(spec.say)):
        add(("numeral", -9), ("collide", -9))
    if not spec.data:
        add(("ridges", -2), ("rain", -1))
    return sorted(LOOKS, key=lambda name: (-score[name], list(LOOKS).index(name)))


def _fold(spec: Spec, look: Look) -> Spec:
    """Whatever this look can't show moves somewhere it can, so no words are ever lost."""
    copy = Spec(**{**spec.__dict__})
    if copy.big and "big" not in look.shows:
        known = f"{copy.say} {copy.sub}".casefold()
        if not copy.say:
            copy.say = copy.big
        elif copy.big.casefold() not in known:
            copy.sub = f"{copy.big} {copy.sub}".strip()
        copy.big = ""
    if copy.items and "items" not in look.shows:
        joined = ", ".join(copy.items)
        copy.sub, copy.items = f"{copy.sub} - {joined}".strip(" -"), []
    return copy


# --- output -------------------------------------------------------------------------------


def _thin_ink(image: Image.Image, limit: float = MAX_INK) -> Image.Image:
    """Keeps the print head safe by opening up the middle of big black areas with fine dots.

    Edges and everything within a few pixels of white stay solid, so type stays sharp. On
    paper this reads as black with a little texture, like ink on rough stock.
    """
    black = image.histogram()[0]
    total = W * H
    if black / total <= limit:
        return image
    solid = image.point(lambda v: 255 if v < 128 else 0).filter(ImageFilter.MinFilter(7))
    interior = solid.histogram()[255]
    if not interior:
        return image
    fraction = min(0.42, (black - limit * total) / interior)
    screen = craft.bayer(Image.new("L", (W, H), int(fraction * 255)))
    out = image.copy()
    out.paste(255, (0, 0), ImageChops.multiply(screen, solid))
    return out


def render(op: dict, sender: str = "") -> tuple[Image.Image, Report]:
    """A finished mode "1" note and a report. Never raises for odd content: it finds a look that fits."""
    spec = parse(op)
    _move_emoji(spec)
    if not (spec.say or spec.sub or spec.big or spec.pic or spec.items or spec.data or spec.qr):
        raise ValueError("A poster needs something to say. Set say, or another field.")
    spec.sender = " ".join(str(sender).split())[:40]
    ranked = rank(spec)
    wanted = spec.look if spec.look in LOOKS else ""
    if wanted == "block" and spec.pic and spec.say and craft.resolve_picture(spec.pic, 40) is not None:
        wanted = "picture"  # A small model often sets both. It means the subject should show.
    warnings: list[str] = []
    if spec.look and not wanted and spec.look != "auto":
        warnings.append(f"No look called {spec.look!r}, so I chose one.")
    order = ([wanted] if wanted else []) + [name for name in ranked if name != wanted]
    order = [name for name in order if name != "quote" or order.index(name) < order.index("block")] + ["quote"]
    for name in order:
        look = LOOKS[name]
        report = Report(look=name)
        page = _Page(report)
        try:
            look.run(page, _fold(spec, look))
        except _NoFit:
            if name == wanted:
                warnings.append(f"Look {name} can't hold this legibly, so I used another. Fewer words would let it fit.")
            continue
        image = _thin_ink(page.image.point(lambda v: 255 if v >= 128 else 0))
        if image.histogram()[0] / (W * H) > 0.6 and name != "quote":
            if name == wanted:
                warnings.append(f"Look {name} would be too dark with this content, so I used another.")
            continue
        report.warnings = warnings + report.warnings
        report.alternatives = [other for other in ranked[:4] if other != name][:3]
        if spec.pic and "pic" not in look.shows:
            report.warnings.append(f"Look {name} doesn't show a pic.")
        if spec.qr and "qr" not in look.shows:
            report.warnings.append(f"Look {name} doesn't show a QR code. Use ticket.")
        if spec.pic and name in ("picture", "stage") and craft.resolve_picture(spec.pic, 40) is None:
            report.warnings.append(f"No picture for {spec.pic!r}. Try an emoji.")
        return image.convert("1", dither=Image.NONE), report
    raise AssertionError("quote always fits")  # pragma: no cover


def compare(op: dict, count: int = 4, sender: str = "") -> tuple[bytes, str]:
    """The same content in the looks that suit it best, numbered, on one sheet to look at."""
    spec = parse(op)
    names = rank(spec)[: min(max(2, count), 6)]
    drawn = []
    for name in names:
        image, report = render({**op, "look": name}, sender)
        if report.look == name:
            drawn.append((name, image))
    columns = 2 if len(drawn) <= 4 else 3
    rows = math.ceil(len(drawn) / columns)
    gap = 8
    sheet = Image.new("L", (columns * (W + gap) + gap, rows * (H + gap + 16) + gap), 200)
    paper = ImageDraw.Draw(sheet)
    for index, (name, image) in enumerate(drawn):
        x, y = gap + index % columns * (W + gap), gap + index // columns * (H + gap + 16)
        paper.text((x + 2, y), f"{index + 1} {name}", fill=0)
        sheet.paste(image.convert("L"), (x, y + 14))
    buffer = io.BytesIO()
    sheet.save(buffer, "PNG", optimize=True)
    return buffer.getvalue(), ", ".join(f"{i + 1} {name}" for i, (name, _) in enumerate(drawn))
