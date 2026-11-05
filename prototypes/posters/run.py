"""Renders every poster, checks it against the real wire format, times it, makes a contact sheet."""
import json
import sys
import time
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).parent))
from kit import finish  # noqa: E402
from posters import POSTERS  # noqa: E402
from prins.design.canvas import bitmap_to_image, image_to_bitmap  # noqa: E402

out = Path(__file__).parent / "out"
out.mkdir(exist_ok=True)
only = set(sys.argv[1:])
timings = {}
for fn in POSTERS:
    if only and fn.__name__ not in only:
        continue
    started = time.perf_counter()
    image = finish(fn())
    timings[fn.__name__] = round((time.perf_counter() - started) * 1000)
    assert image.size == (312, 216) and image.mode == "1"
    assert bitmap_to_image(image_to_bitmap(image)).tobytes() == image.tobytes()
    image.save(out / f"{fn.__name__}.png")
    print(fn.__name__, timings[fn.__name__], "ms")

timing_file = out / "timings.json"
known = json.loads(timing_file.read_text()) if timing_file.exists() else {}
known.update(timings)
timing_file.write_text(json.dumps(known))

names = [fn.__name__ for fn in POSTERS]
cols, scale, gap = 3, 2, 14
rows = (len(names) + cols - 1) // cols
sheet = Image.new("L", (cols * (312 * scale + gap) + gap, rows * (216 * scale + gap) + gap), 120)
for i, name in enumerate(names):
    path = out / f"{name}.png"
    if path.exists():
        im = Image.open(path).convert("L").resize((312 * scale, 216 * scale), Image.NEAREST)
        sheet.paste(im, (gap + (i % cols) * (312 * scale + gap), gap + (i // cols) * (216 * scale + gap)))
sheet.save(out / "sheet.png")
