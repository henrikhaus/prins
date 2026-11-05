# /// script
# requires-python = ">=3.10"
# dependencies = ["bleak"]
# ///
"""Scan for nearby BLE devices and print name, address, RSSI, advertised services."""
import asyncio
import sys

from bleak import BleakScanner


async def main(seconds: float) -> None:
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    rows = sorted(found.values(), key=lambda r: r[1].rssi, reverse=True)
    for device, adv in rows:
        name = adv.local_name or device.name or "?"
        print(f"{adv.rssi:>4}  {name:<28} {device.address}")
        if adv.service_uuids:
            print(f"        services: {', '.join(adv.service_uuids)}")
        if adv.manufacturer_data:
            for cid, data in adv.manufacturer_data.items():
                print(f"        mfr 0x{cid:04x}: {data.hex()}")


if __name__ == "__main__":
    asyncio.run(main(float(sys.argv[1]) if len(sys.argv) > 1 else 8.0))
