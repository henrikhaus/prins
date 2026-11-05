# printer

Reverse-engineered BLE driver, local HTTP API and drawing page for the Clas Ohlson M110 wireless label printer. Each file is a standalone `uv` script, so there is nothing to install. Run everything from this folder.

```sh
uv run server.py              # API + drawing page on http://127.0.0.1:8110 (localhost only)
uv run m110.py text "Hello"   # CLI: text | image <file> | calibrate
uv run scripts/scan.py        # find the printer over BLE
uv run scripts/gatt_dump.py <name-or-address>   # read-only GATT dump
```

The printer must be on and not connected to the phone app. The default target is the BLE name `Q199E63C4390578` (`DEFAULT_NAME` in `m110.py`). Change it for another unit.

## API

| Endpoint | Purpose |
| --- | --- |
| `GET /canvas` | Pixel grid: 312 px wide, 216 rows (max 240), top-left origin, 203 dpi |
| `POST /print` | JSON `{width, height, format, data, threshold?, dither?, dry_run?}`; `data` is base64 `rgba`, `gray8` or `1bpp` (1 = black, MSB first) |
| `POST /print/png` | Raw PNG body; `?dry_run=true`, `?dither=true`, `?threshold=` |
| `GET /` | Minimal drawing page on a 312x216 canvas |

`dry_run` never touches the printer, so use it for testing. Pixels are thresholded to black and white unless `dither` is set. Images narrower than 312 px are centred. Prints are serialised, and each one reconnects (about 5 s). A missing printer returns 503.

## Protocol

Observed with real prints on 2026-11-05. The GATT layout came from a read-only dump.

- Service `0xFF00`: `FF02` is write (no response is fine), `FF03` is notify, `FF01` is read and returns empty. MTU 200.
- Command sequence, all written to `FF02`:
  1. `1b 4e 0d <speed>`
  2. `1b 4e 04 <density>`
  3. `1f 11 0a` (media type: gap labels)
  4. `1d 76 30 00 <row_bytes lo,hi> <rows lo,hi>` followed by 1 bit per pixel, rows top to bottom, 1 = black
  5. `1f f0 05 00`, then `1f f0 03 00`
- The printer sends `01 01` after each write.

Not confirmed: `1a 0f 0c`, which arrives about 2 s after the data (`m110.py` treats it as "print done", but a missing reply never fails a print), and the replies `01 07` and `02 b6 00` to the speed command. The sequence matches the Phomemo family as I recalled it from community docs. The prints are what confirmed it, not those docs.

## Label geometry

Measured from photos of printed calibration frames, with the 40 mm gap-label roll in use:

- Rows are always sent at the full 384 px (48 bytes).
- Only the last 312 px (`label_px`) land on the label. The columns before that fall off its left edge.
- The first ~18 rows printed land before the label starts, so `top_pad_px` adds 20 blank rows.
- A 312x216 frame prints with all four borders visible. The measurement is good to about 3 px.

A different roll width or label height needs `label_px`, `top_pad_px` and `GRID_HEIGHT` / `MAX_HEIGHT` in `server.py` re-measured. Print one bordered image instead of a full-width calibration, because each test uses a label.
