"""Rolling a project's tasks up in the active list, and remembering it."""

import unittest

from support import TempDbTestCase

from task_group_collapse import CollapsedTaskGroups


class CollapsedTaskGroupTests(TempDbTestCase):
    def test_nothing_is_collapsed_to_start_with(self):
        groups = CollapsedTaskGroups()
        self.assertFalse(groups.is_collapsed("ProjectAtlas"))
        self.assertFalse(groups.is_collapsed(""))

    def test_toggling_collapses_then_expands_one_group(self):
        groups = CollapsedTaskGroups()
        self.assertTrue(groups.toggle("ProjectAtlas"))
        self.assertTrue(groups.is_collapsed("ProjectAtlas"))
        self.assertFalse(groups.toggle("ProjectAtlas"))
        self.assertFalse(groups.is_collapsed("ProjectAtlas"))

    def test_collapsing_one_group_leaves_the_others_open(self):
        groups = CollapsedTaskGroups()
        groups.toggle("ProjectAtlas")
        self.assertFalse(groups.is_collapsed("CRM"))

    def test_the_untagged_group_collapses_under_the_empty_tag(self):
        groups = CollapsedTaskGroups()
        groups.toggle("")
        self.assertTrue(groups.is_collapsed(""))
        self.assertTrue(groups.is_collapsed(None))

    def test_collapsed_groups_survive_a_restart(self):
        CollapsedTaskGroups().toggle("ProjectAtlas")
        self.assertTrue(CollapsedTaskGroups().is_collapsed("ProjectAtlas"))

    def test_collapse_all_then_expand_all_covers_every_heading(self):
        tags = ["", "CRM", "ProjectAtlas"]
        groups = CollapsedTaskGroups()
        groups.collapse_all(tags)
        self.assertTrue(groups.all_collapsed(tags))
        groups.expand_all(tags)
        self.assertFalse(any(groups.is_collapsed(tag) for tag in tags))

    def test_all_collapsed_is_false_when_one_group_is_still_open(self):
        groups = CollapsedTaskGroups()
        groups.toggle("CRM")
        self.assertFalse(groups.all_collapsed(["CRM", "ProjectAtlas"]))

    def test_no_groups_at_all_does_not_count_as_all_collapsed(self):
        self.assertFalse(CollapsedTaskGroups().all_collapsed([]))

    def test_unreadable_stored_state_falls_back_to_everything_open(self):
        import db

        db.set_setting(CollapsedTaskGroups.SETTING_KEY, "not json")
        self.assertFalse(CollapsedTaskGroups().is_collapsed("CRM"))


if __name__ == "__main__":
    unittest.main()
