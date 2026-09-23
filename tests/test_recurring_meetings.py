"""Placeholder generation must not bury a note you already wrote."""

import unittest
from datetime import date

from support import TempDbTestCase

from recurring_meetings import RecurringMeetingManager

TUESDAY = 1
FRIDAY = 4


class FillOccurrencesTests(TempDbTestCase):
    def test_creates_one_placeholder_per_matching_weekday(self):
        RecurringMeetingManager.create("Morgan", [TUESDAY, FRIDAY])
        RecurringMeetingManager.top_up_all(today=date(2026, 8, 9))  # Sunday
        dates = [row["date"] for row in self.all_meetings()]
        self.assertEqual(dates, ["2026-08-11", "2026-08-14"])

    def test_skips_dates_that_already_have_a_meeting_with_that_person(self):
        self.add_meeting("2026-08-11", "Morgan", notes="already written by hand")
        recurring_id = RecurringMeetingManager.create("Morgan", [TUESDAY, FRIDAY])
        RecurringMeetingManager._fill_occurrences(
            recurring_id, "Morgan", [TUESDAY, FRIDAY], today=date(2026, 8, 9)
        )
        on_the_11th = [row for row in self.all_meetings() if row["date"] == "2026-08-11"]
        self.assertEqual(len(on_the_11th), 1)
        self.assertEqual(on_the_11th[0]["notes"], "already written by hand")

    def test_person_match_ignores_case_and_padding(self):
        self.add_meeting("2026-08-11", "  morgan ", notes="mine")
        recurring_id = RecurringMeetingManager.create("Morgan", [TUESDAY])
        RecurringMeetingManager._fill_occurrences(
            recurring_id, "Morgan", [TUESDAY], today=date(2026, 8, 9)
        )
        self.assertEqual(len(self.all_meetings()), 1)

    def test_a_skipped_date_is_still_logged_so_it_is_not_retried(self):
        self.add_meeting("2026-08-11", "Morgan", notes="mine")
        recurring_id = RecurringMeetingManager.create("Morgan", [TUESDAY])
        for _ in range(3):
            RecurringMeetingManager._fill_occurrences(
                recurring_id, "Morgan", [TUESDAY], today=date(2026, 8, 9)
            )
        self.assertEqual(len(self.all_meetings()), 1)

    def test_a_different_person_on_the_same_day_does_not_block_the_placeholder(self):
        self.add_meeting("2026-08-11", "Casey Smit", notes="unrelated")
        recurring_id = RecurringMeetingManager.create("Morgan", [TUESDAY])
        RecurringMeetingManager._fill_occurrences(
            recurring_id, "Morgan", [TUESDAY], today=date(2026, 8, 9)
        )
        people = sorted(row["person"] for row in self.all_meetings())
        self.assertEqual(people, ["Casey Smit", "Morgan"])


if __name__ == "__main__":
    unittest.main()
