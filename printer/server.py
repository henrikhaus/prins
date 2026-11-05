# /// script
# requires-python = ">=3.10"
# dependencies = ["bleak", "pillow", "fastapi", "uvicorn"]
# ///
"""Local HTTP API for drawing on the M110's pixel grid and printing it.

  uv run server.py            # http://127.0.0.1:8110  (localhost only: it prints physical labels)

  GET  /canvas                grid geometry (width, height, bit conventions)
  POST /print                 JSON {width, height, format, data(base64), threshold?, dry_run?}
  POST /print/png             raw PNG body; ?dry_run=true, ?dither=true
  GET  /                      minimal drawing page that uses the API
"""
from __future__ import annotations

import asyncio
import base64
import io
from pathlib import Path
from typing import Literal

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from PIL import Image
from pydantic import BaseModel, Field

from m110 import M110

app = FastAPI(title="M110 label canvas")
print_lock = asyncio.Lock()  # one BLE connection at a time

# Calibrated 2026-11-05: 40 mm gap label, 216 rows fit fully (see m110.py).
GRID_WIDTH = M110.label_px
GRID_HEIGHT = 216
MAX_HEIGHT = 240  # a 240-row print was fed correctly during calibration; more would spill past the gap


class PrintRequest(BaseModel):
    width: int = Field(gt=0, le=GRID_WIDTH)
    height: int = Field(gt=0, le=MAX_HEIGHT)
    format: Literal["rgba", "gray8", "1bpp"] = "rgba"
    data: str = Field(description="base64 pixel data, rows top to bottom")
    threshold: int = Field(128, ge=0, le=255, description="gray/alpha-composited value below this prints black")
    dither: bool = False
    dry_run: bool = False


def decode(req: PrintRequest) -> Image.Image:
    """Return an 'L' image (0 = black) from the request pixels."""
    try:
        raw = base64.b64decode(req.data, validate=True)
    except ValueError as exc:
        raise HTTPException(400, f"data is not valid base64: {exc}") from exc
    w, h = req.width, req.height
    if req.format == "1bpp":  # MSB first, rows padded to whole bytes, 1 = black
        expected = ((w + 7) // 8) * h
        if len(raw) != expected:
            raise HTTPException(400, f"1bpp data must be {expected} bytes for {w}x{h}, got {len(raw)}")
        return Image.frombytes("1", (w, h), bytes(b ^ 0xFF for b in raw)).convert("L")
    if req.format == "gray8":
        if len(raw) != w * h:
            raise HTTPException(400, f"gray8 data must be {w * h} bytes for {w}x{h}, got {len(raw)}")
        return Image.frombytes("L", (w, h), raw)
    if len(raw) != w * h * 4:
        raise HTTPException(400, f"rgba data must be {w * h * 4} bytes for {w}x{h}, got {len(raw)}")
    rgba = Image.frombytes("RGBA", (w, h), raw)
    flat = Image.new("RGBA", (w, h), (255, 255, 255, 255))  # transparent canvas pixels print white
    flat.alpha_composite(rgba)
    return flat.convert("L")


def to_bitmap(gray: Image.Image, threshold: int, dither: bool) -> Image.Image:
    if dither:
        return gray.convert("1")
    return gray.point(lambda v: 255 if v >= threshold else 0).convert("1")


async def run(gray: Image.Image, threshold: int, dither: bool, dry_run: bool) -> dict:
    bitmap = to_bitmap(gray, threshold, dither)
    black = sum(1 for v in bitmap.getdata() if v == 0)
    result = {"width": bitmap.width, "height": bitmap.height, "black_pixels": black, "printed": False}
    if dry_run:
        return result
    async with print_lock:
        try:
            async with M110() as printer:
                await printer.print_image(bitmap)
        except RuntimeError as exc:  # printer off / not found
            raise HTTPException(503, str(exc)) from exc
    result["printed"] = True
    return result


@app.get("/canvas")
def canvas() -> dict:
    return {
        "width": GRID_WIDTH,
        "height": GRID_HEIGHT,
        "max_height": MAX_HEIGHT,
        "dpi": 203,
        "origin": "top-left; y increases downward, as the label feeds out",
        "bits": "black prints where the pixel is dark; 1bpp format uses 1 = black, MSB first",
        "formats": ["rgba", "gray8", "1bpp"],
        "note": "images narrower than width are centred on the label",
    }


@app.post("/print")
async def print_pixels(req: PrintRequest) -> dict:
    return await run(decode(req), req.threshold, req.dither, req.dry_run)


@app.post("/print/png")
async def print_png(request: Request, dry_run: bool = False, dither: bool = False, threshold: int = 128) -> dict:
    try:
        img = Image.open(io.BytesIO(await request.body()))
        img.load()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"body is not a readable image: {exc}") from exc
    if img.width > GRID_WIDTH or img.height > MAX_HEIGHT:
        raise HTTPException(400, f"image is {img.width}x{img.height}; max is {GRID_WIDTH}x{MAX_HEIGHT}")
    flat = Image.new("RGBA", img.size, (255, 255, 255, 255))
    flat.alpha_composite(img.convert("RGBA"))
    return await run(flat.convert("L"), threshold, dither, dry_run)


@app.get("/", response_class=HTMLResponse)
def index() -> str:
    return (Path(__file__).parent / "web" / "index.html").read_text()


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8110)
