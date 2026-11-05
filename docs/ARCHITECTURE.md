# Architecture

The Mac runs all the logic. The board is a screen, three buttons and a printer port.

```
 Slack (Socket Mode) ─┐
 Email (read-only IMAP)─┤
 POST /v1/messages ───┤
 (agents, scripts)    ├─► Engine ──► Triage (claude-haiku-5-5, plain text fallback)
                      │     │
 Blue button ► Handy ─┘     ├─► SQLite queue, including every confirm and dismiss
   records, transcribes,    │
   calls the hook           ├─► Screen  ──── JSON over USB ───► Atech board
                            │                                    ▲ buttons
                            └─► Printer: every note is a 312x216, 1-bit grid
                                  ├─ m110: printer/server.py ► Bluetooth ► label printer
                                  ├─ preview: PNG file
                                  ├─ serial: printer on the Mac
                                  └─ atech: board UART ► TTL thermal printer

 Claude, Codex ► prins mcp ► the design tools ► the queue, or a friend through the dashboard
```

The daemon also syncs to the [dashboard](../dashboard/README.md) when `PRINS_CLOUD_URL` and `PRINS_CLOUD_TOKEN` are set. It's optional: the device works the same without it. Every 5 seconds it uploads changed notes and device status, and gets back any decisions made on the web. A repeated command can't print twice, because a note that's no longer queued is left alone.

## Files

| Path | What it does |
|---|---|
| `src/prins/engine.py` | The product logic: queue, screen state, buttons. Start here |
| `src/prins/triage.py` | Prompts, schemas, model call, fallback |
| `src/prins/device.py` | `AtechDevice` for the board, `SimDevice` for no hardware |
| `src/prins/render.py` | Draws the note, encodes ESC/POS |
| `src/prins/printers.py` | The three printer backends |
| `src/prins/handy.py` | Starts and stops Handy |
| `src/prins/server.py` | Local HTTP API |
| `src/prins/connectors/` | Slack and email |
| `src/prins/cloud.py` | Sync with the dashboard |
| `src/prins/design/` | The drawing engine and its tools, shared by MCP and the internal designer |
| `src/prins/mcp_server.py` | The MCP server |
| `printer/` | The M110 driver and its local API |
| `dashboard/` | The web app |
| `firmware/project.yaml` | Screen drawing and the module layout |
| `firmware/my_modules/thermal_printer/` | Rate-limited printer output |
| `scripts/handy-hook.sh` | Bridges Handy's transcript to Prins |

## Board protocol

USB serial, one JSON object per line, capped at 4096 characters. Every action gets an ack.

| Direction | Key | Value |
|---|---|---|
| Mac to board | `ui_card` | `{source, from, title, detail, hint, queue, accent}` |
| Mac to board | `ui_status` | `{title, detail, accent}` fills the screen |
| Mac to board | `ui_design` | `{o, d}`: one piece of a note's bitmap. `ui_card` with `design:1` then shows the note itself |
| Mac to board | `printer_write` | Base64 ESC/POS, at most 2400 bytes decoded. Fails with `busy` when the queue is full |
| Mac to board | `printer_config` | `{baud, bytes_per_sec}` |
| Mac to board | `printer_status` | Answers with the event below |
| Mac to board | `printer_cancel` | Drops whatever is queued |
| Board to Mac | `talk`, `confirm`, `dismiss` | 1 on press, 0 on release |
| Board to Mac | `printer_pending` | Bytes still queued |

## HTTP API

`127.0.0.1:8737`. Every request needs the header `X-Prins-Token`, with the value from `~/.prins/token`.

```sh
curl -H "X-Prins-Token: $(cat ~/.prins/token)" \
  -d '{"text":"Deploy is blocked until you approve the migration","source":"agent","sender":"Claude Code"}' \
  http://127.0.0.1:8737/v1/messages
```

## Decisions worth knowing

- **The card on screen never changes until you decide on it.** An urgent arrival waits. Otherwise you could press print on a note you hadn't read.
- **A queue, not alerts.** Nothing buzzes. The count rises and you go through it when you choose.
- **Notes are images.** Printers have poor font support, so any language prints correctly. The screen uses ASCII, because the board's fonts have no other glyphs and its JSON reader doesn't decode `\uXXXX`. Æ becomes AE on screen only.
- **Failures don't lose anything.** If the model fails, a plain text fallback runs. If printing fails, the note stays queued. If Prins is off, Handy's hook pastes your words as normal.
- **Every confirm and dismiss is stored.** It isn't used yet, but it's the training data for learning what matters to each person.

## Security

- **Messages are untrusted.** They can contain instructions aimed at the model. The system is read-only by design, so the worst outcome is a misleading note, and the printed source and sender come from the connector rather than the model.
- **Only the owner's `:printer:` reaction counts,** otherwise anyone in the workspace could print on your desk.
- **The local API needs a token,** otherwise any website could post to localhost.
- **Email is never modified.** The mailbox opens read-only, and fetches use `BODY.PEEK`.
- **Data leaves the Mac in two ways.** Slack and email text goes to the Anthropic API for triage. If the dashboard is connected, the short note, source and sender go there too, but never the raw message. Audio stays local with Handy's on-device models. Customers will ask, so be ready to explain this.
