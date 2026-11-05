"""Draws Haiku's actual ops through the project's real Canvas, for an honest 'before'."""
import json
from pathlib import Path

from prins.design.canvas import Canvas

here = Path(__file__).parent
(here / "out").mkdir(exist_ok=True)
for name, ops in json.loads((here / "baseline.json").read_text()).items():
    canvas = Canvas(external=False)
    canvas.apply_all(ops)
    canvas.image.save(here / "out" / f"before_{name}.png")
    print(name, len(json.dumps(ops, separators=(",", ":"))), "chars")
