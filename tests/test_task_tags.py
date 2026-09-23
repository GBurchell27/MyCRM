"""Tagging a task with the project it belongs to."""

import unittest

from support import TempDbTestCase

import db
from task_manager import TaskManager, clean_tag


class TagCleaningTests(unittest.TestCase):
    def test_surrounding_and_doubled_whitespace_goes(self):
        self.assertEqual(clean_tag("  Project  Atlas "), "Project Atlas")

    def test_missing_tag_is_empty_not_none(self):
        self.assertEqual(clean_tag(None), "")


class TaskTagTests(TempDbTestCase):
    def test_a_task_keeps_the_tag_it_was_created_with(self):
        task_id = TaskManager.create_task("Ship pilot", tag="ProjectAtlas")
        self.assertEqual(self.task(task_id)["tag"], "ProjectAtlas")

    def test_a_task_created_without_a_tag_is_untagged_not_null(self):
        task_id = TaskManager.create_task("Chase IT")
        self.assertEqual(self.task(task_id)["tag"], "")

    def test_editing_a_task_can_add_change_and_clear_its_tag(self):
        task_id = TaskManager.create_task("Ship pilot")
        TaskManager.update_task(task_id, "Ship pilot", tag="ProjectAtlas")
        self.assertEqual(self.task(task_id)["tag"], "ProjectAtlas")
        TaskManager.update_task(task_id, "Ship pilot", tag="CRM")
        self.assertEqual(self.task(task_id)["tag"], "CRM")
        TaskManager.update_task(task_id, "Ship pilot")
        self.assertEqual(self.task(task_id)["tag"], "")

    def test_a_retyped_tag_joins_the_existing_one_whatever_the_case(self):
        TaskManager.create_task("First", tag="ProjectAtlas")
        second = TaskManager.create_task("Second", tag="projectatlas")
        self.assertEqual(self.task(second)["tag"], "ProjectAtlas")
        self.assertEqual(TaskManager.list_tags(), ["ProjectAtlas"])

    def test_known_tags_are_listed_once_alphabetically_across_open_and_done(self):
        TaskManager.create_task("First", tag="crm")
        TaskManager.create_task("Second", tag="crm")
        done = TaskManager.create_task("Third", tag="Admin")
        TaskManager.complete_task(done)
        TaskManager.create_task("Untagged one")
        self.assertEqual(TaskManager.list_tags(), ["Admin", "crm"])

    def test_existing_databases_gain_the_column_without_losing_tasks(self):
        conn = db.get_conn()
        conn.execute("DROP TABLE tasks")
        conn.execute(
            "CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "title TEXT NOT NULL, notes TEXT DEFAULT '', created_at TEXT NOT NULL, "
            "completed_at TEXT)"
        )
        conn.execute(
            "INSERT INTO tasks (title, notes, created_at) VALUES ('Old task', '', ?)",
            (TaskManager.now_stamp(),),
        )
        conn.commit()
        conn.close()

        db.init_db()

        rows = TaskManager.list_active()
        self.assertEqual([row["title"] for row in rows], ["Old task"])
        self.assertIn(rows[0]["tag"], ("", None))

    def task(self, task_id):
        return TaskManager.states_for([task_id])[task_id]


class GroupByTagTests(TempDbTestCase):
    def test_the_untagged_group_leads_and_the_projects_follow_alphabetically(self):
        TaskManager.create_task("Loose end")
        TaskManager.create_task("Ship pilot", tag="ProjectAtlas")
        TaskManager.create_task("Fix export", tag="CRM")
        TaskManager.create_task("Write brief", tag="crm")

        grouped = TaskManager.group_by_tag(TaskManager.list_active())

        self.assertEqual([tag for tag, _ in grouped], ["", "CRM", "ProjectAtlas"])
        self.assertEqual([row["title"] for row in grouped[0][1]], ["Loose end"])
        self.assertEqual(
            sorted(row["title"] for row in grouped[1][1]),
            ["Fix export", "Write brief"],
        )

    def test_a_task_sent_over_from_a_meeting_lands_at_the_very_top(self):
        TaskManager.create_task("Ship pilot", tag="ProjectAtlas")
        TaskManager.create_task("Older loose end")
        from_meeting = TaskManager.create_task("Chase the licence count")

        grouped = TaskManager.group_by_tag(TaskManager.list_active())
        first_tag, first_rows = grouped[0]

        self.assertEqual(first_tag, "")
        self.assertEqual(first_rows[0]["id"], from_meeting)

    def test_an_empty_list_groups_into_nothing(self):
        self.assertEqual(TaskManager.group_by_tag([]), [])


if __name__ == "__main__":
    unittest.main()
