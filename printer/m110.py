# /// script
# requires-python = ">=3.10"
# dependencies = ["bleak", "pillow"]
# ///
"""Print to a Clas Ohlson M110 label printer over BLE.

Protocol (Phomemo-style ESC/POS raster) confirmed by a real test print on 2026-11-05:
  write to FF02, notifications on FF03; each command is acked with `01 01`.
Unconfirmed: meaning of `01 07` / `02 b6 00` (reply to the speed command) and of
`1a 0f 0c` (sent ~2.4 s after the last command, probably "print done").

CLI:
  uv run m110.py calibrate [--width-bytes 48]
  uv run m110.py text "Hello" [--size 48]
  uv run m110.py image path/to/file.png
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass, field

from bleak import BleakClient, BleakScanner
from PIL import Image, ImageDraw, ImageFont

DEFAULT_NAME = "Q199E63C4390578"
WRITE_UUID = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY_UUID = "0000ff03-0000-1000-8000-00805f9b34fb"

MEDIA_GAP_LABEL = 0x0A  # observed to work with the gap-label roll in use
DONE_REPLY = bytes.fromhex("1a0f0c")  # inferred: print finished


@dataclass
class M110:
    """Async context manager: `async with M110() as p: await p.print_image(img)`."""

    target: str = DEFAULT_NAME
    width_bytes: int = 48  # raster row width in bytes (8 px each); 384 px is accepted
    label_px: int = 312  # printable label width; ~40 mm roll, estimated from photos (+/- ~3 px)
    top_pad_px: int = 20  # blank leading rows; the first ~18 rows printed fell before the label
    density: int = 0x0A
    speed: int = 0x05
    replies: list[bytes] = field(default_factory=list)
    _client: BleakClient | None = None
    _done: asyncio.Event = field(default_factory=asyncio.Event)

    async def __aenter__(self) -> "M110":
        device = await BleakScanner.find_device_by_filter(
            lambda d, adv: self.target in (d.address, d.name, adv.local_name), timeout=15
        )
        if device is None:
            raise RuntimeError(f"printer {self.target!r} not found (is it on and not connected to the phone?)")
        client = BleakClient(device)
        await client.connect()
        await client.start_notify(NOTIFY_UUID, self._on_notify)
        self._client = client
        return self

    async def __aexit__(self, *_: object) -> None:
        if self._client:
            await self._client.disconnect()

    def _on_notify(self, _: object, data: bytearray) -> None:
        reply = bytes(data)
        self.replies.append(reply)
        if reply == DONE_REPLY:
            self._done.set()

    async def _send(self, payload: bytes, pause: float = 0.05) -> None:
        assert self._client
        chunk = max(20, self._client.mtu_size - 3)
        for i in range(0, len(payload), chunk):
            await self._client.write_gatt_char(WRITE_UUID, payload[i : i + chunk], response=False)
            await asyncio.sleep(pause)

    def prepare(self, img: Image.Image) -> Image.Image:
        """Fit into the label area, centre it, pad to the full head width, convert to 1-bit.

        Measured from a calibration print: the 40 mm label covers only the last ~320 of the
        384 head columns, so the left 64 px would be lost. Padding to a full row also avoids
        relying on where the printer places narrower rasters (it seemed to right-align them).
        """
        head_px = self.width_bytes * 8
        img = img.convert("L")
        if img.width > self.label_px:
            img = img.resize((self.label_px, round(img.height * self.label_px / img.width)), Image.LANCZOS)
        canvas = Image.new("L", (head_px, img.height + self.top_pad_px), 255)
        canvas.paste(img, (head_px - self.label_px + (self.label_px - img.width) // 2, self.top_pad_px))
        return canvas.convert("1")

    async def print_image(self, img: Image.Image, wait: float = 8.0) -> None:
        img = self.prepare(img)
        row_bytes = (img.width + 7) // 8
        # Pillow packs 1-bit MSB first with 1 = white; the printer wants 1 = black.
        data = bytes(b ^ 0xFF for b in img.tobytes())
        h = img.height
        self._done.clear()
        await self._send(bytes([0x1B, 0x4E, 0x0D, self.speed]))
        await self._send(bytes([0x1B, 0x4E, 0x04, self.density]))
        await self._send(bytes([0x1F, 0x11, MEDIA_GAP_LABEL]))
        header = bytes([0x1D, 0x76, 0x30, 0x00, row_bytes & 0xFF, row_bytes >> 8, h & 0xFF, h >> 8])
        await self._send(header + data)
        await self._send(bytes.fromhex("1ff00500"))
        await self._send(bytes.fromhex("1ff00300"))
        try:
            await asyncio.wait_for(self._done.wait(), wait)
        except asyncio.TimeoutError:
            pass  # completion reply is only inferred; don't fail the print on it

    async def print_text(self, text: str, size: int = 48) -> None:
        font = ImageFont.load_default(size=size)
        probe = ImageDraw.Draw(Image.new("L", (1, 1)))
        l, t, r, b = probe.multiline_textbbox((0, 0), text, font=font)
        img = Image.new("L", (r - l + 16, b - t + 16), 255)
        ImageDraw.Draw(img).multiline_text((8 - l, 8 - t), text, font=font, fill=0)
        await self.print_image(img)


def calibration_image(width_bytes: int, height: int = 240) -> Image.Image:
    """Full-width frame with ticks every 8 px (long every 64) and L/R markers.

    Wastes a label and gets clipped by it; prefer printing a normal image with a border.
    """
    w = width_bytes * 8
    img = Image.new("L", (w, height), 255)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, w - 1, height - 1], outline=0, width=2)
    for x in range(0, w, 8):
        d.line([x, 0, x, 24 if x % 64 == 0 else 10], fill=0)
    font = ImageFont.load_default(size=28)
    d.text((10, 60), "L", font=font, fill=0)
    d.text((w - 36, 60), "R", font=font, fill=0)
    d.text((w // 2 - 60, 110), f"{w}px", font=font, fill=0)
    return img


async def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--target", default=DEFAULT_NAME)
    ap.add_argument("--width-bytes", type=int, default=48)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("calibrate")
    t = sub.add_parser("text")
    t.add_argument("text")
    t.add_argument("--size", type=int, default=48)
    i = sub.add_parser("image")
    i.add_argument("path")
    args = ap.parse_args()

    async with M110(args.target, args.width_bytes) as p:
        if args.cmd == "calibrate":
            await p.print_image(calibration_image(args.width_bytes))
        elif args.cmd == "text":
            await p.print_text(args.text, args.size)
        else:
            await p.print_image(Image.open(args.path))
        print("replies:", " | ".join(r.hex(" ") for r in p.replies))


if __name__ == "__main__":
    asyncio.run(main())
