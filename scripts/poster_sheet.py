"""Renders a JSON list of poster fields to one contact sheet, to look at what the engine does.

    python scripts/poster_sheet.py cases.json sheet.png [--scale 2]

Each case is the arguments draw_poster takes. Prints which look ran, what it reports, the
share of black ink, the smallest capital height, and how long it took.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw

from prins.design.canvas import Canvas


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("cases")
    parser.add_argument("sheet")
    parser.add_argument("--scale", type=int, default=2)
    parser.add_argument("--columns", type=int, default=3)
    args = parser.parse_args()

    cases = json.loads(Path(args.cases).read_text())
    width, height, gap, label = 312 * args.scale, 216 * args.scale, 12, 18
    rows = (len(cases) + args.columns - 1) // args.columns
    sheet = Image.new("L", (args.columns * (width + gap) + gap, rows * (height + gap + label) + gap), 150)
    draw = ImageDraw.Draw(sheet)
    for index, case in enumerate(cases):
        fields = case.get("input", case)
        name = case.get("name", str(index + 1))
        canvas = Canvas(external=False, sender=case.get("sender", ""))
        started = time.perf_counter()
        canvas.apply({"op": "poster", **fields})
        spent = (time.perf_counter() - started) * 1000
        ink = canvas.image.convert("L").histogram()[0] / (312 * 216)
        report = canvas.report
        flag = " OVER-INK" if ink > 0.6 else ""
        print(f"{index + 1:2d} {name[:26]:26s} {report.look:10s} ink {ink:4.0%}{flag} cap {report.min_cap:3d} {spent:5.0f} ms {' '.join(report.warnings)}")
        x, y = gap + index % args.columns * (width + gap), gap + index // args.columns * (height + gap + label)
        draw.text((x + 2, y + 2), f"{index + 1} {name} [{report.look}]", fill=0)
        sheet.paste(canvas.image.convert("L").resize((width, height), Image.NEAREST), (x, y + label))
    sheet.save(args.sheet)


if __name__ == "__main__":
    main()
