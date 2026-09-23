"""The deterministic pack — what gets assembled with no AI involved."""

import json
import unittest

from support import TempDbTestCase

from catchup_pack import build_pack
from task_manager import TaskManager


def agenda(*items):
    return json.dumps(list(items))


def item(text, **fields):
    payload = {"text": text, "detail": "", "checked": False, "in_tasks": False}
    payload.update(fields)
    return payload


class BuildPackTests(TempDbTestCase):
    def test_the_07_august_pack_covers_every_meeting_since_the_last_one_to_one(self):
        self.add_meeting("2026-08-04", "Morgan", ai_summary="agreed to deploy Dashboard",
                         agenda_items=agenda(item("Dashboard credentials"),
                                             item("Holiday cover", checked=True)))
        self.add_meeting("2026-08-04", "Jordan Lee", ai_summary="reporting dashboard ownership")
        self.add_meeting("2026-08-05", "Robin van Dijk", ai_summary="competitor intel scope")
        self.add_meeting("2026-08-06", "Chris Baker", ai_summary="dutch transcription quality")
        target = self.add_meeting("2026-08-07", "Morgan")

        pack = build_pack("Morgan", "2026-08-07", exclude_meeting_id=target)
        text = pack.render()

        self.assertEqual(len(pack.window.interim), 3)
        self.assertEqual([c.item["text"] for c in pack.carried], ["Dashboard credentials"])
        self.assertEqual([c.title for c in pack.closed], ["Holiday cover"])
        self.assertIn("Last time — Morgan, 2026-08-04", text)
        self.assertIn("reporting dashboard ownership", text)
        self.assertIn("competitor intel scope", text)
        self.assertIn("dutch transcription quality", text)
        self.assertIn("Still open from last time", text)
        self.assertIn("Holiday cover (ticked off in the meeting)", text)

    def test_headline_counts_read_like_the_panel_header(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1",
                         agenda_items=agenda(item("Open one"), item("Open two")))
        self.add_meeting("2026-08-11", "Casey Smit", ai_summary="Dashboard walkthrough")
        target = self.add_meeting("2026-08-11", "Morgan")

        pack = build_pack("Morgan", "2026-08-11", exclude_meeting_id=target)
        self.assertEqual(pack.headline(), "Since 2026-08-07 — 1 meeting · 2 open items")

    def test_a_task_completed_in_the_window_is_reported_once_not_twice(self):
        task_id = TaskManager.create_task("ProjectAtlas")
        TaskManager.complete_task(task_id)
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1",
                         agenda_items=agenda(item("ProjectAtlas", in_tasks=True,
                                                  task_id=task_id)))
        target = self.add_meeting("2026-08-11", "Morgan")

        pack = build_pack("Morgan", "2026-08-11", exclude_meeting_id=target)
        text = pack.render()

        self.assertEqual([c.title for c in pack.closed], ["ProjectAtlas"])
        self.assertEqual(pack.completed_tasks, [], "already covered by the closed item")
        self.assertEqual(text.count("ProjectAtlas"), 1)

    def test_unrelated_tasks_completed_in_the_window_are_listed_separately(self):
        task_id = TaskManager.create_task("Chase IT for credentials")
        TaskManager.complete_task(task_id)
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1")
        target = self.add_meeting("2026-08-11", "Morgan")

        pack = build_pack("Morgan", "2026-08-11", exclude_meeting_id=target)
        self.assertEqual([t["title"] for t in pack.completed_tasks], ["Chase IT for credentials"])
        self.assertIn("Other tasks completed", pack.render())

    def test_the_pack_still_renders_when_there_is_no_previous_meeting(self):
        target = self.add_meeting("2026-08-11", "Someone New")
        pack = build_pack("Someone New", "2026-08-11", exclude_meeting_id=target)
        text = pack.render()

        self.assertFalse(pack.window.has_anchor)
        self.assertIn("No previous meeting with Someone New", text)
        self.assertIn("None logged.", text)

    def test_a_long_transcript_is_trimmed_so_it_cannot_crowd_out_other_meetings(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1")
        self.add_meeting("2026-08-08", "Rambler", transcript="word " * 4000)
        self.add_meeting("2026-08-09", "Concise", ai_summary="short and useful")
        target = self.add_meeting("2026-08-11", "Morgan")

        text = build_pack("Morgan", "2026-08-11", exclude_meeting_id=target).render()
        self.assertIn("[…trimmed]", text)
        self.assertIn("short and useful", text)

    def test_notes_are_used_when_there_is_no_ai_summary(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1")
        self.add_meeting("2026-08-08", "Handwritten", notes="typed these myself")
        target = self.add_meeting("2026-08-11", "Morgan")

        text = build_pack("Morgan", "2026-08-11", exclude_meeting_id=target).render()
        self.assertIn("typed these myself", text)


if __name__ == "__main__":
    unittest.main()
