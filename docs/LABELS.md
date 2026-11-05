# Label maker

Hold a button, say what you want on a sticky note, and a drawing agent designs it. Look at it on the board, say more to change it, press a button to print.

```sh
source .venv/bin/activate
prins labels --dry-run     # starts printer/server.py and the board loop; prints nothing
prins labels               # the same, and button 6 prints for real
prins mic-test             # hold button 5, hear what the board's microphone picked up
prins label-draw "a label that says Dentist"   # the agent alone, no hardware
```

The label maker has its own firmware in `firmware/`: `atech upload firmware`. The original queue-and-approve product's firmware is in `firmware-prins/` (a 320x240 screen and different ports), and `prins run` talks to that one. The two cannot be flashed at once and neither daemon works with the other's firmware.

Put `ANTHROPIC_API_KEY` in `.env`. Only one program can hold the board's USB port, so stop `mic-test` before `labels`.

## Layout (14-port board)

| Port | Module | Instance | Job |
|---|---|---|---|
| 1-2 | microphone | `microphone` | Streams audio while button 5 is held |
| 4 | button | `discard` | Red when there is a design: throws it away |
| 5 | button | `talk` | Hold to speak. Yellow when you can hold again to edit |
| 6 | button | `printbtn` | Green when there is a design to print |
| 10-11 | ST7735 160x80 | `screen` | Thumbnail of the design. Middle of the right column, next to the Restart button |

Port 12 holds the board's reset button, so no module can go there, and a two-port module cannot straddle it: the screen's only central spot is 10-11 (13-14 is the other free pair on that side). Port 7 is free. The buttons need V2.0 for coloured lights.

## States

| State | Button 5 | Button 6 | Button 4 | Screen |
|---|---|---|---|---|
| idle | off | off | off | "Hold button 5..." |
| listening | red | off | red if a design exists | Listening |
| thinking | glowing yellow | off | red if a design exists | what it heard |
| ready | yellow | green | red | thumbnail |
| printing | off | glowing green | off | thumbnail |
| error | glowing red | off | red if a design exists | reason |

Holding 5 again revises the current design with the new instruction. Button 4 starts over. After a print the design stays, so 6 prints another copy. Errors go back to the resting screen after 8 seconds and never lose the design.

## Flow

```
hold 5 ─► board streams 16 kHz PCM ─► Mac: Whisper (local) ─► text
       let go                                                  │
                                                               ▼
   screen thumbnail ◄─ Mac renders 1-bit PNG ◄─ Claude draws with the design engine, can search the web,
                                                  and sees the current design
   press 6 ─► POST /print/png on printer/server.py ─► M110 over BLE
```

| File | What it does |
|---|---|
| `firmware/project.yaml` | Microphone streaming, lights, screen |
| `src/prins/labels.py` | The state machine. Start here |
| `src/prins/labeldesigner.py` | The drawing agent: prompt, tool loop, web search, revising |
| `src/prins/design/` | The design engine (figures, logos, SVG, QR, fonts) that the agent draws with |
| `src/prins/sitelogos.py` | Finds a company's own logo on its homepage |
| `src/prins/inbox.py` | Reads one person's Slack DMs through `sz` |
| `src/prins/drawing.py` | Quality checks on a finished design, and the thumbnail |
| `src/prins/stt.py` | Local Whisper (`faster-whisper`) |
| `src/prins/labelboard.py` | Board protocol |
| `src/prins/labelprinter.py` | Printer server client, starts it if needed |
| `src/prins/mictest.py` | `prins mic-test` |

The agent starts with `draw_poster` (see [MCP.md](MCP.md#posters)), can compare looks with `compare_looks`, and reaches for the other tools (`draw_batch`, `draw_logo`, `draw_svg`, `draw_image`, `draw_text`, `preview`, ...) for what a poster can't do. It ends by calling `finish(title, summary)`. A design is the list of ops it drew. Holding talk again puts those ops back on the canvas and gives the agent the picture plus your new instruction. `finish` runs two checks and sends problems back (up to two times): a blank label or one that is more than 60% black, and text under 16 px.

## Web access

When the instruction names a real company, organization, brand, product, place or event, the agent looks it up before it draws, and uses the real logo and wording instead of inventing a generic one. Private people named on a badge are never looked up. The steps:

1. `draw_logo` for a well-known brand (a catalog of 3000+ logos, no search).
2. Otherwise Anthropic's `web_search` finds the company's website (at most 3 searches and 3 page reads per design, about one US cent per search).
3. `find_logo_images` (`src/prins/sitelogos.py`) reads the company's homepage on the Mac and lists candidate logo images, best first: the site's own data, SVG and app icons, then images merely called "logo" (often other companies' customer logos), then the social share image.
4. The agent loads one with `draw_svg` or `draw_image`, checks it with `preview`, and tries the next if it is wrong. If nothing works it sets the name in good type and says no logo was found in the summary.

The agent's tool calls and any errors are in the `prins labels` log. `--no-web` on `prins labels` or `prins label-draw` turns the web off.

Web pages and your words are both untrusted, so the agent can only draw:
- It has no print, save, send or file tools. Nothing prints until you press 6, and you see the thumbnail first.
- Images and SVGs it loads from a URL go through a guard (`check_public_url` in `design/assets.py`): public `http(s)` addresses on ports 80 and 443 only, no logins in the URL, no loopback, home network, link-local or cloud-metadata addresses, and every redirect hop is checked. Local files are refused, and so are SVGs that link to other files.
- It may only load images from sites that appeared in what you said, in search results, or in `find_logo_images` results. `find_logo_images` itself takes a plain homepage address with no query string, fragment or login, because a company's own site is usually learned from text, not from a result address.
- `web_fetch` is told not to treat URLs from the agent's own tool results as fair game.
- A residual risk: the guard resolves the name before downloading, so a hostile DNS server could still swap the address in between.

## Inbox: messages from chosen people

Slack DMs from the people you choose appear on the desk: today Henrik Hausberg and Magnus Krogstad. `prins labels` asks System Zero's `sz` command (already signed in on this Mac) for news once a second, so there is no Slack app, no open port and no webhook.

```
Slack ─► System Zero ─► sz msg ls ─► prins labels ─► agent: task note, design, or skip ─► queue ─► screen
```

- **Who counts.** One entry per person in `PRINS_INBOX` in `.env`, written `USERID:DMID:Name` and separated by semicolons: the person's Slack user id, the id of your DM with them (the end of the DM's Slack URL), and the name printed as the sender. Only messages in that DM from that user id count, not yours, not automated. A display name proves nothing (anyone can copy one), so the ids decide, and a person's id only counts in their own DM. To add someone: open the DM in Slack and copy the id from its URL, and "Copy member ID" from their profile (or read both from `sz msg ls --json`). `prins doctor` lists who is on, and `--no-inbox` turns the inbox off. A new person starts from now: their old messages never print.
- **What it costs System Zero.** Each look is `sz msg ls` for the 2 + N newest conversations (N people), about 13 KB. A new message always makes its conversation the newest, so that is enough. Only when someone's DM has something new does it fetch that thread. After a start it looks wide once (60 conversations), in case the DM was busy while the daemon was off.
- **No replays.** The position is saved in `~/.prins/inbox.json`. The first ever run starts from now, so old DMs never print. Messages that arrived while the daemon was off are picked up when it starts, newest ten, up to a day old.
- **The agent decides what a message becomes** (`design_message` in `labeldesigner.py`): a request or reminder becomes a task note with the action as the headline, in the message's language; a request to make something is designed; chit-chat, thanks, links and codes are skipped and nothing appears.
- **Who it is from is printed by us.** The strip at the bottom of the note (a line and "from Henrik Hausberg") is drawn after the agent is done, over whatever is there, and the agent is told to leave it empty. The sender comes from our settings, never from the model or the message. The message text is untrusted: the agent can only draw.
- **A queue, not a replacement.** A finished message never replaces what is on the screen, yours or another message. The screen shows "+N" for how many wait, and button 4 says "next" when there is one. Discard (4) moves on to the next message. Print (6) prints the one on the screen, and it stays for a second copy. Holding 5 changes it by voice, with the message as the first instruction.
- **Nothing is lost.** If the model is down, or more than 20 messages an hour arrive (`PRINS_INBOX_MAX_PER_HOUR`), the message still arrives, as plain big text with the same footer, and costs nothing.
- **System Zero down?** The log says so once, then every minute, and the poller backs off up to 30 s. It recovers by itself.

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
