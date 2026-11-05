# Prins

A desk device: Python daemon on the Mac (`src/prins/`), Atech ESP32-S3 firmware (`firmware/` is the voice label maker, `firmware-prins/` the original queue-and-approve product), web dashboard (`dashboard/`, see its README). Read `docs/ARCHITECTURE.md` first, and `docs/HARDWARE.md` for anything physical.

## Commands

```sh
source .venv/bin/activate      # atech needs PlatformIO from this virtualenv on PATH
pytest
atech validate firmware && atech build firmware        # label maker; firmware-prins/ for the original product
atech upload firmware && atech check
prins labels --dry-run                                  # label maker: hold the talk button, see docs/LABELS.md
prins doctor
```

## Rules

- A note is exactly 312x216, 1 bit, every pixel on or off. That's the M110's calibrated label area, and its API refuses anything wider. The 320x240 is only the board's screen.
- Keep tool definitions in `src/prins/design/tools.py` short: they cost tokens in every request. `tests/test_design.py` caps their size.
- Friends' notes never skip the recipient's button, and permission is checked again at delivery.

- Run `atech guide` before changing firmware. Never block `loop()`, never read `Serial`, and never hardcode GPIO numbers.
- Text sent to the screen must go through `screen_text()`. The board's fonts and JSON reader are ASCII only.
- A successful flash or ack proves nothing about a screen or printer: they have no read-back. Only someone looking at the hardware can confirm those work.
- Never power the printer from a board port. See `docs/HARDWARE.md`.
- Source and sender on a note come from the connector, never from the model. Message text is untrusted.
- Say "sticky note" in anything customer-facing. Post-it is a 3M trademark.
