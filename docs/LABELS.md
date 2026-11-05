# Label maker

Hold a button, say what you want on a sticky note, and a drawing agent designs it. Look at it on the board, say more to change it, press a button to print.

```sh
source .venv/bin/activate
prins labels --dry-run     # starts printer/server.py and the board loop; prints nothing
prins labels               # the same, and button 6 prints for real
prins mic-test             # hold button 5, hear what the board's microphone picked up
prins label-draw "a label that says Dentist"   # the agent alone, no hardware
```

Put `ANTHROPIC_API_KEY` in `.env`. Only one program can hold the board's USB port, so stop `mic-test` before `labels`.

## Layout (14-port board)

| Port | Module | Instance | Job |
|---|---|---|---|
| 1-2 | microphone | `microphone` | Streams audio while button 5 is held |
| 4 | button | `discard` | Red when there is a design: throws it away |
| 5 | button | `talk` | Hold to speak. Yellow when you can hold again to edit |
| 6 | button | `printbtn` | Green when there is a design to print |
| 7 | NeoPixel 3x3 | `light` | Status |
| 9-10 | ST7735 160x80 | `screen` | Thumbnail of the design |

Port 12 holds the board's reset button, so no module can go there. The buttons need V2.0 for coloured lights.

## States

| State | Button 5 | Button 6 | Button 4 | Light 7 | Screen |
|---|---|---|---|---|---|
| idle | off | off | off | off | "Hold button 5..." |
| listening | red | off | red if a design exists | off | Listening |
| thinking | glowing yellow | off | red if a design exists | glowing yellow | what it heard |
| ready | yellow | green | red | green | thumbnail |
| printing | off | glowing green | off | glowing green | thumbnail |
| error | yellow | off | red if a design exists | blinking red | reason |

Holding 5 again revises the current design with the new instruction. Button 4 starts over. After a print the design stays, so 6 prints another copy. Errors go back to the resting screen after 8 seconds and never lose the design.

## Flow

```
hold 5 ─► board streams 16 kHz PCM ─► Mac: Whisper (local) ─► text
       let go                                                  │
                                                               ▼
   screen thumbnail ◄─ Mac renders 1-bit PNG ◄─ Claude draws shapes (and sees the current design)
   press 6 ─► POST /print/png on printer/server.py ─► M110 over BLE
```

| File | What it does |
|---|---|
| `firmware/project.yaml` | Microphone streaming, lights, screen |
| `src/prins/labels.py` | The state machine. Start here |
| `src/prins/designer.py` | The drawing agent: prompt, shape schema, retries |
| `src/prins/drawing.py` | Renders shapes to a 1-bit image, checks them, makes the thumbnail |
| `src/prins/stt.py` | Local Whisper (`faster-whisper`) |
| `src/prins/labelboard.py` | Board protocol |
| `src/prins/labelprinter.py` | Printer server client, starts it if needed |
| `src/prins/mictest.py` | `prins mic-test` |

The agent returns the whole design each time as shapes (`text`, `rect`, `ellipse`, `polygon`, `polyline`). Each draw is checked for text running off the label, text under 16 px, a blank label and a mostly black one. Problems go back to the agent for up to two more tries. The spoken text is untrusted: the agent can only return a drawing.

## Board protocol

JSON lines over USB, as in [ARCHITECTURE.md](ARCHITECTURE.md).

| Direction | Key | Value |
|---|---|---|
| Board to Mac | `audio_start` | 1, when talk is pressed |
| Board to Mac | `audio` | Base64 of 1200 little-endian int16 samples, 16 kHz mono (3200 characters) |
| Board to Mac | `audio_end` | `{samples, dropped}`: how many were sent, and how many the board's buffer lost |
| Board to Mac | `talk`, `printbtn`, `discard` | 1 on press, 0 on release |
| Mac to board | `ui_state` | `{state, title, detail, design, preview}`: states above, text through `screen_text()` |
| Mac to board | `ui_preview` | `"W,H:<base64>"`: 2 bits per pixel, four pixels per byte, at most 120x80 |

## Things that bit us

- **The SDK sets `Serial.setTxTimeoutMs(0)`**, so a write that does not fit the board's 256 byte USB buffer is dropped, not delayed. A 3300 character audio line arrived cut off, failed to parse, and was ignored without any error: the recording was 24 ms long. The firmware raises the timeout to 200 ms only while talk is held, then restores 0. Any new long line from the board needs the same.
- **The board listens all the time but sends nothing until talk is held.** It keeps the last 200 ms in RAM so the first word is not clipped, and 250 ms after release so the last one is not cut.
- **Speech engine.** The model downloads on first use (`turbo` is about 1.6 GB). Set `PRINS_STT_MODEL=base` for a small, quicker one. The level is raised before Whisper hears it, and `prins mic-test --boosted` plays that version.
- **No read-back.** `atech check` cannot see the screen, lights or printer. Only someone looking at the hardware can confirm those work.
- **Screen upside down?** Swap `screen.setRotation(1)` and `3` in `project.yaml`. Rotation 1 is right for ports 9-10.
- **The thumbnail is 116x80**, so it shows layout, not readable text. The Big Screen (320x240) would show the label at full size.
