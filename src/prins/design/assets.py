"""Things that come from outside the canvas: fonts, images, SVGs and brand logos."""

from __future__ import annotations

import base64
import binascii
import hashlib
import io
import ipaddress
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path
from typing import Optional

from PIL import Image, ImageFont, ImageOps

from .patterns import bayer

MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
CACHE_DIR = Path.home() / ".prins" / "cache"
_USER_AGENT = "prins-note-designer/0.1"
# Simple Icons: brand logos as single-colour SVGs. Pinned, so a logo can't change under a design.
_LOGO_URL = "https://cdn.jsdelivr.net/npm/simple-icons@16.36.0/icons/{slug}.svg"

Image.MAX_IMAGE_PIXELS = 64_000_000  # Refuses decompression bombs.

_FONT_DIRS = [
    Path("/System/Library/Fonts"),
    Path("/System/Library/Fonts/Supplemental"),
    Path("/Library/Fonts"),
    Path.home() / "Library/Fonts",
    Path("/usr/share/fonts"),
    Path.home() / ".fonts",
]
# Friendly names. The value is (file stem, face index in that file).
_FONT_ALIASES = {
    "sans": ("Helvetica", 0),
    "sans-bold": ("Helvetica", 1),
    "serif": ("Times", 0),
    "serif-bold": ("Times", 1),
    "mono": ("Menlo", 0),
    "mono-bold": ("Menlo", 1),
    "hand": ("Bradley Hand Bold", 0),
    "script": ("SnellRoundhand", 0),
    "marker": ("MarkerFelt", 0),
    "display": ("Impact", 0),
    "typewriter": ("AmericanTypewriter", 0),
    "stencil": ("Stencil", 0),
    "comic": ("Comic Sans MS", 0),
    "gothic": ("Copperplate", 0),
    "chalk": ("Chalkduster", 0),
}
PIXEL_FONT = "pixel"
_PIXEL_FONT_HEIGHT = 11


class AssetError(ValueError):
    pass


@lru_cache(maxsize=1)
def _font_files() -> dict[str, Path]:
    found: dict[str, Path] = {}
    for folder in _FONT_DIRS:
        if folder.exists():
            for path in folder.rglob("*"):
                if path.suffix.lower() in {".ttf", ".ttc", ".otf"}:
                    found.setdefault(path.stem.lower(), path)
    return found


def font_names() -> list[str]:
    available = [name for name, (stem, _) in _FONT_ALIASES.items() if stem.lower() in _font_files()]
    return [PIXEL_FONT, *available]


def all_system_fonts() -> list[str]:
    return sorted(_font_files())


def _usable_font(path: Path, size: int, index: int) -> ImageFont.ImageFont:
    """Some system fonts can't measure text at very small sizes, so step up until one can."""
    for candidate in range(size, size + 6):
        font = ImageFont.truetype(str(path), candidate, index=index)
        try:
            font.getlength("x")
            return font
        except OSError:
            continue
    raise AssetError(f"Font {path.stem} can't render at size {size}.")


@lru_cache(maxsize=128)
def load_font(name: str, size: int, external: bool = True) -> ImageFont.ImageFont:
    """A friendly name, any installed font's name, or, for trusted callers, a path or URL."""
    if name in _FONT_ALIASES:
        stem, index = _FONT_ALIASES[name]
        path = _font_files().get(stem.lower())
        if path:
            return _usable_font(path, size, index)
    path = _font_files().get(name.lower())
    if path:
        return _usable_font(path, size, 0)
    if external and (name.startswith(("http://", "https://")) or Path(name).expanduser().exists()):
        data = read_source(name, external=True)
        return ImageFont.truetype(io.BytesIO(data), size)
    if name in _FONT_ALIASES:
        return ImageFont.load_default(size)  # Not on this machine: still prints.
    raise AssetError(f"Unknown font {name!r}. See catalog fonts.")


def pixel_font() -> ImageFont.ImageFont:
    return ImageFont.load_default_imagefont()


PIXEL_HEIGHT = _PIXEL_FONT_HEIGHT


def read_source(src: str, external: bool, web: bool = False) -> bytes:
    """A URL, a local path, or inline `data:` / raw base64.

    `web` allows public web URLs without allowing files or the local network, for a design
    that an untrusted instruction or web page can steer. `external` allows everything.
    """
    if src.startswith("data:"):
        return _decode_base64(src.split(",", 1)[-1])
    if src.lstrip().startswith("<svg") or src.lstrip().startswith("<?xml"):
        return src.encode()
    if src.startswith(("http://", "https://")):
        if not (external or web):
            raise AssetError("This design can't load from the network.")
        return _download(src, guarded=not external)
    if external and len(src) < 1024 and Path(src).expanduser().is_file():
        path = Path(src).expanduser()
        if path.stat().st_size > MAX_DOWNLOAD_BYTES:
            raise AssetError(f"{src} is over 20 MB.")
        return path.read_bytes()
    if not external and len(src) < 1024 and "/" in src:
        raise AssetError("This design can't read files.")
    if len(src) >= 32:
        return _decode_base64(src)
    raise AssetError(f"Can't find {src!r}. Give a URL, a file path, or base64.")


def _decode_base64(text: str) -> bytes:
    try:
        return base64.b64decode(text, validate=False)
    except (binascii.Error, ValueError) as exc:
        raise AssetError("That isn't valid base64.") from exc


def check_public_url(url: str) -> None:
    """Refuse anything that is not an ordinary public web address: this machine, the home
    network, link-local and cloud metadata addresses, odd ports, and non-http schemes."""
    parts = urllib.parse.urlsplit(url)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise AssetError("Only http and https web addresses can be loaded.")
    if parts.username or parts.password:
        raise AssetError("Web addresses with a login in them can't be loaded.")
    try:
        port = parts.port
    except ValueError as exc:
        raise AssetError(f"{url} has a bad port.") from exc
    if port not in (None, 80, 443):
        raise AssetError("Only the standard web ports can be loaded.")
    try:
        addresses = {info[4][0] for info in socket.getaddrinfo(parts.hostname, port or 443, type=socket.SOCK_STREAM)}
    except socket.gaierror as exc:
        raise AssetError(f"Couldn't find {parts.hostname}.") from exc
    for address in addresses:
        if not ipaddress.ip_address(address.split("%")[0]).is_global:
            raise AssetError(f"{parts.hostname} is not a public web address, so it can't be loaded.")


class _GuardedRedirects(urllib.request.HTTPRedirectHandler):
    """Every hop of a redirect has to pass the same check as the first address."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        check_public_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _download(url: str, guarded: bool = False, cache: bool = True, limit: int = MAX_DOWNLOAD_BYTES, truncate: bool = False) -> bytes:
    if guarded:
        check_public_url(url)
    cached = CACHE_DIR / hashlib.sha256(url.encode()).hexdigest()
    if cache:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        if cached.exists():
            return cached.read_bytes()
    request = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    opener = urllib.request.build_opener(_GuardedRedirects) if guarded else urllib.request.build_opener()
    try:
        with opener.open(request, timeout=15) as response:
            data = response.read(limit + 1)
    except (urllib.error.URLError, OSError) as exc:
        raise AssetError(f"Couldn't download {url}: {exc}") from exc
    if len(data) > limit:
        if not truncate:
            raise AssetError(f"{url} is over {limit // (1024 * 1024)} MB.")
        data = data[:limit]
    if cache:
        cached.write_bytes(data)
    return data


def fetch_public_page(url: str, limit: int = 2 * 1024 * 1024) -> bytes:
    """A web page, fresh and never cached, cut at `limit` bytes. Public addresses only."""
    return _download(url, guarded=True, cache=False, limit=limit, truncate=True)


def logo_svg(name: str) -> bytes:
    """A brand logo by name. Tries the name as written, then Simple Icons' slug rules."""
    slug = name.strip().lower()
    slug = slug.replace("+", "plus").replace("&", "and").replace(".", "dot")
    slug = re.sub(r"[^a-z0-9]", "", slug)
    if not slug:
        raise AssetError(f"{name!r} isn't a logo name.")
    try:
        return _download(_LOGO_URL.format(slug=slug))
    except AssetError as exc:
        raise AssetError(
            f"No logo named {name!r} in Simple Icons. Try draw_image or draw_svg with the logo's URL or path data."
        ) from exc


def is_svg(data: bytes) -> bool:
    head = data[:600].lstrip().lower()
    return head.startswith(b"<svg") or (head.startswith(b"<?xml") and b"<svg" in head) or b"<svg" in head[:300]


def refuse_outside_references(data: bytes) -> None:
    """The SVG renderer follows links to local files, which an untrusted design must not do."""
    if not is_svg(data):
        return
    text = data.decode("utf-8", "replace")
    for target in re.findall(r"""(?:href\s*=\s*["']|url\(\s*["']?)([^"')\s]+)""", text):
        if not target.startswith(("#", "data:")):
            raise AssetError("This design can't load files or links from an SVG.")
    if re.search(r"@import|<!ENTITY|<!DOCTYPE", text, re.IGNORECASE):
        raise AssetError("This design can't load files or links from an SVG.")


def load_image(data: bytes, width: int, height: int) -> Image.Image:
    """Any image or SVG, as RGBA. SVGs are rasterized at the size they'll be used."""
    if is_svg(data):
        return _render_svg(data.decode("utf-8", "replace"), width, height)
    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (OSError, ValueError, Image.DecompressionBombError) as exc:
        raise AssetError(f"Couldn't read that image: {exc}") from exc
    return ImageOps.exif_transpose(image).convert("RGBA")


def _render_svg(svg: str, width: int, height: int) -> Image.Image:
    import resvg_py

    match = re.search(r'viewBox=["\']\s*[-\d.]+[\s,]+[-\d.]+[\s,]+([\d.]+)[\s,]+([\d.]+)', svg)
    if match and float(match.group(1)) and float(match.group(2)):
        ratio = float(match.group(1)) / float(match.group(2))
    else:
        ratio = width / max(height, 1)
    scale = min(width / ratio, height)
    target_h, target_w = max(1, round(scale)), max(1, round(scale * ratio))
    try:
        png = resvg_py.svg_to_bytes(svg_string=svg, width=target_w, height=target_h)
    except Exception as exc:  # The renderer raises its own types for malformed SVG.
        raise AssetError(f"Couldn't render that SVG: {exc}") from exc
    return Image.open(io.BytesIO(bytes(png))).convert("RGBA")


def fit_image(image: Image.Image, width: int, height: int, fit: str) -> Image.Image:
    """On a white background. Returns an RGB image of exactly width x height."""
    if fit == "stretch":
        fitted = image.resize((width, height), Image.LANCZOS)
    elif fit == "cover":
        fitted = ImageOps.fit(image, (width, height), Image.LANCZOS)
    else:
        fitted = ImageOps.contain(image, (width, height), Image.LANCZOS)
    background = Image.new("RGBA", (width, height), (255, 255, 255, 255))
    background.alpha_composite(fitted, ((width - fitted.width) // 2, (height - fitted.height) // 2))
    return background.convert("RGB")


DITHERS = ("atkinson", "floyd", "bayer", "halftone", "threshold")


def dither_to_mask(image: Image.Image, method: str, threshold: int = 128, invert: bool = False, contrast: bool = True) -> Image.Image:
    """Mode "1" mask where 255 means a black dot."""
    gray = image.convert("L")
    if contrast and method != "threshold":
        gray = ImageOps.autocontrast(gray, cutoff=1)
    if invert:
        gray = ImageOps.invert(gray)
    width, height = gray.size

    if method == "threshold":
        return gray.point(lambda v: 255 if v < threshold else 0).convert("1", dither=Image.NONE)
    if method == "floyd":
        return ImageOps.invert(gray.convert("1").convert("L")).convert("1", dither=Image.NONE)
    if method == "bayer":
        pixels = gray.load()
        mask = Image.new("1", (width, height), 0)
        mask.putdata([255 if bayer(x, y, 1 - pixels[x, y] / 255) else 0 for y in range(height) for x in range(width)])
        return mask
    if method == "halftone":
        return _halftone(gray)
    if method == "atkinson":
        return _atkinson(gray)
    raise AssetError(f"Unknown dither {method!r}. Use one of {', '.join(DITHERS)}.")


def _atkinson(gray: Image.Image) -> Image.Image:
    """Keeps more contrast than Floyd-Steinberg, which suits thermal paper."""
    width, height = gray.size
    values = [float(v) for v in gray.tobytes()]
    out = [0] * (width * height)
    neighbours = ((1, 0), (2, 0), (-1, 1), (0, 1), (1, 1), (0, 2))
    for y in range(height):
        for x in range(width):
            index = y * width + x
            old = values[index]
            new = 255.0 if old >= 128 else 0.0
            out[index] = 0 if new else 255
            error = (old - new) / 8
            for dx, dy in neighbours:
                nx, ny = x + dx, y + dy
                if 0 <= nx < width and ny < height:
                    values[ny * width + nx] += error
    mask = Image.new("1", (width, height), 0)
    mask.putdata(out)
    return mask


def _halftone(gray: Image.Image, cell: int = 5) -> Image.Image:
    width, height = gray.size
    pixels = gray.load()
    mask = Image.new("1", (width, height), 0)
    data: list[int] = [0] * (width * height)
    for top in range(0, height, cell):
        for left in range(0, width, cell):
            box = [pixels[x, y] for y in range(top, min(top + cell, height)) for x in range(left, min(left + cell, width))]
            radius = (1 - sum(box) / len(box) / 255) ** 0.5 * cell * 0.72
            cx, cy = left + cell / 2, top + cell / 2
            for y in range(top, min(top + cell, height)):
                for x in range(left, min(left + cell, width)):
                    if (x + 0.5 - cx) ** 2 + (y + 0.5 - cy) ** 2 <= radius**2:
                        data[y * width + x] = 255
    mask.putdata(data)
    return mask


_EMOJI_FONT = Path("/System/Library/Fonts/Apple Color Emoji.ttc")


def emoji_rgba(text: str, size: int = 160) -> Optional[Image.Image]:
    """An emoji cropped tight, on transparency. None if this machine has no emoji font."""
    if not _EMOJI_FONT.exists():
        return None
    from PIL import ImageDraw

    font = ImageFont.truetype(str(_EMOJI_FONT), 160)  # The size Apple's font ships at.
    canvas = Image.new("RGBA", (200 * max(1, len(text)), 200), (255, 255, 255, 0))
    ImageDraw.Draw(canvas).text((0, 0), text, font=font, embedded_color=True)
    box = canvas.getbbox()
    return canvas.crop(box) if box else None


def emoji_image(text: str, width: int, height: int) -> Optional[Image.Image]:
    """Any emoji, drawn by the system's emoji font. None if this machine has no such font."""
    image = emoji_rgba(text)
    return None if image is None else fit_image(image, width, height, "contain")
