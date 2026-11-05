# Prins

Built for the DNB × Founders Hub hackathon on 5 November 2026.

Prins is a tiny sticky note printer with a screen and three buttons. It turns inbox messages into tasks and lets you design notes by voice. Preview a note on the screen, ask for changes, then press a button to print.

We reverse-engineered a sticker printer's Bluetooth protocol to control every pixel. Each 312x216 black-and-white sticker became a 100% customizable canvas for text, drawings, logos, or anything else we want to put on paper.

**200 messages hit your inbox. Five sticky notes reach your desk.**

- **Screen:** shows the message, where it came from, and how many are waiting.
- **Green:** print it. **Red:** dismiss it. **Blue, held:** dictate a note.
- **Everywhere else:** Handy's hotkey still dictates into any app, like Wispr Flow.
- **Agents:** connect Claude or Codex and say "print the Spotify logo". See [docs/MCP.md](docs/MCP.md).
- **Friends:** add each other on the dashboard, grant permission, and send each other notes.


## Try it now, with no hardware

```sh
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python -e ".[dev,slack]"
source .venv/bin/activate

prins run --device sim
```

In a second terminal, with the same virtualenv active:

```sh
prins send "Can you send me the Q3 numbers before Friday?" --source slack --sender "Maria"
```

Set `PRINS_PRINTER=preview` in `.env` for no printer. In the first terminal, type `c` then Enter to print, or `d` to dismiss. Notes land in `~/.prins/prints/` as PNGs. Add `ANTHROPIC_API_KEY` to `.env` (see `.env.example`) for real triage. Without it, a plain text fallback runs.

## Run it on the kit

Follow **[docs/HARDWARE.md](docs/HARDWARE.md)** step by step. In short:

```sh
atech upload firmware-prins  # The original product's firmware (the label maker's is firmware/, see docs/LABELS.md). The first build downloads the ESP32 compiler, about 5 GB
prins screen-test        # Check the screen and buttons by eye
prins run                # The real thing
```

## Docs

- [Hardware](docs/HARDWARE.md): layout, bring-up, printer choice, wiring
- [Architecture](docs/ARCHITECTURE.md): how it fits together, protocol, security
- [Dictation](docs/DICTATION.md): why Handy, how it connects
- [Connectors](docs/CONNECTORS.md): Slack and email setup
- [Dashboard](dashboard/README.md): the web app, friends, syncing a device, deploying on Dokploy
- [MCP server](docs/MCP.md): connect Claude or Codex, and every drawing tool
- [Printer](printer/README.md): the M110 driver and its reverse-engineered protocol

## Status

| Part | State |
|---|---|
| Queue, buttons, screen logic | Tested |
| Model request and fallback | Tested against the real SDK with a fake server. **Not yet run against the live API** |
| Firmware | Compiles. **Not yet run on a board** |
| Handy integration | Hook script tested. **Not yet run with Handy itself** |
| Printing | Goes through the M110 driver in `printer/`. Tested with its dry run. **Prins hasn't printed on paper yet** |
| Designs and MCP | 312x216 engine and tools tested, including over real stdio and with real logos |
| Slack, email | Tested with fake events. **Not yet run on real accounts** |
| Teams | Not built |
| Dashboard, sync and friends | Tested end to end in Chrome with the real daemon on a simulated device. **Runs locally, not deployed** |

## Development

```sh
pytest
atech validate firmware-prins && atech build firmware-prins
cd dashboard && bun run check
```

Rules for changing firmware are in `atech guide`. Read them first: the main one is never to block `loop()`.
