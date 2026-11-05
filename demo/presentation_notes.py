"""Draws the example notes on the presentation's use-case slide with the real design engine.

Run from the repo root: python demo/presentation_notes.py
"""

from __future__ import annotations

from pathlib import Path

from prins.design.canvas import Canvas

OUT = Path("dashboard/public/presentation")


def text(s, x, y, w, h, font="display", **extra):
    return {"op": "text", "s": s, "x": x, "y": y, "w": w, "h": h, "font": font, **extra}


def rect(x, y, w, h, **extra):
    return {"op": "shape", "kind": "rect", "x": x, "y": y, "w": w, "h": h, **extra}


def dot(x, y, size, fill=True, **extra):
    return {"op": "shape", "kind": "ellipse", "x": x, "y": y, "w": size, "h": size, "fill": fill, **extra}


def hazard(y):
    return {"op": "pattern", "name": "stripes:9", "x": 0, "y": y, "w": 312, "h": 12}


NOTES = {
    "reply": [
        hazard(0),
        text("REPLY TO", 16, 20, 280, 54),
        rect(0, 80, 312, 84),
        text("NORTHWIND", 12, 86, 288, 72, ink="white"),
        text("Before their board meets", 14, 172, 284, 34, align="l"),
    ],
    "merged": [
        text("feature/search", 62, 2, 200, 22, font="mono-bold", align="l"),
        {"op": "shape", "kind": "curve", "lw": 7, "pts": [[0, 34], [90, 34], [130, 40], [165, 72], [205, 78]]},
        {"op": "shape", "kind": "curve", "lw": 7, "pts": [[0, 122], [90, 122], [130, 116], [165, 84], [205, 78]]},
        rect(200, 74, 66, 9),
        *[dot(x, 24, 20, ink="white") for x in (8, 38, 68)],
        *[dot(x, 24, 20, fill=False, lw=5) for x in (8, 38, 68)],
        *[dot(x, 112, 20, ink="white") for x in (8, 38, 68)],
        *[dot(x, 112, 20, fill=False, lw=5) for x in (8, 38, 68)],
        dot(248, 46, 62),
        dot(263, 61, 32, ink="white"),
        dot(271, 69, 16),
        text("main", 62, 134, 90, 20, font="mono-bold", align="l"),
        text("PR 512 MERGED", 8, 158, 296, 52, font="sans-bold"),
    ],
    "gym": [
        dot(-34, -12, 240),
        text("6", 6, 4, 170, 208, font="sans-bold", ink="white"),
        text("GYM", 196, 10, 108, 62, font="sans-bold"),
        text("Tomorrow, before work", 214, 136, 90, 70, font="hand", align="r"),
    ],
    "anniversary": [
        hazard(0),
        hazard(204),
        text("Happy\nanniversary", 12, 18, 188, 112, font="script", align="l"),
        text("10 years to my wife", 14, 134, 180, 26, align="l"),
        {"op": "frame", "name": "stamp", "x": 214, "y": 20, "w": 84, "h": 92},
        {"op": "figure", "name": "ring", "x": 226, "y": 34, "w": 60, "h": 64},
        {"op": "pattern", "name": "waves:6", "x": 196, "y": 138, "w": 116, "h": 58},
        dot(162, 128, 66, ink="white"),
        dot(162, 128, 66, fill=False, lw=3),
        dot(168, 134, 54, fill=False),
        text("PRINS\n5 NOV", 170, 142, 50, 38),
    ],
    "ticket": [
        {"op": "shape", "kind": "rrect", "x": 2, "y": 2, "w": 308, "h": 212, "r": 12, "fill": False, "lw": 3},
        {"op": "shape", "kind": "rrect", "x": 2, "y": 2, "w": 308, "h": 38, "r": 12},
        rect(2, 26, 308, 14),
        text("CONCERT", 14, 6, 180, 30, align="l", ink="white"),
        text("ROCKEFELLER", 14, 44, 206, 50, align="l"),
        rect(14, 94, 206, 2),
        text("14 MARCH", 14, 98, 206, 44, align="l"),
        text("DOORS", 14, 142, 60, 14, align="l", font="sans-bold"),
        text("19:30", 14, 154, 90, 26, align="l"),
        text("ROW 4", 120, 154, 90, 26, align="l"),
        {"op": "pattern", "name": "vlines:3", "x": 14, "y": 184, "w": 206, "h": 22},
        {"op": "shape", "kind": "line", "lw": 2, "pts": [[232, 40], [232, 214]], "ink": "dots:3"},
        text("SEAT", 240, 48, 60, 20, align="l", font="sans-bold"),
        text("12", 240, 68, 62, 60, align="l"),
    ],
    "moon": [
        {"op": "pattern", "name": "rays:22", "x": 130, "y": 0, "w": 182, "h": 216},
        text("TO", 8, 6, 124, 64, align="l"),
        text("THE", 8, 72, 124, 64, align="l"),
        text("MOON", 8, 138, 124, 72, align="l"),
        dot(152, 34, 148, ink="white"),
        {"op": "figure", "name": "rocket", "x": 164, "y": 42, "w": 128, "h": 132},
    ],
}

for name, ops in NOTES.items():
    canvas = Canvas()
    canvas.apply_all(ops)
    canvas.image.convert("1").save(OUT / f"{name}.png")
