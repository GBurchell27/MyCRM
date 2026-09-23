"""Per-series brief toggle, carried badges, and exports carrying the brief."""

import csv
import json
import os
import tempfile
import unittest

from support import TempDbTestCase

from recurring_meetings import RecurringMeetingManager
from widgets.agenda_checklist import carried_badge

TUESDAY, FRIDAY = 1, 4


class CatchupToggleTests(TempDbTestCase):
    def test_a_new_series_briefs_by_default(self):
        recurring_id = RecurringMeetingManager.create("Morgan", [TUESDAY, FRIDAY])
        self.assertTrue(RecurringMeetingManager.catchup_enabled(recurring_id))

    def test_the_toggle_can_be_turned_off(self):
        recurring_id = RecurringMeetingManager.create("Quiet Person", [TUESDAY],
                                                     catchup_enabled=False)
        self.assertFalse(RecurringMeetingManager.catchup_enabled(recurring_id))

    def test_a_one_off_meeting_never_auto_briefs(self):
        self.assertFalse(RecurringMeetingManager.catchup_enabled(None))
        self.assertFalse(RecurringMeetingManager.catchup_enabled(9999))


class CarriedBadgeTests(unittest.TestCase):
    def test_a_repeatedly_carried_item_shows_its_age(self):
        self.assertEqual(
            carried_badge({"carried_count": 3, "first_raised": "2026-07-24"}),
            "↻3 since 24 Jul",
        )

    def test_a_fresh_item_has_no_badge(self):
        self.assertEqual(carried_badge({}), "")
        self.assertEqual(carried_badge({"carried_count": 0}), "")
        self.assertEqual(carried_badge(None), "")

    def test_a_missing_or_broken_date_still_shows_the_count(self):
        self.assertEqual(carried_badge({"carried_count": 2}), "↻2")
        self.assertEqual(carried_badge({"carried_count": 2, "first_raised": "nope"}), "↻2")


class ExportTests(TempDbTestCase):
    def setUp(self):
        super().setUp()
        self.meeting_id = self.add_meeting(
            "2026-08-11", "Morgan",
            agenda_items=json.dumps([{"text": "Dashboard credentials", "checked": False}]),
            ai_summary="the meeting summary",
        )
        conn = __import__("db").get_conn()
        conn.execute("UPDATE meetings SET catchup_brief=? WHERE id=?",
                     ("Two things moved since Friday.", self.meeting_id))
        conn.commit()
        conn.close()

    def test_csv_export_includes_the_brief(self):
        from tabs.meetings_tab import MeetingsTab

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.csv")
            MeetingsTab.export_csv(self, path)  # rows come from load_rows below
            with open(path, encoding="utf-8") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(rows[0][3], "Catch-up brief")
        self.assertEqual(rows[1][3], "Two things moved since Friday.")

    def load_rows(self):
        """Stand in for the tab's own loader so the export can run headless."""
        return self.all_meetings()

    def test_excel_export_includes_the_brief(self):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("openpyxl not installed")
        from excel_export import write_meetings_workbook

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "out.xlsx")
            write_meetings_workbook(path, self.all_meetings())
            sheet = load_workbook(path).active
            headers = [cell.value for cell in sheet[1]]
            first = [cell.value for cell in sheet[2]]

        self.assertEqual(headers[3], "Catch-up brief")
        self.assertEqual(first[3], "Two things moved since Friday.")

    def test_a_row_saved_before_the_column_existed_exports_blank_not_crash(self):
        from excel_export import field
        legacy = {"date": "2026-01-01", "person": "Old"}
        self.assertEqual(field(legacy, "catchup_brief"), "")


if __name__ == "__main__":
    unittest.main()
