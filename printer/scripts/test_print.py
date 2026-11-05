# /// script
# requires-python = ">=3.10"
# dependencies = ["bleak", "pillow"]
# ///
"""Send a small test bitmap to the M110 and log every notification it returns.

The command sequence is a HYPOTHESIS (Phomemo-style ESC/POS raster), not yet verified.
Usage: test_print.py <address-or-name>
"""
import asyncio
import sys
import time

from bleak import BleakClient, BleakScanner
from PIL import Image, ImageDraw

WRITE = "0000ff02-0000-1000-8000-00805f9b34fb"
NOTIFY = "0000ff03-0000-1000-8000-00805f9b34fb"

T0 = time.monotonic()


def log(direction: str, data: bytes) -> None:
    print(f"{time.monotonic() - T0:6.2f}s {direction} {data.hex(' ')}")


def make_image(width: int = 96, height: int = 96) -> Image.Image:
    img = Image.new("1", (width, height), 1)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, width - 1, height - 1], outline=0, width=3)
    d.line([0, 0, width - 1, height - 1], fill=0, width=2)
    d.text((10, 36), "M110 OK", fill=0)
    return img


def raster_bytes(img: Image.Image) -> bytes:
    """1bpp, MSB first, 1 = black pixel."""
    w, h = img.size
    row_bytes = (w + 7) // 8
    px = img.load()
    out = bytearray()
    for y in range(h):
        for bx in range(row_bytes):
            b = 0
            for bit in range(8):
                x = bx * 8 + bit
                if x < w and px[x, y] == 0:
                    b |= 0x80 >> bit
            out.append(b)
    return bytes(out)


async def main(target: str) -> None:
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: target in (d.address, d.name, adv.local_name), timeout=15
    )
    if device is None:
        sys.exit(f"device {target!r} not found")

    img = make_image()
    w, h = img.size
    row_bytes = (w + 7) // 8
    data = raster_bytes(img)

    async with BleakClient(device) as client:
        await client.start_notify(NOTIFY, lambda _, d: log("<-", bytes(d)))
        chunk = max(20, client.mtu_size - 3)

        async def send(payload: bytes, pause: float = 0.05) -> None:
            for i in range(0, len(payload), chunk):
                part = payload[i : i + chunk]
                log("->", part if len(part) <= 32 else part[:32] + b"...")
                await client.write_gatt_char(WRITE, part, response=False)
                await asyncio.sleep(pause)

        await send(bytes.fromhex("1b4e0d05"))  # print speed
        await send(bytes.fromhex("1b4e040a"))  # density
        await send(bytes.fromhex("1f110a"))  # media type: labels with gaps
        header = bytes([0x1D, 0x76, 0x30, 0x00, row_bytes & 0xFF, row_bytes >> 8, h & 0xFF, h >> 8])
        await send(header + data)
        await send(bytes.fromhex("1ff00500"))
        await send(bytes.fromhex("1ff00300"))
        await asyncio.sleep(5)  # let the printer finish and report


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
