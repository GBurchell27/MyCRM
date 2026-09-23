"""Which agenda items follow you into the next meeting, and which are done."""

import json
import unittest

from support import TempDbTestCase

from carry_over import CLOSED_BY_TASK, CLOSED_BY_TICK, CarryOverManager
from task_manager import TaskManager


def agenda(*items):
    return json.dumps(list(items))


def item(text, **fields):
    payload = {"text": text, "detail": "", "checked": False, "in_tasks": False}
    payload.update(fields)
    return payload


class SplitAnchorItemsTests(TempDbTestCase):
    def test_ticked_items_close_and_unticked_items_carry(self):
        anchor_id = self.add_meeting(
            "2026-08-07", "Morgan",
            agenda_items=agenda(item("Done thing", checked=True), item("Open thing")),
        )
        carried, closed = CarryOverManager.split_anchor_items(self.meeting(anchor_id))

        self.assertEqual([c.item["text"] for c in carried], ["Open thing"])
        self.assertEqual([c.title for c in closed], ["Done thing"])
        self.assertEqual(closed[0].closed_by, CLOSED_BY_TICK)

    def test_an_item_completed_in_the_tasks_tab_does_not_come_back(self):
        task_id = TaskManager.create_task("ProjectAtlas")
        TaskManager.complete_task(task_id)
        anchor_id = self.add_meeting(
            "2026-08-07", "Morgan",
            agenda_items=agenda(item("ProjectAtlas", in_tasks=True, task_id=task_id)),
        )
        carried, closed = CarryOverManager.split_anchor_items(self.meeting(anchor_id))

        self.assertEqual(carried, [])
        self.assertEqual(closed[0].closed_by, CLOSED_BY_TASK)
        self.assertTrue(closed[0].completed_at)

    def test_an_item_still_open_in_tasks_carries_and_keeps_its_link(self):
        task_id = TaskManager.create_task("ProjectAtlas")
        anchor_id = self.add_meeting(
            "2026-08-07", "Morgan",
            agenda_items=agenda(item("ProjectAtlas", in_tasks=True, task_id=task_id)),
        )
        carried, closed = CarryOverManager.split_anchor_items(self.meeting(anchor_id))

        self.assertEqual(closed, [])
        payload = carried[0].as_agenda_item()
        self.assertEqual(payload["task_id"], task_id)
        self.assertTrue(payload["in_tasks"])

    def test_a_deleted_task_is_not_a_completed_task(self):
        task_id = TaskManager.create_task("Chase IT")
        TaskManager.delete_task(task_id)
        anchor_id = self.add_meeting(
            "2026-08-07", "Morgan",
            agenda_items=agenda(item("Chase IT", in_tasks=True, task_id=task_id)),
        )
        carried, closed = CarryOverManager.split_anchor_items(self.meeting(anchor_id))

        self.assertEqual(closed, [])
        payload = carried[0].as_agenda_item()
        self.assertNotIn("task_id", payload)
        self.assertFalse(payload["in_tasks"], "the To Tasks button must work again")

    def test_carrying_stamps_provenance_and_ages_the_item(self):
        anchor_id = self.add_meeting(
            "2026-08-07", "Morgan", agenda_items=agenda(item("Dashboard credentials")),
        )
        carried, _ = CarryOverManager.split_anchor_items(self.meeting(anchor_id))
        payload = carried[0].as_agenda_item()

        self.assertEqual(payload["first_raised"], "2026-08-07")
        self.assertEqual(payload["carried_count"], 1)
        self.assertEqual(payload["source_meeting_id"], anchor_id)

    def test_carrying_again_keeps_the_original_date_and_increments_the_count(self):
        anchor_id = self.add_meeting(
            "2026-08-11", "Morgan",
            agenda_items=agenda(item("Dashboard credentials", first_raised="2026-07-24",
                                     carried_count=2)),
        )
        carried, _ = CarryOverManager.split_anchor_items(self.meeting(anchor_id))
        payload = carried[0].as_agenda_item()

        self.assertEqual(payload["first_raised"], "2026-07-24")
        self.assertEqual(payload["carried_count"], 3)

    def test_blank_rows_and_a_missing_anchor_are_ignored(self):
        anchor_id = self.add_meeting(
            "2026-08-07", "Morgan", agenda_items=agenda(item(""), item("   ")),
        )
        self.assertEqual(CarryOverManager.split_anchor_items(self.meeting(anchor_id)), ([], []))
        self.assertEqual(CarryOverManager.split_anchor_items(None), ([], []))

    def test_a_ticked_item_wins_even_if_its_task_is_still_open(self):
        task_id = TaskManager.create_task("Handled in the meeting")
        anchor_id = self.add_meeting(
            "2026-08-07", "Morgan",
            agenda_items=agenda(item("Handled in the meeting", checked=True,
                                     in_tasks=True, task_id=task_id)),
        )
        carried, closed = CarryOverManager.split_anchor_items(self.meeting(anchor_id))
        self.assertEqual(carried, [])
        self.assertEqual(closed[0].closed_by, CLOSED_BY_TICK)


class MergeIntoTests(TempDbTestCase):
    def _carried(self, *items, meeting_date="2026-08-07"):
        anchor_id = self.add_meeting(meeting_date, "Morgan", agenda_items=agenda(*items))
        carried, _ = CarryOverManager.split_anchor_items(self.meeting(anchor_id))
        return carried

    def test_carried_items_append_after_what_is_already_there(self):
        carried = self._carried(item("Open thing"))
        merged, added = CarryOverManager.merge_into([item("Today's topic")], carried)
        self.assertEqual([m["text"] for m in merged], ["Today's topic", "Open thing"])
        self.assertEqual(added, 1)

    def test_merging_twice_does_not_duplicate(self):
        carried = self._carried(item("Open thing"))
        merged, _ = CarryOverManager.merge_into([], carried)
        merged, added = CarryOverManager.merge_into(merged, carried)
        self.assertEqual([m["text"] for m in merged], ["Open thing"])
        self.assertEqual(added, 0)

    def test_matching_is_insensitive_to_case_and_spacing(self):
        carried = self._carried(item("Open   Thing"))
        merged, added = CarryOverManager.merge_into([item("open thing")], carried)
        self.assertEqual(len(merged), 1)
        self.assertEqual(added, 0)

    def test_an_existing_row_adopts_the_carried_history(self):
        carried = self._carried(item("Dashboard credentials", first_raised="2026-07-24",
                                     carried_count=2))
        merged, _ = CarryOverManager.merge_into([item("Dashboard credentials")], carried)
        self.assertEqual(merged[0]["first_raised"], "2026-07-24")
        self.assertEqual(merged[0]["carried_count"], 3)

    def test_blank_existing_rows_are_dropped(self):
        merged, _ = CarryOverManager.merge_into([item(""), item("Real")], [])
        self.assertEqual([m["text"] for m in merged], ["Real"])


if __name__ == "__main__":
    unittest.main()
