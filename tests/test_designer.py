"""The internal designer, with the real SDK against a fake API, so the requests are the real ones."""

from __future__ import annotations

import json

import anthropic
import httpx2

from prins.design.canvas import bitmap_to_image
from prins.design.designer import Designer
from prins.triage import Triage, TriageResult


def scripted_client(turns: list, seen: list):
    def handler(request: httpx2.Request) -> httpx2.Response:
        seen.append(json.loads(request.content))
        blocks, stop = turns[min(len(seen) - 1, len(turns) - 1)]
        return httpx2.Response(200, json={
            "id": "m", "type": "message", "role": "assistant", "model": "claude-haiku-5-5",
            "content": blocks, "stop_reason": stop, "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 10},
        })

    return anthropic.Anthropic(api_key="t", max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(handler)))


def tool_use(name: str, args: dict, id_: str = "t1") -> dict:
    return {"type": "tool_use", "id": id_, "name": name, "input": args}


DONE = ([{"type": "text", "text": "Done."}], "end_turn")


def test_draws_with_the_shared_tools_and_stops():
    seen: list = []
    client = scripted_client([
        ([tool_use("draw_batch", {"ops": [{"op": "figure", "name": "heart"}, {"op": "frame", "name": "double"}]})], "tool_use"),
        DONE,
    ], seen)
    bitmap = Designer(client).design("a heart with a border")
    assert bitmap_to_image(bitmap).convert("L").histogram()[0] > 1000
    assert len(seen) == 2
    assert seen[0]["model"] == "claude-haiku-5-5" and seen[0]["output_config"]["effort"] == "low"
    names = {tool["name"] for tool in seen[0]["tools"]}
    assert "draw_batch" in names and "print_note" not in names and "draw_image" not in names


def test_a_tool_error_goes_back_so_the_model_can_fix_it():
    seen: list = []
    client = scripted_client([
        ([tool_use("draw_figure", {"name": "nope"})], "tool_use"),
        ([tool_use("draw_figure", {"name": "heart"}, "t2")], "tool_use"),
        DONE,
    ], seen)
    assert Designer(client).design("heart") is not None
    result = seen[1]["messages"][-1]["content"][0]
    assert result["is_error"] is True and "catalog" in result["content"]


def test_parallel_tool_calls_all_get_one_result_message():
    seen: list = []
    client = scripted_client([
        ([tool_use("draw_figure", {"name": "heart", "w": 50, "h": 50}, "a"), tool_use("draw_text", {"s": "hi", "x": 60, "w": 100, "h": 50}, "b")], "tool_use"),
        DONE,
    ], seen)
    Designer(client).design("x")
    content = seen[1]["messages"][-1]["content"]
    assert [c["tool_use_id"] for c in content] == ["a", "b"]


def test_it_gives_up_after_a_few_turns_so_cost_is_bounded():
    seen: list = []
    client = scripted_client([([tool_use("draw_figure", {"name": "heart"})], "tool_use")], seen)
    assert Designer(client).design("x") is not None
    assert len(seen) == 4


def test_no_drawing_or_an_api_error_means_the_plain_layout():
    assert Designer(scripted_client([DONE], [])).design("x") is None
    assert Designer(None).design("x") is None

    def fail(request):
        return httpx2.Response(500, json={"type": "error", "error": {"type": "api_error", "message": "no"}})

    client = anthropic.Anthropic(api_key="t", max_retries=0, http_client=httpx2.Client(transport=httpx2.MockTransport(fail)))
    assert Designer(client).design("x") is None


def test_it_cant_read_files_even_if_the_brief_tries(tmp_path):
    seen: list = []
    client = scripted_client([
        ([tool_use("draw_svg", {"src": str(tmp_path / "secret.svg")})], "tool_use"),
        DONE,
    ], seen)
    assert Designer(client).design("show my secret") is None
    assert seen[1]["messages"][-1]["content"][0]["is_error"] is True


def test_dictation_asking_for_a_design_uses_the_designer(rig):
    class Tracker:
        def __init__(self):
            self.briefs = []

        def design(self, brief):
            from prins.design.canvas import Canvas

            self.briefs.append(brief)
            canvas = Canvas()
            canvas.apply({"op": "figure", "name": "cake"})
            return canvas.bitmap()

    class WantsCake:
        def dictation(self, _text):
            return [TriageResult(True, "Sam's birthday", design_brief="a cake with candles")]

    designer = Tracker()
    rig.engine.triage, rig.engine.designer = WantsCake(), designer
    rig.hold_talk()
    rig.engine.hook_transcript("print a birthday card for Sam with a cake")
    assert designer.briefs == ["a cake with candles"]
    assert rig.device.current.bitmap


def test_ordinary_dictation_spends_nothing_on_design(rig):
    class Tracker:
        def design(self, brief):
            raise AssertionError("should not run")

    rig.engine.designer = Tracker()
    rig.hold_talk()
    rig.engine.hook_transcript("Book the dentist.")
    assert rig.device.current.bitmap == ""


def test_a_brief_comes_through_triage():
    reply = {"notes": [{"title": "Card for Sam", "detail": "", "priority": "normal", "due": "", "design_brief": "cake"}]}
    client = scripted_client([([{"type": "text", "text": json.dumps(reply)}], "end_turn")], [])
    assert Triage(client).dictation("a card for sam with a cake")[0].design_brief == "cake"
