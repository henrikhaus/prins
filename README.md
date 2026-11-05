# Prins

A tiny sticky note printer with a screen and three buttons. Your inbox and your voice go in, a small model turns them into tasks, and you decide with a button what becomes paper.

**200 messages hit your inbox. Five sticky notes reach your desk.**

- **Screen:** shows the message, where it came from, and how many are waiting.
- **Green:** print it. **Red:** dismiss it. **Blue, held:** dictate a note.
- **Everywhere else:** Handy's hotkey still dictates into any app, like Wispr Flow.


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

In the first terminal, type `c` then Enter to print, or `d` to dismiss. Notes land in `~/.prins/prints/` as PNGs. Add `ANTHROPIC_API_KEY` to `.env` (see `.env.example`) for real triage. Without it, a plain text fallback runs.

## Run it on the kit

Follow **[docs/HARDWARE.md](docs/HARDWARE.md)** step by step. In short:

```sh
atech upload firmware      # The first build downloads the ESP32 compiler, about 5 GB
prins screen-test        # Check the screen and buttons by eye
prins run                # The real thing
```

## Docs

- [Hardware](docs/HARDWARE.md): layout, bring-up, printer choice, wiring
- [Architecture](docs/ARCHITECTURE.md): how it fits together, protocol, security
- [Dictation](docs/DICTATION.md): why Handy, how it connects
- [Connectors](docs/CONNECTORS.md): Slack and email setup

## Status

| Part | State |
|---|---|
| Queue, buttons, screen logic | Tested |
| Model request and fallback | Tested against the real SDK with a fake server. **Not yet run against the live API** |
| Firmware | Compiles. **Not yet run on a board** |
| Handy integration | Hook script tested. **Not yet run with Handy itself** |
| Printing | PNG output works, and ESC/POS bytes are tested. **No real printer yet** |
| Slack, email | Tested with fake events. **Not yet run on real accounts** |
| Teams | Not built |

## Development

```sh
pytest
atech validate firmware && atech build firmware
```

Rules for changing firmware are in `atech guide`. Read them first: the main one is never to block `loop()`.
