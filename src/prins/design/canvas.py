"""The design engine: applies small drawing operations to the 312x216 grid."""

from __future__ import annotations

import base64
import binascii
import random
from typing import Any, Iterable, Optional

from PIL import Image, ImageChops, ImageDraw

from . import assets
from .figures import FIGURES, figure_mask
from .formula import FormulaError, compile_formula
from .frames import FRAMES, frame_mask
from .patterns import PATTERNS, has_pattern, pattern_image

WIDTH, HEIGHT = 312, 216
BITMAP_BYTES = (WIDTH + 7) // 8 * HEIGHT  # 39 bytes per row, 8424 in all.
MAX_OPS = 2000
_MAX_REPEAT = 500

Op = dict[str, Any]


class DesignError(ValueError):
    pass


def image_to_bitmap(image: Image.Image) -> str:
    """The wire format: base64 of packed rows, most significant bit first, 1 = black."""
    if image.size != (WIDTH, HEIGHT):
        raise DesignError(f"A note is exactly {WIDTH}x{HEIGHT}, not {image.width}x{image.height}.")
    packed = bytes(b ^ 0xFF for b in image.convert("1").tobytes())
    return base64.b64encode(packed).decode("ascii")


def bitmap_to_image(bitmap: str) -> Image.Image:
    try:
        packed = base64.b64decode(bitmap, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DesignError("That isn't a valid note bitmap.") from exc
    if len(packed) != BITMAP_BYTES:
        raise DesignError(f"A note bitmap is {BITMAP_BYTES} bytes, not {len(packed)}.")
    return Image.frombytes("1", (WIDTH, HEIGHT), bytes(b ^ 0xFF for b in packed))


def _invert(image: Image.Image) -> Image.Image:
    """ImageChops.invert turns a mode "1" image all white, so go through grayscale."""
    return ImageChops.invert(image.convert("L")).convert("1", dither=Image.NONE)


def _length(draw: ImageDraw.ImageDraw, text: str, font: Any) -> float:
    """Pillow raises division by zero when measuring an empty string."""
    return draw.textlength(text, font=font) if text else 0


def _int(op: Op, key: str, default: int) -> int:
    value = op.get(key, default)
    try:
        return round(float(value))
    except (TypeError, ValueError) as exc:
        raise DesignError(f"{key} must be a number, not {value!r}.") from exc


class Canvas:
    """external=False stops a design reading files or the network, for untrusted callers.
    web=True lets such a design load public web addresses, and nothing else outside itself."""

    def __init__(self, external: bool = True, web: bool = False) -> None:
        self.external = external
        self.web = web
        self.image = Image.new("1", (WIDTH, HEIGHT), 1)
        self.ops: list[Op] = []

    # --- document ---------------------------------------------------------------------

    def apply(self, op: Op) -> None:
        if not isinstance(op, dict) or "op" not in op:
            raise DesignError('Each operation needs an "op" name.')
        if len(self.ops) >= MAX_OPS:
            raise DesignError(f"A design can have {MAX_OPS} operations.")
        self._run(op)
        self.ops.append(op)

    def apply_all(self, ops: Iterable[Op]) -> None:
        for op in ops:
            self.apply(op)

    def undo(self, count: int = 1) -> None:
        keep = self.ops[: max(0, len(self.ops) - max(1, count))]
        self.clear()
        self.apply_all(keep)

    def clear(self) -> None:
        self.image = Image.new("1", (WIDTH, HEIGHT), 1)
        self.ops = []

    @property
    def blank(self) -> bool:
        return not self.ops

    def bitmap(self) -> str:
        return image_to_bitmap(self.image)

    def _run(self, op: Op) -> None:
        name = op["op"]
        handler = getattr(self, f"_op_{str(name).replace('-', '_')}", None)
        if handler is None:
            raise DesignError(f"Unknown op {name!r}. Ops: {', '.join(OPS)}.")
        try:
            handler(op)
        except (assets.AssetError, FormulaError) as exc:
            raise DesignError(str(exc)) from exc
        except (TypeError, KeyError, ValueError) as exc:
            if isinstance(exc, DesignError):
                raise
            raise DesignError(f"Bad {name} op: {exc}") from exc

    # --- painting ---------------------------------------------------------------------

    def _box(self, op: Op) -> tuple[int, int, int, int]:
        x, y = _int(op, "x", 0), _int(op, "y", 0)
        width, height = _int(op, "w", WIDTH - x), _int(op, "h", HEIGHT - y)
        if width <= 0 or height <= 0:
            raise DesignError(f"Box has no area: w={width}, h={height}.")
        if width > 4096 or height > 4096:
            raise DesignError("Box is too big.")
        return x, y, width, height

    def _paint(self, mask: Image.Image, ink: Any = "black") -> None:
        """Mask is canvas-sized, mode "1". Ink is black, white, invert, or any pattern."""
        ink = "black" if ink in (None, "") else str(ink)
        if ink in ("black", "k"):
            self.image.paste(0, (0, 0), mask)
        elif ink in ("white", "w"):
            self.image.paste(1, (0, 0), mask)
        elif ink in ("invert", "x"):
            self.image.paste(_invert(self.image), (0, 0), mask)
        elif has_pattern(ink):
            self.image.paste(0, (0, 0), ImageChops.logical_and(mask, pattern_image(ink, WIDTH, HEIGHT)))
        else:
            raise DesignError(f"Unknown ink {ink!r}. Use black, white, invert, or a pattern name.")

    def _place(self, part: Image.Image, x: int, y: int, op: Op) -> None:
        """Puts a small mask on the canvas, rotated about its own center if asked."""
        mask = Image.new("1", (WIDTH, HEIGHT), 0)
        mask.paste(1, (x, y), part)
        rotation = op.get("rot", 0)
        if rotation:
            center = (x + part.width / 2, y + part.height / 2)
            mask = mask.rotate(-float(rotation), Image.NEAREST, center=center)
        self._paint(mask, op.get("ink"))

    # --- operations -------------------------------------------------------------------

    def _op_text(self, op: Op) -> None:
        text = str(op.get("s", ""))
        if not text:
            return
        x, y, width, height = self._box(op)
        part = render_text(
            text, width, height,
            font=str(op.get("font", "sans-bold")), size=_int(op, "size", 0),
            align=str(op.get("align", "c")), valign=str(op.get("valign", "m")),
            wrap=bool(op.get("wrap", True)), spacing=float(op.get("spacing", 1.15)),
            external=self.external,
        )
        self._place(part, x, y, op)

    def _op_figure(self, op: Op) -> None:
        name = str(op.get("name", ""))
        x, y, width, height = self._box(op)
        if name.startswith("emoji:"):
            image = assets.emoji_image(name[6:], width, height)
            if image is None:
                raise DesignError("This machine has no emoji font. Use a figure or draw_image.")
            self._place(assets.dither_to_mask(image, str(op.get("dither", "atkinson"))), x, y, op)
            return
        if name not in FIGURES:
            raise DesignError(f"Unknown figure {name!r}. See catalog figures, or use emoji:🎂.")
        self._place(figure_mask(name, width, height), x, y, op)

    def _op_pattern(self, op: Op) -> None:
        name = str(op.get("name", ""))
        if not has_pattern(name):
            raise DesignError(f"Unknown pattern {name!r}. See catalog patterns.")
        x, y, width, height = self._box(op)
        part = Image.new("1", (width, height), 0)
        draw = ImageDraw.Draw(part)
        if op.get("shape") == "ellipse":
            draw.ellipse([0, 0, width - 1, height - 1], fill=1)
        else:
            draw.rectangle([0, 0, width - 1, height - 1], fill=1)
        tone = pattern_image(name, width, height)
        self._place(ImageChops.logical_and(part, tone), x, y, op)

    def _op_frame(self, op: Op) -> None:
        name = str(op.get("name", "line"))
        if name not in FRAMES and name not in FIGURES:
            raise DesignError(f"Unknown frame {name!r}. See catalog frames. Figure names also work.")
        inset = _int(op, "inset", 0)
        x, y, width, height = self._box(op)
        box = (x + inset, y + inset, x + width - 1 - inset, y + height - 1 - inset)
        self._paint(frame_mask(name, (WIDTH, HEIGHT), box, max(1, _int(op, "size", 3))), op.get("ink"))

    def _op_shape(self, op: Op) -> None:
        kind = str(op.get("kind", "rect"))
        mask = Image.new("1", (WIDTH, HEIGHT), 0)
        draw = ImageDraw.Draw(mask)
        line_width = max(1, _int(op, "lw", 1))
        fill = 1 if op.get("fill", True) else None
        outline = 1 if fill is None else None

        if kind in ("line", "polygon", "curve"):
            points = _points(op.get("pts"))
            if kind == "polygon":
                draw.polygon(points, fill=fill, outline=outline, width=line_width)
            else:
                if kind == "curve":
                    points = _smooth(points)
                draw.line(points, fill=1, width=line_width, joint="curve")
        else:
            x, y, width, height = self._box(op)
            box = [x, y, x + width - 1, y + height - 1]
            start, end = float(op.get("a0", 0)), float(op.get("a1", 360))
            if kind == "rect":
                draw.rectangle(box, fill=fill, outline=outline, width=line_width)
            elif kind == "rrect":
                draw.rounded_rectangle(box, radius=_int(op, "r", 8), fill=fill, outline=outline, width=line_width)
            elif kind == "ellipse":
                draw.ellipse(box, fill=fill, outline=outline, width=line_width)
            elif kind == "arc":
                draw.arc(box, start, end, fill=1, width=line_width)
            elif kind == "pie":
                draw.pieslice(box, start, end, fill=fill, outline=outline, width=line_width)
            elif kind == "chord":
                draw.chord(box, start, end, fill=fill, outline=outline, width=line_width)
            else:
                raise DesignError(f"Unknown shape {kind!r}. Use rect, rrect, ellipse, line, curve, polygon, arc, pie or chord.")
        self._paint(mask, op.get("ink"))

    def _op_image(self, op: Op) -> None:
        src = op.get("src")
        if not src:
            raise DesignError("image needs a src: URL, file path, or base64.")
        data = assets.read_source(str(src), self.external, self.web)
        if not self.external:
            assets.refuse_outside_references(data)
        self._draw_raster(data, op, default_dither="atkinson", fit="contain")

    def _op_svg(self, op: Op) -> None:
        if op.get("d"):
            viewbox = op.get("vb", "0 0 24 24")
            rule = ' fill-rule="evenodd"' if op.get("evenodd") else ""
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{_clean_viewbox(viewbox)}"><path{rule} d="{_clean_path(str(op["d"]))}"/></svg>'
            data = svg.encode()
        elif op.get("svg"):
            data = str(op["svg"]).encode()
        elif op.get("src"):
            data = assets.read_source(str(op["src"]), self.external, self.web)
        else:
            raise DesignError("svg needs d (path data), svg (markup), or src (URL or path).")
        if not self.external:
            assets.refuse_outside_references(data)
        self._draw_raster(data, op, default_dither="threshold", fit="contain")

    def _op_logo(self, op: Op) -> None:
        name = op.get("name")
        if not name:
            raise DesignError("logo needs a name, such as spotify.")
        self._draw_raster(assets.logo_svg(str(name)), op, default_dither="threshold", fit="contain")

    def _draw_raster(self, data: bytes, op: Op, default_dither: str, fit: str) -> None:
        x, y, width, height = self._box(op)
        image = assets.load_image(data, width, height)
        fitted = assets.fit_image(image, width, height, str(op.get("fit", fit)))
        mask = assets.dither_to_mask(
            fitted, str(op.get("dither", default_dither)), threshold=_int(op, "threshold", 128),
            invert=bool(op.get("invert", False)),
        )
        self._place(mask, x, y, op)

    def _op_pixels(self, op: Op) -> None:
        x, y = _int(op, "x", 0), _int(op, "y", 0)
        scale = max(1, _int(op, "scale", 1))
        if "rows" in op:
            rows = op["rows"]
            if not isinstance(rows, list) or not rows:
                raise DesignError("rows must be a list of strings.")
            width = max(len(str(row)) for row in rows)
            part = Image.new("1", (width, len(rows)), 0)
            for j, row in enumerate(rows):
                for i, char in enumerate(str(row)):
                    if char not in ". 0_":
                        part.putpixel((i, j), 1)
        elif "b64" in op:
            width = _int(op, "w", WIDTH)
            data = assets._decode_base64(str(op["b64"]))
            row_bytes = (width + 7) // 8
            height = _int(op, "h", len(data) // max(row_bytes, 1))
            if len(data) < row_bytes * height or height <= 0:
                raise DesignError(f"b64 has {len(data)} bytes, but {width}x{height} needs {row_bytes * height}.")
            part = Image.frombytes("1", (width, height), data[: row_bytes * height])
        else:
            raise DesignError("pixels needs rows (strings where . is off) or b64 (packed bits, 1 = black).")
        if scale > 1:
            part = part.resize((part.width * scale, part.height * scale), Image.NEAREST)
        self._place(part, x, y, op)

    def _op_formula(self, op: Op) -> None:
        test = compile_formula(str(op.get("f", "")))
        x, y, width, height = self._box(op)
        part = Image.new("1", (width, height), 0)
        part.putdata([255 if test(i, j, width, height) else 0 for j in range(height) for i in range(width)])
        self._place(part, x, y, op)

    def _op_qr(self, op: Op) -> None:
        import segno

        data = str(op.get("s", ""))
        if not data:
            raise DesignError("qr needs s, the text or URL to encode.")
        x, y, width, height = self._box(op)
        code = segno.make(data, error=str(op.get("ecc", "m")), boost_error=False)
        matrix = code.matrix
        side = len(matrix)
        scale = min(width, height) // side
        if scale < 1:
            raise DesignError(f"This QR needs at least {side}x{side} pixels. Give it a bigger box or less text.")
        part = Image.new("1", (side, side), 0)
        part.putdata([255 if cell else 0 for row in matrix for cell in row])
        part = part.resize((side * scale, side * scale), Image.NEAREST)
        self._place(part, x + (width - part.width) // 2, y + (height - part.height) // 2, op)

    def _op_transform(self, op: Op) -> None:
        kind = str(op.get("kind", "invert"))
        x, y, width, height = self._box(op)
        box = (x, y, x + width, y + height)
        region = self.image.crop(box)
        if kind == "invert":
            region = _invert(region)
        elif kind == "flip-h":
            region = region.transpose(Image.FLIP_LEFT_RIGHT)
        elif kind == "flip-v":
            region = region.transpose(Image.FLIP_TOP_BOTTOM)
        elif kind == "rotate":
            region = region.rotate(-float(op.get("deg", 180)), Image.NEAREST, fillcolor=1)
        elif kind == "mirror-h":  # The left half reflected onto the right.
            half = region.crop((0, 0, width // 2, height)).transpose(Image.FLIP_LEFT_RIGHT)
            region.paste(half, (width - half.width, 0))
        elif kind == "mirror-v":
            half = region.crop((0, 0, width, height // 2)).transpose(Image.FLIP_TOP_BOTTOM)
            region.paste(half, (0, height - half.height))
        elif kind == "shift":
            region = ImageChops.offset(region, _int(op, "dx", 0), _int(op, "dy", 0))
        elif kind == "pixelate":
            block = max(2, _int(op, "size", 4))
            small = region.convert("L").resize((max(1, width // block), max(1, height // block)), Image.BOX)
            region = small.resize((width, height), Image.NEAREST).point(lambda v: 255 if v >= 128 else 0).convert("1", dither=Image.NONE)
        elif kind == "outline":
            from PIL import ImageFilter

            gray = region.convert("L")
            eroded = gray.filter(ImageFilter.MaxFilter(3))
            region = ImageChops.invert(ImageChops.subtract(eroded, gray)).point(lambda v: 255 if v >= 128 else 0).convert("1", dither=Image.NONE)
        else:
            raise DesignError(f"Unknown transform {kind!r}. Use invert, flip-h, flip-v, rotate, mirror-h, mirror-v, shift, pixelate or outline.")
        self.image.paste(region, box)

    def _op_repeat(self, op: Op) -> None:
        """Runs `ops` n times, moving by dx, dy each time."""
        count = min(_int(op, "n", 2), _MAX_REPEAT)
        dx, dy = _int(op, "dx", 0), _int(op, "dy", 0)
        for index in range(count):
            for inner in op.get("ops", []):
                self._run(_moved(inner, dx * index, dy * index))

    def _op_scatter(self, op: Op) -> None:
        """Runs `ops` n times at random spots. The same seed gives the same result."""
        rng = random.Random(_int(op, "seed", 1))
        x, y, width, height = self._box(op)
        for _ in range(min(_int(op, "n", 20), _MAX_REPEAT)):
            px, py = x + rng.randrange(width), y + rng.randrange(height)
            for inner in op.get("ops", []):
                self._run(_moved(inner, px, py))

    def _op_clear(self, op: Op) -> None:
        ink = op.get("ink", "white")
        self._paint(Image.new("1", (WIDTH, HEIGHT), 1), ink)


OPS = sorted(name[4:] for name in dir(Canvas) if name.startswith("_op_"))


def _moved(op: Op, dx: int, dy: int) -> Op:
    moved = dict(op)
    moved["x"] = _int(op, "x", 0) + dx
    moved["y"] = _int(op, "y", 0) + dy
    if isinstance(op.get("pts"), list):
        moved["pts"] = [[p[0] + dx, p[1] + dy] for p in _point_pairs(op["pts"])]
    return moved


def _point_pairs(raw: Any) -> list[tuple[float, float]]:
    if not isinstance(raw, list) or len(raw) < 2:
        raise DesignError("pts needs at least two points: [[x,y],[x,y]] or [x,y,x,y].")
    if isinstance(raw[0], (int, float)):
        return [(float(raw[i]), float(raw[i + 1])) for i in range(0, len(raw) - 1, 2)]
    return [(float(p[0]), float(p[1])) for p in raw]


_points = _point_pairs


def _smooth(points: list[tuple[float, float]], steps: int = 12) -> list[tuple[float, float]]:
    """A Catmull-Rom curve through the points."""
    if len(points) < 3:
        return points
    padded = [points[0], *points, points[-1]]
    out: list[tuple[float, float]] = []
    for i in range(1, len(padded) - 2):
        p0, p1, p2, p3 = padded[i - 1], padded[i], padded[i + 1], padded[i + 2]
        for step in range(steps):
            t = step / steps
            out.append(tuple(
                0.5 * (2 * p1[k] + (p2[k] - p0[k]) * t + (2 * p0[k] - 5 * p1[k] + 4 * p2[k] - p3[k]) * t**2
                       + (3 * p1[k] - p0[k] - 3 * p2[k] + p3[k]) * t**3)
                for k in (0, 1)
            ))
    out.append(points[-1])
    return out


def _clean_viewbox(value: Any) -> str:
    text = " ".join(str(v) for v in value) if isinstance(value, list) else str(value)
    if not all(c in "0123456789.,- " for c in text):
        raise DesignError("vb must be four numbers.")
    return text


def _clean_path(value: str) -> str:
    # Path data has no reason to contain quotes or tags. This keeps it inside the attribute.
    if any(c in value for c in '<>"\'&'):
        raise DesignError("d must be plain SVG path data.")
    return value


def render_text(
    text: str,
    width: int,
    height: int,
    font: str = "sans-bold",
    size: int = 0,
    align: str = "c",
    valign: str = "m",
    wrap: bool = True,
    spacing: float = 1.15,
    external: bool = True,
) -> Image.Image:
    """A mode "1" mask of exactly width x height. Size 0 picks the largest size that fits."""
    if font == assets.PIXEL_FONT:
        return _render_pixel_text(text, width, height, size, align, valign, wrap)

    probe = ImageDraw.Draw(Image.new("1", (1, 1)))
    probe.fontmode = "1"

    def layout(candidate: int) -> tuple[Any, list[str], int, int]:
        loaded = assets.load_font(font, candidate, external)
        lines = _wrap_lines(probe, text, loaded, width) if wrap else text.split("\n")
        line_height = max(1, round((sum(loaded.getmetrics())) * spacing))
        widest = max((_length(probe, line, loaded) for line in lines), default=0)
        return loaded, lines, line_height, int(widest)

    if size > 0:
        loaded, lines, line_height, _ = layout(size)
    else:
        low, high, best = 6, min(height + 8, 400), 6
        while low <= high:
            mid = (low + high) // 2
            _, lines, line_height, widest = layout(mid)
            if line_height * len(lines) <= height + (spacing - 1) * mid and widest <= width:
                best, low = mid, mid + 1
            else:
                high = mid - 1
        loaded, lines, line_height, _ = layout(best)

    mask = Image.new("1", (width, height), 0)
    draw = ImageDraw.Draw(mask)
    draw.fontmode = "1"
    total = line_height * len(lines)
    top = {"t": 0, "m": (height - total) // 2, "b": height - total}.get(valign, 0)
    for index, line in enumerate(lines):
        length = _length(draw, line, loaded)
        left = {"l": 0, "c": (width - length) / 2, "r": width - length}.get(align, 0)
        if line:
            draw.text((left, top + index * line_height), line, font=loaded, fill=1)
    return mask


def _wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: Any, width: int) -> list[str]:
    lines: list[str] = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            while draw.textlength(word, font=font) > width and len(word) > 1:
                cut = len(word) - 1
                while cut > 1 and draw.textlength(word[:cut], font=font) > width:
                    cut -= 1
                if line:
                    lines.append(line)
                    line = ""
                lines.append(word[:cut])
                word = word[cut:]
            candidate = f"{line} {word}".strip() if line else word
            if draw.textlength(candidate, font=font) <= width:
                line = candidate
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def _render_pixel_text(text: str, width: int, height: int, size: int, align: str, valign: str, wrap: bool) -> Image.Image:
    """Pillow's bitmap font, scaled in whole steps so every pixel stays square."""
    font = assets.pixel_font()
    probe = ImageDraw.Draw(Image.new("1", (1, 1)))
    char_height = assets.PIXEL_HEIGHT

    def layout(scale: int) -> list[str]:
        return _wrap_lines(probe, text, font, width // scale) if wrap else text.split("\n")

    if size > 0:
        scale = max(1, round(size / char_height))
    else:
        scale = 1
        for candidate in range(1, 64):
            lines = layout(candidate)
            fits = len(lines) * (char_height + 1) * candidate <= height and max((_length(probe, l, font) for l in lines), default=0) * candidate <= width
            if fits:
                scale = candidate
            else:
                break

    lines = layout(scale)
    native = Image.new("1", (max(1, width // scale), max(1, height // scale)), 0)
    draw = ImageDraw.Draw(native)
    draw.fontmode = "1"
    total = len(lines) * (char_height + 1)
    top = {"t": 0, "m": (native.height - total) // 2, "b": native.height - total}.get(valign, 0)
    for index, line in enumerate(lines):
        length = _length(draw, line, font)
        left = {"l": 0, "c": (native.width - length) / 2, "r": native.width - length}.get(align, 0)
        if line:
            draw.text((left, top + index * (char_height + 1)), line, font=font, fill=1)
    scaled = native.resize((native.width * scale, native.height * scale), Image.NEAREST)
    mask = Image.new("1", (width, height), 0)
    mask.paste(scaled, (0, 0))
    return mask


def catalog(kind: Optional[str] = None) -> dict[str, list[str]]:
    """Names that can be used. Kept out of tool schemas, so they only cost tokens when asked for."""
    everything = {
        "figures": sorted(FIGURES),
        "patterns": sorted(PATTERNS) + ["gray:N"],
        "frames": sorted(FRAMES),
        "fonts": assets.font_names(),
        "dithers": list(assets.DITHERS),
        "ops": OPS,
        "system_fonts": assets.all_system_fonts(),
    }
    if kind:
        if kind not in everything:
            raise DesignError(f"Unknown catalog {kind!r}. Use one of {', '.join(everything)}.")
        return {kind: everything[kind]}
    everything.pop("system_fonts")
    return everything
