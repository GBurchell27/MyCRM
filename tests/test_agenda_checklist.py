"""The checklist must hand back everything it was given.

Carry-forward history lives on the agenda item, but the widget rebuilds items
from its own entry boxes on save. Anything it doesn't deliberately preserve is
lost the first time the note is saved.
"""

import tkinter as tk
import unittest
from unittest import mock

from support import TempDbTestCase

from task_manager import TaskManager
from widgets.agenda_checklist import AgendaChecklist


class AgendaChecklistRoundTripTests(TempDbTestCase):
    def setUp(self):
        super().setUp()
        self.root = tk.Tk()
        self.root.withdraw()
        # The widget confirms bulk actions with a modal dialog, which would sit
        # there forever without someone to click it.
        patcher = mock.patch("widgets.agenda_checklist.messagebox")
        self.messagebox = patcher.start()
        self.addCleanup(patcher.stop)
        self.checklist = AgendaChecklist(
            self.root, get_meeting_context=lambda: {"person": "Morgan", "date": "2026-08-11"}
        )

    def tearDown(self):
        self.root.destroy()
        super().tearDown()

    def test_carry_forward_metadata_survives_a_round_trip(self):
        self.checklist.set_items([{
            "text": "Dashboard credentials", "detail": "still with IT", "checked": False,
            "in_tasks": True, "task_id": 42,
            "first_raised": "2026-07-24", "carried_count": 3, "source_meeting_id": 31,
        }])
        out = self.checklist.get_filled_items()[0]

        self.assertEqual(out["text"], "Dashboard credentials")
        self.assertEqual(out["detail"], "still with IT")
        self.assertEqual(out["task_id"], 42)
        self.assertEqual(out["first_raised"], "2026-07-24")
        self.assertEqual(out["carried_count"], 3)
        self.assertEqual(out["source_meeting_id"], 31)

    def test_unknown_future_keys_are_preserved_too(self):
        self.checklist.set_items([{"text": "Thing", "some_later_field": "keep me"}])
        self.assertEqual(self.checklist.get_filled_items()[0]["some_later_field"], "keep me")

    def test_plain_items_gain_no_task_id(self):
        self.checklist.set_items([{"text": "Thing"}])
        self.assertNotIn("task_id", self.checklist.get_filled_items()[0])

    def test_sending_a_row_to_tasks_records_the_task_id(self):
        self.checklist.set_items([{"text": "Chase IT", "detail": "credentials"}])
        self.checklist.add_row_to_tasks(self.checklist.item_rows[0]["frame"])

        out = self.checklist.get_filled_items()[0]
        self.assertTrue(out["in_tasks"])
        self.assertIn("task_id", out)
        self.assertEqual(TaskManager.states_for([out["task_id"]])[out["task_id"]]["title"],
                         "Chase IT")

    def test_add_unchecked_to_tasks_records_every_task_id(self):
        self.checklist.set_items([{"text": "One"}, {"text": "Two"}])
        self.checklist.add_unchecked_to_tasks()

        ids = [item["task_id"] for item in self.checklist.get_filled_items()]
        self.assertEqual(len(set(ids)), 2)
        self.assertEqual(len(TaskManager.states_for(ids)), 2)


if __name__ == "__main__":
    unittest.main()
