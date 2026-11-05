# Poster concepts

The design brainstorm that led to `src/prins/design/poster.py`. Nothing here is wired into Prins: the code is kept as a record of the hand-tuned originals, which the engine's looks now generalize.

Each poster is hand-tuned Python on the real 312x216, 1-bit grid, and is checked against the note wire format. The renders in `out/` are the concepts. `out/before_*.png` shows what Haiku drew for the same briefs using the existing tool definitions.

The idea is to move design craft out of the model and into the engine. The model writes one small JSON object, such as `{"art":"stack","lines":["DEPLOY","BLOCKED"],"sub":"APPROVE THE MIGRATION"}`, and the engine does the rest. `payloads.py` holds a hand-written payload for each poster. These haven't been tried with a model.

```sh
cd prototypes/posters
python run.py         # needs the project's virtualenv, and macOS for the fonts
python baseline.py
python payloads.py
```

Not done yet: printing on real paper.
