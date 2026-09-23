"""The progress pack — what a boss-is-back update is assembled from, no AI involved."""

import json
import unittest
from datetime import date

from support import TempDbTestCase

from progress_pack import build_pack, default_range, valid_range
from task_manager import TaskManager


def agenda(*items):
    return json.dumps(list(items))


def item(text, **fields):
    payload = {"text": text, "detail": "", "checked": False, "in_tasks": False}
    payload.update(fields)
    return payload


class DefaultRangeTests(unittest.TestCase):
    def test_the_default_window_is_the_fortnight_ending_today(self):
        start, end = default_range(today=date(2026, 8, 17))
        self.assertEqual((start, end), ("2026-08-04", "2026-08-17"))

    def test_a_backwards_or_unreadable_range_is_rejected(self):
        self.assertTrue(valid_range("2026-08-04", "2026-08-17"))
        self.assertTrue(valid_range("2026-08-17", "2026-08-17"))
        self.assertFalse(valid_range("2026-08-18", "2026-08-17"))
        self.assertFalse(valid_range("", "2026-08-17"))
        self.assertFalse(valid_range("2026-08-17", None))


class BuildPackTests(TempDbTestCase):
    def test_the_pack_covers_every_meeting_in_the_window_whoever_it_was_with(self):
        self.add_meeting("2026-08-05", "Morgan", ai_summary="Dashboard rollout signed off")
        self.add_meeting("2026-08-11", "Jordan Lee", notes="competitor intel scope")
        self.add_meeting("2026-08-17", "Chris Baker", transcript="dutch transcription")

        pack = build_pack("2026-08-04", "2026-08-17")
        text = pack.render()

        self.assertEqual(len(pack.meetings), 3)
        self.assertEqual(pack.people, ["Morgan", "Jordan Lee", "Chris Baker"])
        self.assertIn("Dashboard rollout signed off", text)
        self.assertIn("competitor intel scope", text)
        self.assertIn("dutch transcription", text)

    def test_meetings_outside_the_window_and_empty_ones_are_left_out(self):
        self.add_meeting("2026-08-03", "Morgan", ai_summary="the week before")
        self.add_meeting("2026-08-18", "Morgan", ai_summary="the week after")
        self.add_meeting("2026-08-10", "Morgan")  # placeholder, nothing written

        pack = build_pack("2026-08-04", "2026-08-17")

        self.assertEqual(pack.meetings, [])
        self.assertFalse(pack.has_anything)
        self.assertIn("None logged in this window", pack.render())

    def test_agenda_items_are_split_into_what_closed_and_what_is_still_open(self):
        self.add_meeting(
            "2026-08-11", "Morgan", notes="1:1",
            agenda_items=agenda(
                item("Dashboard credentials", detail="waiting on IT"),
                item("Holiday cover", checked=True),
            ),
        )

        pack = build_pack("2026-08-04", "2026-08-17")
        text = pack.render()

        self.assertEqual([i.text for i in pack.closed_items], ["Holiday cover"])
        self.assertEqual([i.text for i in pack.open_items], ["Dashboard credentials"])
        self.assertIn("Action items ticked off in meetings", text)
        self.assertIn("- Dashboard credentials — waiting on IT  [Morgan, 2026-08-11]", text)

    def test_tasks_completed_in_the_window_are_reported_with_their_notes(self):
        inside = TaskManager.create_task("ProjectAtlas", notes="shipped to pilot")
        TaskManager.complete_task(inside)
        open_task = TaskManager.create_task("Still going")

        pack = build_pack("2026-01-01", date.today().isoformat())
        text = pack.render()

        self.assertEqual([task["id"] for task in pack.completed_tasks], [inside])
        self.assertIn("ProjectAtlas", text)
        self.assertIn("shipped to pilot", text)
        self.assertNotIn("Still going", text)
        self.assertTrue(open_task)

    def test_the_headline_reads_like_the_dialog_header(self):
        self.add_meeting("2026-08-11", "Morgan", notes="1:1",
                         agenda_items=agenda(item("Holiday cover", checked=True)))

        pack = build_pack("2026-08-04", "2026-08-17")

        self.assertEqual(
            pack.headline(),
            "2026-08-04 → 2026-08-17 (14 days) · 1 meeting · 1 person · 1 item closed",
        )


if __name__ == "__main__":
    unittest.main()
