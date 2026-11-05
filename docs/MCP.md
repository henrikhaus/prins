# MCP server

Connect Prins to Claude, Codex or any MCP client, and ask your agent to print anything:

> Print the Spotify logo.
>
> Make a birthday card for Sam with a cake and send it to him.
>
> Print a QR code for this link, with a ticket frame.

## Connect it

The server runs on your own machine over stdio. Install the project first (see the README).

**Claude Code**

```sh
claude mcp add prins -- ~/Documents/dev/Personal/prins/.venv/bin/prins mcp
```

**Codex**, in `~/.codex/config.toml`:

```toml
[mcp_servers.prins]
command = "/Users/YOU/Documents/dev/Personal/prins/.venv/bin/prins"
args = ["mcp"]
```

Settings are read from the `.env` in the project folder. Drawing and `preview` work with nothing else running. The rest needs:

| To do this | You need |
|---|---|
| `print_note` | `prins run` running, and for paper, `cd printer && uv run server.py` |
| `list_friends`, `send_to_friend` | `PRINS_CLOUD_URL` and `PRINS_CLOUD_TOKEN`, from the dashboard's Devices page |

## The grid

A note is **312x216 pixels, 1 bit: every pixel is on or off.** That's the M110's calibrated label area. The origin is top-left.

There's no limit on the design, because every pixel is reachable:

| Tool | What it does |
|---|---|
| `draw_logo` | A brand logo by name, from Simple Icons' 3000+ logos |
| `draw_svg` | Any vector: path data, full SVG markup, or a URL or file |
| `draw_image` | Any image or photo by URL, path or base64, dithered to 1 bit |
| `draw_pixels` | Exact pixels: rows of text for pixel art, or a raw bitmap |
| `draw_text` | Any installed font, or a font file. Auto-sizes to its box |
| `draw_figure` | 60 ready-made figures, or any emoji |
| `draw_pattern` | 30 patterns and gradients, or any flat gray tone |
| `draw_frame` | 15 frames. Any figure can also repeat as a border |
| `draw_shape` | Rectangles, ellipses, lines, curves, polygons, arcs |
| `draw_formula` | Per-pixel math, such as `sin(r/6+a*3)>0` |
| `draw_qr` | A scannable QR code |
| `transform` | Invert, flip, rotate, mirror, shift, pixelate or outline a region |
| `draw_batch` | Many steps in one call |
| `preview` | See the note as an image |
| `save_design`, `load_design` | Reuse a design without redrawing it |
| `undo`, `clear`, `catalog` | Step back, start over, list the available names |
| `print_note` | Print on your own Prins |
| `list_friends`, `send_to_friend` | See who you can send to, and send them the note |

Anywhere that takes `ink` accepts `black`, `white`, `invert` or a pattern such as `dots:6`, so text can be filled with a pattern.

## Keeping it cheap

- **Short definitions.** All tools together are about 7,300 characters, roughly 1,800 tokens by the usual estimate of 4 characters per token.
- **Names on demand.** Figure, pattern and font lists sit behind `catalog` instead of in every request.
- **Few tokens per design.** The Spotify note in the tests is 145 characters of JSON. A preview image is small enough to cost little.
- **One call.** `draw_batch` draws a whole design at once, and `repeat` and `scatter` avoid repeating yourself.

## Who can print what

- **Your own agent:** notes wait in the queue for the green button. Set `PRINS_AGENT_AUTO_PRINT=true` to skip it.
- **Friends:** they need your permission, which is off by default and set on the dashboard's Friends page. Their notes **always** wait for your button, and the screen shows the design first. There's a limit of 30 notes per hour per friend.

## The internal designer

When someone dictates something like "make it a card with a cake", the daemon's small model draws it with the same tool definitions. Ordinary notes use the plain layout and cost nothing extra.

It's more restricted than an MCP client, because its input can come from someone else: it can't read files, fetch arbitrary URLs, or print. It stops after 4 turns.

An MCP client is trusted like any other tool you connect: `draw_image` and `draw_svg` can read local files and URLs on its behalf.
