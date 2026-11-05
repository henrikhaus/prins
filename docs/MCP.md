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
| `draw_poster` | A whole designed note from its meaning. Start here. See below |
| `compare_looks` | The same content in the looks that suit it, as one numbered image |
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

## Posters

`draw_poster` is how a small model makes a note that looks designed. The model says what the note means, and the engine (`design/poster.py`, `design/craft.py`) does the rest:

```json
{"look": "picture", "say": "Bite me", "pic": "🦈"}
```

| Field | What it is |
|---|---|
| `say` | The fewest words that carry the message |
| `sub` | One short line of detail |
| `big` | A number or time to feature |
| `pic` | The subject: any emoji, a word Unicode has an emoji for, or `logo:brand` |
| `data` | Real numbers over time |
| `items` | List entries, or `KEY: VALUE` facts |
| `qr` | A link for a QR code |
| `look` | Which look. Leave it out and the engine chooses |
| `seed` | Another number gives another variation |

There are 18 looks: `block`, `alarm`, `relief`, `monument`, `ransom`, `numeral`, `collide`, `picture`, `engraving`, `stage`, `post`, `ticket`, `rain`, `ridges`, `transit`, `cover`, `list` and `quote`. `catalog` with kind `looks` says when each one fits.

A look solves its own layout for whatever text arrives, so:

- **Words aren't lost.** A field a look can't show moves to one it can. A note that can't fit its text says so.
- **Text stays legible.** If a look can't hold the words at a printable size, or would go over 60% black, the next best look takes over and the result says why.
- **Odd arguments still print.** Only a call with nothing to say is an error.
- **Who a note is from is never the model's to say.** A poster prints FROM only from `PRINS_NAME`.

A poster is an ordinary op, so `draw_batch` can draw on top of one, and `undo`, `save_design` and revising a label all work.

Flag emoji need Pillow built with `raqm`, and without it they fall back to another look. So do right-to-left and other scripts that need shaping, which print with their letters unjoined.

## Keeping it cheap

- **Short definitions.** All tools together are about 9,000 characters, roughly 2,250 tokens by the usual estimate of 4 characters per token. A test holds them under that.
- **Names on demand.** Figure, pattern and font lists sit behind `catalog` instead of in every request.
- **Few tokens per design.** The Spotify note in the tests is 145 characters of JSON. A preview image is small enough to cost little.
- **One call.** `draw_batch` draws a whole design at once, and `repeat` and `scatter` avoid repeating yourself.

## Who can print what

- **Your own agent:** notes wait in the queue for the green button. Set `PRINS_AGENT_AUTO_PRINT=true` to skip it.
- **Friends:** they need your permission, which is off by default and set on the dashboard's Friends page. Their notes **always** wait for your button, and the screen shows the design first. There's a limit of 30 notes per hour per friend.

## The internal designer

When someone dictates something like "make it a card with a cake", the daemon's small model calls `draw_poster` once. Ordinary notes use the plain layout and cost nothing extra.

It gets that one tool and is done as soon as it has drawn. On Haiku the call is forced, which skips thinking. Newer Sonnet and Opus models refuse a forced call, so they get `auto` instead and may think. `scripts/poster_eval.py` measures time and tokens on real briefs.

It's more restricted than an MCP client, because its input can come from someone else: it can't read files, fetch arbitrary URLs, or print. A refused call goes back once, so it makes at most 2 calls.

An MCP client is trusted like any other tool you connect: `draw_image` and `draw_svg` can read local files and URLs on its behalf.
