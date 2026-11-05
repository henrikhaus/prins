# /// script
# requires-python = ">=3.10"
# dependencies = ["bleak"]
# ///
"""Connect to a BLE device and dump its GATT services, characteristics and readable values.

Read-only: never writes to a characteristic. Usage: gatt_dump.py <address-or-name>
"""
import asyncio
import sys

from bleak import BleakClient, BleakScanner


async def main(target: str) -> None:
    device = await BleakScanner.find_device_by_filter(
        lambda d, adv: target in (d.address, d.name, adv.local_name), timeout=15
    )
    if device is None:
        sys.exit(f"device {target!r} not found")
    async with BleakClient(device) as client:
        print(f"connected: {client.is_connected}  mtu: {client.mtu_size}")
        for service in client.services:
            print(f"\nservice {service.uuid}  ({service.description})")
            for char in service.characteristics:
                props = ",".join(char.properties)
                line = f"  char {char.uuid}  [{props}]  handle={char.handle}"
                if "read" in char.properties:
                    try:
                        value = await client.read_gatt_char(char)
                        line += f"\n    value: {bytes(value).hex()}  {bytes(value)!r}"
                    except Exception as exc:  # noqa: BLE001
                        line += f"\n    read failed: {exc}"
                print(line)
                for desc in char.descriptors:
                    print(f"    desc {desc.uuid}")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1]))
