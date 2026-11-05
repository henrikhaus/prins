"""The craft behind posters: type that fits exactly, pictures of anything, and print-like shading.

Everything here is a decision a designer would make, so that the model doesn't have to. Images
are mode "L" with 0 for black and 255 for white until the very end, so shading can be computed
before it is reduced to one bit.
"""

from __future__ import annotations

import math
import re
import unicodedata
from functools import lru_cache
from typing import Callable, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

from . import assets
from .figures import FIGURES, figure_mask
from .patterns import _BAYER_8

W, H = 312, 216
MIN_TEXT_PX = 16  # Matches the label maker's check: smaller smears on a 203 dpi thermal head.

# File stem, then the face's style name inside that file (None if the file has only one).
_FACES = {
    "impact": ("impact", None),
    "din": ("din condensed bold", None),
    "futura": ("futura", "Bold"),
    "didot": ("didot", "Bold"),
    "didot-italic": ("didot", "Italic"),
    "bodoni": ("bodoni 72", "Bold"),
    "rockwell": ("rockwell", "Bold"),
    "phosphate": ("phosphate", "Solid"),
    "krungthep": ("krungthep", None),
    "black": ("arial black", None),
    "courier": ("courier new bold", None),
    "georgia": ("georgia bold", None),
    "typewriter": ("americantypewriter", "Bold"),
    "menlo": ("menlo", "Bold"),
    "helvetica": ("helvetica", "Bold"),
}
# For scripts the display faces don't have. A note prints correctly in any language.
_FALLBACK_STEMS = ("arial unicode", "applesdgothicneo", "hiragino sans gb", "stheiti medium", "applegothic")
_NO_SUCH_GLYPH = "\U000F0000"
_BIG = 240  # The size text is drawn at before it is reduced, which keeps its outlines clean.
_LEAST_SQUASH = 0.88


# --- type ---------------------------------------------------------------------------------


@lru_cache(maxsize=128)
def _open_face(name: str, size: int) -> ImageFont.FreeTypeFont:
    stem, style = _FACES[name]
    path = assets._font_files().get(stem)
    if path is None:
        return ImageFont.load_default(size)
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


@lru_cache(maxsize=4096)
def _has_glyph(name: str, char: str) -> bool:
    face = _open_face(name, 64)
    drawn = face.getmask(char, mode="L")
    if drawn.getbbox() is None:
        return False
    missing = face.getmask(_NO_SUCH_GLYPH, mode="L")
    return bytes(drawn) != bytes(missing) or drawn.size != missing.size


def _face_for(name: str, text: str, size: int) -> ImageFont.FreeTypeFont:
    if all(c.isspace() or _has_glyph(name, c) for c in text):
        return _open_face(name, size)
    for stem in _FALLBACK_STEMS:
        path = assets._font_files().get(stem)
        if path is not None:
            return ImageFont.truetype(str(path), size)
    return _open_face(name, size)


@lru_cache(maxsize=512)
def _ink(text: str, face: str) -> Image.Image:
    """The text's ink at a large size, cropped tight. Width and height are its true proportions."""
    font = _face_for(face, text, _BIG)
    width = int(font.getlength(text)) + _BIG
    canvas = Image.new("L", (max(1, width), _BIG * 2), 0)
    ImageDraw.Draw(canvas).text((_BIG // 3, _BIG // 3), text, font=font, fill=255)
    box = canvas.getbbox()
    return canvas.crop(box) if box else Image.new("L", (1, 1), 0)


def aspect(text: str, face: str) -> float:
    ink = _ink(text, face)
    return ink.width / max(1, ink.height)


def word(text: str, face: str, w: Optional[int] = None, h: Optional[int] = None, heavy: bool = False) -> Image.Image:
    """A one-bit mask of the text's ink, exactly w by h. Give one side to keep its proportions."""
    ink = _ink(text, face)
    ratio = ink.width / max(1, ink.height)
    if w and not h:
        h = round(w / ratio)
    elif h and not w:
        w = round(h * ratio)
    small = ink.resize((max(1, int(w or ink.width)), max(1, int(h or ink.height))), Image.LANCZOS)
    cut = 62 if heavy else 118  # A heavier cut keeps the hairlines of a delicate face.
    return small.point(lambda v: 255 if v >= cut else 0)


def caption(text: str, face: str = "din", size: int = 18, width: Optional[int] = None) -> Image.Image:
    """Small text, hinted straight to pixels so it stays sharp. Never below the legible size.

    If it can't fit `width` at that size it is squeezed sideways, down to what a condensed
    face can take, and past that the caller should have made it wrap.
    """
    size = max(MIN_TEXT_PX, size)
    font = _face_for(face, text, size)
    canvas = Image.new("L", (int(font.getlength(text)) + size * 2, size * 2), 0)
    drawing = ImageDraw.Draw(canvas)
    drawing.fontmode = "1"
    drawing.text((size // 2, size // 4), text, font=font, fill=255)
    box = canvas.getbbox()
    mask = canvas.crop(box) if box else Image.new("L", (1, 1), 0)
    if width and mask.width > width:
        mask = mask.resize((width, mask.height), Image.NEAREST)
    return mask


def wrap_caption(text: str, width: int, face: str = "din", size: int = 18) -> list[Image.Image]:
    """Greedy lines of legible caption text that fit width."""
    size = max(MIN_TEXT_PX, size)
    font = _face_for(face, text, size)
    lines: list[str] = []
    current = ""
    for token in text.split():
        trial = f"{current} {token}".strip()
        if font.getlength(trial) <= width or not current:
            current = trial
        else:
            lines.append(current)
            current = token
    if current:
        lines.append(current)
    return [caption(line, face, size, width) for line in lines]


def break_lines(text: str, face: str, width: int, height: int, gap: int = 6, most: int = 6) -> list[str]:
    """Where a designer would break these words so they fill the box when each is set full width.

    Tries every set of breaks up to `most` lines. The best one comes closest to the box's height
    without leaving a line far smaller than the others.
    """
    words = text.split()
    if len(words) <= 1:
        return words or [""]
    if len(words) > 14:  # Past this many, trying every break gets slow and greedy wrapping is fine.
        most_each = max(1, math.ceil(len(words) / most))
        return [" ".join(words[i:i + most_each]) for i in range(0, len(words), most_each)]

    best: list[str] = [" ".join(words)]
    best_score = float("inf")
    count = len(words)
    for mask in range(1 << (count - 1)):
        if bin(mask).count("1") + 1 > most:
            continue
        lines, start = [], 0
        for i in range(count - 1):
            if mask >> i & 1:
                lines.append(" ".join(words[start:i + 1]))
                start = i + 1
        lines.append(" ".join(words[start:]))
        heights = [width / max(0.05, aspect(line, face)) for line in lines]
        total = sum(heights) + gap * (len(lines) - 1)
        overflow = max(0.0, total - height) / height
        empty = max(0.0, height - total) / height
        balance = max(heights) / max(1.0, min(heights))
        score = overflow * 3 + empty + max(0.0, balance - 2.2) * 0.25 + len(lines) * 0.002
        if score < best_score:
            best, best_score = lines, score
    return best


def stack(lines: list[str], face: str, width: int, height: int, gap: int = 6, stretch: float = 1.6) -> list[Image.Image]:
    """Each line set to the full width, with heights adjusted so the stack fills the height.

    Letters can take being made taller, and a little shorter. Past that they look distorted,
    so a short word that would need it gets narrower instead, and the caller centers it.
    """
    natural = [width / max(0.05, aspect(line, face)) for line in lines]
    room = max(8, height - gap * (len(lines) - 1))
    scale = min(stretch, room / max(1.0, sum(natural)))
    narrow = 1.0
    if scale < _LEAST_SQUASH:
        narrow, scale = scale / _LEAST_SQUASH, _LEAST_SQUASH
    return [word(line, face, w=max(8, round(width * narrow)), h=max(8, round(n * scale * narrow))) for line, n in zip(lines, natural)]


def smallest(masks: list[Image.Image]) -> int:
    return min((m.height for m in masks), default=0)


def paste(canvas: Image.Image, mask: Image.Image, x: float, y: float, ink: int = 0) -> None:
    canvas.paste(ink, (round(x), round(y)), mask)


def xor(canvas: Image.Image, mask: Image.Image, x: float, y: float) -> None:
    layer = Image.new("L", canvas.size, 0)
    layer.paste(mask, (round(x), round(y)))
    canvas.paste(ImageChops.invert(canvas), (0, 0), layer)


def fill_mask(canvas: Image.Image, fill: Image.Image, mask: Image.Image, x: float = 0, y: float = 0) -> None:
    layer = Image.new("L", canvas.size, 0)
    layer.paste(mask, (round(x), round(y)))
    canvas.paste(fill, (0, 0), layer)


# --- tone ---------------------------------------------------------------------------------


def tone(fn: Callable[[int, int], float], w: int = W, h: int = H) -> Image.Image:
    """fn(x, y) gives brightness from 0 to 1."""
    return Image.frombytes("L", (w, h), bytes(max(0, min(255, int(fn(x, y) * 255))) for y in range(h) for x in range(w)))


def bayer(gray: Image.Image) -> Image.Image:
    data, (w, h) = gray.tobytes(), gray.size
    return Image.frombytes("L", (w, h), bytes(
        255 if data[y * w + x] / 255 > (_BAYER_8[y % 8][x % 8] + 0.5) / 64 else 0
        for y in range(h) for x in range(w)
    ))


def atkinson(gray: Image.Image) -> Image.Image:
    w, h = gray.size
    values = [float(v) for v in gray.tobytes()]
    out = bytearray(w * h)
    spread = ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2))
    for y in range(h):
        for x in range(w):
            i = y * w + x
            new = 255.0 if values[i] >= 128 else 0.0
            out[i] = int(new)
            error = (values[i] - new) / 8
            for dx, dy in spread:
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and ny < h:
                    values[ny * w + nx] += error
    return Image.frombytes("L", (w, h), bytes(out))


def halftone(gray: Image.Image, cell: float = 5, angle: float = 45) -> Image.Image:
    """Round dots on a rotated screen, as in real print."""
    w, h = gray.size
    source = gray.load()
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            u, v = (x * ca + y * sa) / cell, (-x * sa + y * ca) / cell
            iu, iv = math.floor(u), math.floor(v)
            fu, fv = u - iu - 0.5, v - iv - 0.5
            cu, cv = (iu + 0.5) * cell, (iv + 0.5) * cell
            sx = min(w - 1, max(0, int(cu * ca - cv * sa)))
            sy = min(h - 1, max(0, int(cu * sa + cv * ca)))
            radius = math.sqrt(1 - source[sx, sy] / 255) * 0.76
            out[y * w + x] = 0 if fu * fu + fv * fv < radius * radius else 255
    return Image.frombytes("L", (w, h), bytes(out))


def engrave(gray: Image.Image, spacing: float = 4, angle: float = -24, wobble: Optional[Image.Image] = None) -> Image.Image:
    """Copperplate: tone drawn only in lines that swell in the dark and thin out in the light.

    `wobble` is a height map that bends the lines, so they follow a form instead of lying flat.
    """
    w, h = gray.size
    source, bend = gray.load(), wobble.load() if wobble is not None else None
    a = math.radians(angle)
    ca, sa = math.cos(a), math.sin(a)
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            along = x * sa + y * ca
            if bend is not None:
                along += bend[x, y] / 255 * spacing * 2.6
            phase = abs((along / spacing) % 1 - 0.5)
            out[y * w + x] = 0 if phase < 0.5 * (1 - source[x, y] / 255) ** 0.85 else 255
    return Image.frombytes("L", (w, h), bytes(out))


def bright_up(gray: Image.Image, floor: int = 0, ceiling: int = 255) -> Image.Image:
    """Stretches contrast so a picture uses every tone from black to white."""
    low, high = gray.getextrema()
    if high <= low:
        return gray
    return gray.point(lambda v: floor + (v - low) * (ceiling - floor) // (high - low))


def inflate(mask: Image.Image) -> Image.Image:
    """A height map that swells a flat silhouette like a pillow, so light can fall on it."""
    size = max(mask.width, mask.height)
    height = Image.new("L", mask.size, 0)
    for radius, weight in ((size * 0.02, 0.45), (size * 0.05, 0.35), (size * 0.1, 0.2)):
        blurred = mask.filter(ImageFilter.GaussianBlur(radius)).point(lambda v, w=weight: int(v * w))
        height = ImageChops.add(height, blurred)
    return ImageChops.multiply(height, mask)


def light(height: Image.Image, strength: float = 7.0, lx: float = -0.6, ly: float = -0.6, lz: float = 0.53) -> Image.Image:
    """Shades a height map as if lit from the upper left."""
    w, h = height.size
    px = height.load()
    out = bytearray(w * h)
    for y in range(h):
        for x in range(w):
            nx = (px[max(0, x - 1), y] - px[min(w - 1, x + 1), y]) / 255 * strength
            ny = (px[x, max(0, y - 1)] - px[x, min(h - 1, y + 1)]) / 255 * strength
            length = math.sqrt(nx * nx + ny * ny + 1)
            value = (nx * lx + ny * ly + lz) / length
            out[y * w + x] = max(0, min(255, int(40 + value * 300)))
    return Image.frombytes("L", (w, h), bytes(out))


# --- pictures of anything -----------------------------------------------------------------


def _emoji(text: str, size: int) -> Optional[Image.Image]:
    return assets.emoji_rgba(text, size)


@lru_cache(maxsize=1)
def _emoji_words() -> dict[str, str]:
    """Every word in the names of the emoji blocks, to the shortest-named emoji that has it."""
    index: dict[str, tuple[int, str]] = {}
    for code in [*range(0x1F300, 0x1F650), *range(0x1F680, 0x1F700), *range(0x1F900, 0x1FB00)]:
        name = unicodedata.name(chr(code), "")
        words = name.split()
        for token in words:
            if token not in index or len(words) < index[token][0]:
                index[token] = (len(words), chr(code))
    return {token: char for token, (_, char) in index.items()}


def _named_emoji(name: str) -> Optional[str]:
    """`dragon` finds the dragon emoji from Unicode's own names, with no table to keep up."""
    clean = re.sub(r"[^a-z0-9 ]", " ", name.lower()).strip().upper()
    if not clean or len(clean) > 40:
        return None
    for candidate in (clean, f"{clean} FACE"):
        try:
            char = unicodedata.lookup(candidate)
        except KeyError:
            continue
        if ord(char[0]) > 0x2000:
            return char
    words = _emoji_words()
    for token in clean.split():
        for form in (token, token.rstrip("S")):
            if form in words:
                return words[form]
    return None


def resolve_picture(name: str, size: int = 200) -> Optional[tuple[Image.Image, Image.Image]]:
    """A picture of the subject as (gray, mask), both the same size, or None if we have none.

    The subject is a figure name, an emoji, or a word Unicode has an emoji for, or logo:brand.
    """
    name = name.strip()
    if not name:
        return None
    if name.lower().startswith("logo:"):
        try:
            data = assets.logo_svg(name[5:])
            image = assets.load_image(data, size, size)
        except assets.AssetError:
            return None
        return _from_rgba(image)
    # Emoji first: they are detailed drawings, where the built-in figures are flat shapes.
    key = name.lower().replace(" ", "-")
    emoji = name if any(ord(c) > 0x2000 for c in name) else _named_emoji(name)
    if emoji:
        image = _emoji(emoji, size)
        if image is not None:
            return _from_rgba(image)
    if key in FIGURES:
        mask = figure_mask(key, size, size).convert("L")
        box = mask.getbbox()
        mask = mask.crop(box) if box else mask
        return light(inflate(mask), strength=9), mask
    return None


def _from_rgba(image: Image.Image) -> tuple[Image.Image, Image.Image]:
    alpha = image.getchannel("A").point(lambda v: 255 if v >= 110 else 0)
    box = alpha.getbbox()
    if box:
        image, alpha = image.crop(box), alpha.crop(box)
    r, g, b = image.convert("RGB").split()
    # Colour emoji are bright. Mixing in the darkest channel keeps yellow and pink from going white.
    darkest = ImageChops.darker(ImageChops.darker(r, g), b)
    gray = Image.blend(image.convert("L"), darkest, 0.45)
    stretched = bright_up(_mean_inside(gray, alpha), 0, 245)
    return stretched, alpha


def _mean_inside(gray: Image.Image, alpha: Image.Image) -> Image.Image:
    """Whatever is outside the subject shouldn't count as its darkest or brightest tone."""
    average = sum(g for g, a in zip(gray.tobytes(), alpha.tobytes()) if a) // max(1, sum(1 for a in alpha.tobytes() if a))
    return Image.composite(gray, Image.new("L", gray.size, average), alpha)


def fit(image: Image.Image, width: int, height: int) -> Image.Image:
    ratio = min(width / image.width, height / image.height)
    return image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))), Image.LANCZOS)


def finish_picture(gray: Image.Image, mask: Image.Image, finish: str) -> Image.Image:
    """The picture reduced to one bit, in a printer's technique. White outside the subject."""
    hard = mask.point(lambda v: 255 if v >= 128 else 0)
    if finish == "engrave":
        drawn = engrave(gray, spacing=3.6, wobble=inflate(hard))
    elif finish == "halftone":
        drawn = halftone(gray, cell=4.2)
    else:
        drawn = atkinson(gray)
    return Image.composite(drawn, Image.new("L", gray.size, 255), hard)
