# Hardware

## What is in the kit, and what is not

The Atech kit covers the board, screen and buttons. **The printer is a separate Clas Ohlson M110 label printer**, driven over Bluetooth from the Mac by the code in `printer/`. Its adhesive labels are the sticky notes.

```sh
cd printer && uv run server.py     # In its own terminal. Keep the printer on and off the phone app.
PRINS_PRINTER=m110                 # In .env
prins test-print
```

Without a printer, `PRINS_PRINTER=preview` saves each note as a PNG. The rest of this page, from "Choosing a printer" on, covers the alternatives to the M110.

## Default layout (14-port board)

| Port | Module | `atech` id | Why here |
|---|---|---|---|
| 1-2 | Big Screen, 320x240 | `st7789_tft` | Hardware SPI, upright with rotation 1 |
| 3 | Thermal printer wiring | `thermal_printer` (ours) | Ports 3 and 4 are the only UART ports |
| 9 | Button: talk | `button` | |
| 10 | Button: confirm (green) | `button` | |
| 11 | Button: dismiss (red) | `button` | |

Your layout can differ. Change `firmware-prins/project.yaml` and run `atech upload firmware-prins` again. Run `atech view firmware-prins` to see the board in 3D and compare it with the one in your hand.

Other kits:
- **10-port board:** set `board: 10port` and put the printer on port 4, its UART port.
- **Small Color Display only:** the card layout assumes 320x240 and needs adjusting for 160x80.
- **Fewer than three buttons:** `getGesture()` can make one button do both jobs, for example tap to print and long press to dismiss. This is not built yet.
- **Coloured button lights** need V2.0 buttons. On older ones the calls do nothing, so label them.

## Bring-up, in order

Each step has one pass condition. Don't move on until it passes.

**Setup**

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev,slack]"
source .venv/bin/activate   # atech needs PlatformIO on PATH, which this provides
prins doctor
```

**1. Board on USB.** Run `atech ports`. *Pass: it lists a `/dev/cu.usbmodem...` port.* If not, try another cable, since many are charge-only, and avoid hubs.

**2. Flash.** Run `atech upload firmware-prins`, then `atech check`. *Pass: `atech check` reports the modules.* It cannot detect the screen or printer, because they have no read-back, so a pass here doesn't prove they work.

**3. Screen and buttons.** Run `prins screen-test`. *Pass: all seven screens are readable and the right way up, and each button prints its own name.* If the screen is upside down, change `setRotation(1)` to `3` in `project.yaml`. If names are swapped, fix the ports.

**4. The whole loop, without paper.** In one terminal run `prins run`. In another:

```sh
prins send "Can you send me the Q3 numbers before Friday?" --source slack --sender "Maria"
```

*Pass: the card appears with its source and queue size, green writes a PNG to `~/.prins/prints/`, and red clears the card.*

**5. Dictation.** Run `scripts/install-handy.sh`, follow its instructions, and keep Handy running. *Pass: holding blue and saying "book the dentist" creates a Voice card, and nothing is pasted anywhere. Handy's own hotkey still pastes normally.* Check whether your first word gets clipped, because starting Handy from a button adds a delay we haven't measured.

**6. The model.** Add `ANTHROPIC_API_KEY` to `.env` and restart. *Pass: a rambling dictation becomes a clean task, and "lunch is at noon" sent with `prins send` never reaches the queue.*

**7. Printer.** See below.

**8. Slack.** See [CONNECTORS.md](CONNECTORS.md).

## Choosing a printer

These are the alternatives to the M110, for a printer built into the product.

| | Embedded TTL printer on the board | Bluetooth or USB printer on the Mac |
|---|---|---|
| Setting | `PRINS_PRINTER=atech` | `PRINS_PRINTER=serial` |
| Fits inside the product | Yes. This is the real product path | No, it's a separate box |
| Sticky paper | **Unverified** in these printers | Phomemo sells sticky rolls for its M02 series |
| Connection | Needs wiring and its own power supply | **Unverified:** see below |
| Use it for | The product | The fastest demo with sticky paper |

**Before you buy, check these:**
- **Sticky paper in an embedded printer** is the biggest open hardware question, since the product is called a sticky note printer. I couldn't confirm that 58 mm adhesive rolls work in these mechanisms. Adhesive can gum up the paper path. Test one before designing around it.
- **Bluetooth printers:** open-source Phomemo drivers document classic Bluetooth RFCOMM, not BLE. A paired printer may appear as `/dev/cu.*` on the Mac, and the code would drive that, but this hasn't been tried. The same projects suggest ESC/POS raster, but one author found standard text commands failed. Dot width also needs confirming, so set `PRINS_PRINTER_DOTS` to match.
- **A printer without a serial port on the Mac** is not supported yet. BLE printers would need a new class in `printers.py`.

## Wiring an embedded TTL printer

**Power comes first, because this is how you can damage something.**

- **Never power the printer from a port.** Ports supply 3.3 V and the printer draws around 2 A at peak. [DFRobot's DFR0503](https://wiki.dfrobot.com/Embedded%20Thermal%20Printer%20-%20TTL%20Serial%20SKU:%20DFR0503-EN) specifies 5-9 V and about 2 A instantaneous, and buyers of similar units advise a supply of at least 3 A.
- **Use a separate 5-9 V supply** and join its ground to the port's GND. Weak power shows up as faded prints.
- **Connect only these two signals.** Leave the printer's TX and the port's Line B disconnected, because that TX line may be 5 V and the ESP32-S3 is a 3.3 V part. As a result the board can't detect "out of paper".

```
Atech port 3              Thermal printer             Supply 5-9 V, 3 A
  Line A (GPIO 17) ---->  RX
  GND ----------------->  GND  <--------------------  GND
                          VH   <--------------------  V+
  3.3V: not connected
  Line B: not connected   TX: not connected
```

**The physical connection to the port is an open question.** Atech says other Arduino modules work, but I found no documentation on the port connector or a breakout. Ask them on [Discord](https://discord.gg/B6kuhUW27S) or at hello@atech.dev before cutting anything.

**Bring-up:**
1. Hold the printer's feed button while powering it on to print a self-test page. It shows the baud rate. *Pass: the page is dark and clean.*
2. Set `PRINS_PRINTER=atech` and `PRINS_PRINTER_BAUD` in `.env`.
3. Run `prins test-print`. *Pass: a sharp note with "Æ Ø Å ß é ñ" legible.*
4. Garbage means the wrong baud rate. Missing bands or a skewed image means data is arriving too fast, so lower `PRINS_PRINTER_BYTES_PER_SEC`. Faded means weak power.

## From kit to sellable product

- **Single-board layout:** the kit proves demand, but module prices alone won't support a mass-market price. A volume product needs a custom board.
- **Compliance:** selling finished electronics usually requires CE or FCC approval, and the kit's status may not carry over. Get advice before shipping units to customers.
- **Standalone mode:** today the Mac runs everything. The board can do WiFi, but the Atech SDK only carries USB, so standalone operation is real engineering work. Atech's microphone module could replace the Mac's microphone in that version.
