from __future__ import annotations

from prins.device import CardView, StatusView
from prins.printers import PrintError


def test_empty_queue_shows_all_clear(rig):
    assert isinstance(rig.device.current, CardView)
    assert rig.device.current.title == "All clear"
    assert rig.device.current.queue == 0


def test_screen_shows_message_source_and_queue_size(rig):
    rig.message("Please send the numbers.", sender="Maria")
    rig.message("Call the bank.", source="email", sender="Jonas")
    view = rig.device.current
    assert (view.source, view.sender, view.queue) == ("slack", "Maria", 2)
    assert view.title == "Please send the numbers."


def test_confirm_prints_and_advances(rig):
    rig.message("First.")
    rig.message("Second.")
    rig.device.click("confirm")
    assert len(rig.printer.printed) == 1
    assert rig.device.current.title == "Second."
    assert rig.device.current.queue == 1
    assert rig.store.stats()["printed"] == 1


def test_dismiss_does_not_print_and_is_recorded(rig):
    rig.message("First.")
    rig.device.click("dismiss")
    assert rig.printer.printed == []
    assert rig.store.stats()["dismissed"] == 1
    assert rig.device.current.title == "All clear"


def test_buttons_with_an_empty_queue_do_nothing(rig):
    rig.device.click("confirm")
    rig.device.click("dismiss")
    assert rig.printer.printed == []


def test_failed_print_keeps_the_note_queued(rig):
    rig.message("Important.")
    rig.printer.error = PrintError("out of paper")
    rig.device.click("confirm")
    assert isinstance(rig.device.current, StatusView)
    assert "out of paper" in rig.device.current.detail
    assert rig.store.stats()["queued"] == 1

    rig.printer.error = None
    rig.clock.now += 10
    rig.engine.refresh()
    assert rig.device.current.title == "Important."
    rig.device.click("confirm")
    assert len(rig.printer.printed) == 1


def test_urgent_arrival_does_not_swap_the_card_under_your_thumb(rig):
    rig.engine.store.add(source="email", sender="A", raw_text="x", title="On screen", priority="low")
    rig.engine.refresh()
    assert rig.device.current.title == "On screen"

    rig.engine.store.add(source="email", sender="B", raw_text="y", title="Urgent", priority="high")
    rig.engine.refresh()
    assert rig.device.current.title == "On screen"
    assert rig.device.current.queue == 2

    # It still goes first once the current card is decided.
    rig.engine.store.add(source="email", sender="C", raw_text="z", title="Normal", priority="normal")
    rig.device.click("dismiss")
    assert rig.device.current.title == "Urgent"


def test_duplicates_are_ignored(rig):
    rig.message("Same.", external_id="abc")
    rig.message("Same.", external_id="abc")
    assert rig.device.current.queue == 1


def test_a_message_that_is_not_a_task_never_reaches_the_queue(rig):
    class NotATask:
        def message(self, **_):
            from prins.triage import TriageResult

            return TriageResult(is_task=False, title="FYI")

    rig.engine.triage = NotATask()
    rig.message("Lunch is at noon.")
    assert rig.device.current.title == "All clear"
    assert rig.store.stats()["ignored"] == 1


# --- dictation -----------------------------------------------------------------------


def test_talk_button_records_while_held(rig):
    rig.device.press("talk", True)
    assert rig.dictation.calls == ["toggle"]
    assert rig.device.current.kind == "listening"
    rig.clock.now += 2
    rig.device.press("talk", False)
    assert rig.dictation.calls == ["toggle", "toggle"]
    assert rig.device.current.kind == "thinking"


def test_an_accidental_tap_is_cancelled(rig):
    rig.hold_talk(seconds=0.05)
    assert rig.dictation.calls == ["toggle", "cancel"]
    assert rig.device.current.title == "All clear"


def test_transcript_from_the_talk_button_becomes_a_note_and_is_not_pasted(rig):
    rig.hold_talk()
    assert rig.engine.hook_transcript("Book the dentist.") == ""
    assert rig.device.current.source == "voice"
    assert rig.device.current.title == "Book the dentist."


def test_transcript_from_handys_own_hotkey_passes_through(rig):
    assert rig.engine.hook_transcript("Dear team,") == "Dear team,"
    assert rig.device.current.title == "All clear"


def test_only_one_transcript_is_captured_per_press(rig):
    rig.hold_talk()
    assert rig.engine.hook_transcript("For the queue.") == ""
    assert rig.engine.hook_transcript("For my document.") == "For my document."


def test_late_transcript_is_not_swallowed(rig):
    rig.hold_talk()
    rig.clock.now += 100
    rig.engine.refresh()
    assert rig.device.current.kind == "error"
    assert rig.engine.hook_transcript("Typed later.") == "Typed later."


def test_buttons_are_ignored_while_listening(rig):
    rig.message("On screen.")
    rig.device.press("talk", True)
    rig.device.click("confirm")
    rig.device.click("dismiss")
    assert rig.printer.printed == []
    assert rig.store.stats()["queued"] == 1


def test_a_lost_release_cannot_block_the_queue_forever(rig):
    rig.message("On screen.")
    rig.device.press("talk", True)
    rig.clock.now += 200
    rig.engine.refresh()
    assert rig.dictation.calls == ["toggle", "cancel"]
    rig.clock.now += 10
    rig.engine.refresh()
    assert rig.device.current.title == "On screen."
    rig.device.click("confirm")
    assert len(rig.printer.printed) == 1


def test_missing_handy_shows_an_error_instead_of_listening(rig):
    rig.dictation.works = False
    rig.device.press("talk", True)
    assert rig.device.current.kind == "error"
    rig.device.press("talk", False)
    assert rig.dictation.calls == ["toggle"]


def test_voice_dictation_with_several_tasks_makes_several_notes(rig):
    from prins.triage import TriageResult

    class TwoTasks:
        def dictation(self, _text):
            return [TriageResult(True, "Call Sam"), TriageResult(True, "Pay invoice")]

    rig.engine.triage = TwoTasks()
    rig.hold_talk()
    rig.engine.hook_transcript("um call sam and also pay that invoice")
    assert rig.device.current.queue == 2
