"""Undoing a completion, and filing a task straight from the list."""

import unittest

from support import TempDbTestCase

from task_manager import TaskManager


class TaskStateTestCase(TempDbTestCase):
    def task(self, task_id):
        return TaskManager.states_for([task_id])[task_id]


class ReopenTaskTests(TaskStateTestCase):
    def test_a_task_ticked_off_by_mistake_goes_back_to_the_active_list(self):
        task_id = TaskManager.create_task("Chase the licence count")
        TaskManager.complete_task(task_id)
        self.assertEqual(TaskManager.list_active(), [])

        TaskManager.reopen_task(task_id)

        self.assertEqual([row["id"] for row in TaskManager.list_active()], [task_id])
        self.assertEqual(TaskManager.list_history(), [])
        self.assertIsNone(self.task(task_id)["completed_at"])

    def test_reopening_keeps_the_title_notes_and_tag(self):
        task_id = TaskManager.create_task(
            "Ship pilot", notes="Waiting on IT", tag="ProjectAtlas"
        )
        TaskManager.complete_task(task_id)

        TaskManager.reopen_task(task_id)

        row = self.task(task_id)
        self.assertEqual(row["title"], "Ship pilot")
        self.assertEqual(row["notes"], "Waiting on IT")
        self.assertEqual(row["tag"], "ProjectAtlas")

    def test_a_reopened_task_can_be_completed_again_with_a_fresh_stamp(self):
        task_id = TaskManager.create_task("Chase IT")
        TaskManager.complete_task(task_id)
        TaskManager.reopen_task(task_id)

        TaskManager.complete_task(task_id)

        self.assertIsNotNone(self.task(task_id)["completed_at"])

    def test_reopening_a_task_that_was_never_finished_changes_nothing(self):
        task_id = TaskManager.create_task("Still open")

        TaskManager.reopen_task(task_id)

        self.assertEqual([row["id"] for row in TaskManager.list_active()], [task_id])


class SetTagTests(TaskStateTestCase):
    def test_filing_a_task_leaves_its_title_and_notes_alone(self):
        task_id = TaskManager.create_task("Chase IT", notes="Ticket 4021")

        TaskManager.set_tag(task_id, "CRM")

        row = self.task(task_id)
        self.assertEqual(row["tag"], "CRM")
        self.assertEqual(row["title"], "Chase IT")
        self.assertEqual(row["notes"], "Ticket 4021")

    def test_a_tag_filed_from_the_list_joins_an_existing_one_whatever_the_case(self):
        TaskManager.create_task("First", tag="ProjectAtlas")
        task_id = TaskManager.create_task("Second")

        TaskManager.set_tag(task_id, "  projectatlas ")

        self.assertEqual(self.task(task_id)["tag"], "ProjectAtlas")
        self.assertEqual(TaskManager.list_tags(), ["ProjectAtlas"])

    def test_filing_can_move_a_task_between_projects_and_clear_it_again(self):
        task_id = TaskManager.create_task("Ship pilot", tag="CRM")

        TaskManager.set_tag(task_id, "Admin")
        self.assertEqual(self.task(task_id)["tag"], "Admin")

        TaskManager.set_tag(task_id, "")
        self.assertEqual(self.task(task_id)["tag"], "")

    def test_a_completed_task_can_still_be_filed(self):
        task_id = TaskManager.create_task("Chase IT")
        TaskManager.complete_task(task_id)

        TaskManager.set_tag(task_id, "Admin")

        row = self.task(task_id)
        self.assertEqual(row["tag"], "Admin")
        self.assertIsNotNone(row["completed_at"])


if __name__ == "__main__":
    unittest.main()
