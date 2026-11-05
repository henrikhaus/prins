"""Runs briefs through the real internal designer, and reports time, tokens and a contact sheet.

    python scripts/poster_eval.py                   # the held-out briefs, on PRINS_MODEL
    python scripts/poster_eval.py --model claude-sonnet-5-5 --out results.json
    python scripts/poster_sheet.py results.json sheet.png

Needs Anthropic credentials, and spends a little money: about 20 small calls.
"""

from __future__ import annotations

import argparse
import json
import statistics
import time
from pathlib import Path

import anthropic

from prins.design.designer import Designer


class _Recording:
    """Passes calls through, and notes what each one took and what the model sent."""

    def __init__(self, client: anthropic.Anthropic) -> None:
        self.messages = self
        self._create = client.messages.create
        self.calls: list[dict] = []

    def create(self, **kwargs):
        started = time.perf_counter()
        response = self._create(**kwargs)
        tool = next((block.input for block in response.content if block.type == "tool_use"), {})
        self.calls.append({
            "seconds": time.perf_counter() - started,
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
            "input": tool,
        })
        return response


def main() -> None:
    here = Path(__file__).parent
    parser = argparse.ArgumentParser()
    parser.add_argument("--briefs", default=str(here / "poster_briefs.json"))
    parser.add_argument("--model", default="claude-haiku-5-5")
    parser.add_argument("--out", default="poster_results.json")
    args = parser.parse_args()

    recording = _Recording(anthropic.Anthropic(timeout=30.0))
    designer = Designer(recording, args.model)
    results = []
    for brief in json.loads(Path(args.briefs).read_text()):
        before = len(recording.calls)
        started = time.perf_counter()
        bitmap = designer.design(brief)
        calls = recording.calls[before:]
        results.append({
            "name": brief[:40],
            "input": calls[-1]["input"] if calls else {},
            "seconds": round(time.perf_counter() - started, 2),
            "model_seconds": round(sum(c["seconds"] for c in calls), 2),
            "calls": len(calls),
            "output_tokens": sum(c["output_tokens"] for c in calls),
            "drew": bitmap is not None,
        })
        last = results[-1]
        print(f"{last['seconds']:5.2f}s  {last['calls']} call  {last['output_tokens']:4d} out  {brief[:50]}  {json.dumps(last['input'], ensure_ascii=False)[:90]}")
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"\nMedian {statistics.median(r['seconds'] for r in results):.2f}s total, "
          f"{statistics.median(r['model_seconds'] for r in results):.2f}s in the model, "
          f"{statistics.median(r['output_tokens'] for r in results):.0f} output tokens. "
          f"{sum(r['drew'] for r in results)}/{len(results)} drew.")


if __name__ == "__main__":
    main()
