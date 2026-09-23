"""Spotting when someone has become a regular."""

import unittest

from support import TempDbTestCase

from meeting_cadence import analyse, load_cadence
from recurring_meetings import RecurringMeetingManager

MONDAY, TUESDAY, WEDNESDAY, THURSDAY, FRIDAY = 0, 1, 2, 3, 4


def row(meeting_id, meeting_date, person, content="notes"):
    return {"id": meeting_id, "date": meeting_date, "person": person,
            "agenda_items": "", "notes": content, "ai_summary": "", "transcript": ""}


class CadenceTests(unittest.TestCase):
    def test_a_twice_weekly_pattern_is_regular_and_names_both_days(self):
        rows = [
            row(1, "2026-07-28", "Morgan"), row(2, "2026-07-31", "Morgan"),
            row(3, "2026-08-04", "Morgan"), row(4, "2026-08-07", "Morgan"),
        ]
        cadence = analyse("Morgan", rows)
        self.assertTrue(cadence.looks_regular)
        self.assertEqual(cadence.weekday_pattern, [TUESDAY, FRIDAY])
        self.assertEqual(
            cadence.describe(),
            "You've met Morgan 4 times, a couple of times a week on Tuesdays and Fridays.",
        )

    def test_a_weekly_pattern_reads_as_weekly(self):
        rows = [row(i, d, "Taylor") for i, d in enumerate(
            ["2026-07-20", "2026-07-27", "2026-08-03", "2026-08-10"], start=1)]
        cadence = analyse("Taylor", rows)
        self.assertTrue(cadence.looks_regular)
        self.assertEqual(cadence.weekday_pattern, [MONDAY])
        self.assertIn("about weekly on Mondays", cadence.describe())

    def test_a_fortnightly_pattern_is_still_regular(self):
        rows = [row(i, d, "Robin") for i, d in enumerate(
            ["2026-07-01", "2026-07-15", "2026-07-29"], start=1)]
        cadence = analyse("Robin", rows)
        self.assertTrue(cadence.looks_regular)
        self.assertIn("about every two weeks", cadence.describe())

    def test_two_meetings_are_not_yet_a_pattern(self):
        rows = [row(1, "2026-08-04", "Jordan"), row(2, "2026-08-11", "Jordan")]
        self.assertFalse(analyse("Jordan", rows).looks_regular)

    def test_three_meetings_years_apart_are_not_a_pattern(self):
        rows = [row(i, d, "Old Friend") for i, d in enumerate(
            ["2024-01-01", "2025-01-01", "2026-01-01"], start=1)]
        self.assertFalse(analyse("Old Friend", rows).looks_regular)

    def test_empty_placeholders_do_not_count_toward_a_pattern(self):
        rows = [
            row(1, "2026-07-28", "Morgan"), row(2, "2026-07-31", "Morgan"),
            row(3, "2026-08-04", "Morgan", content=""),
            row(4, "2026-08-07", "Morgan", content=""),
        ]
        cadence = analyse("Morgan", rows)
        self.assertEqual(cadence.meeting_count, 2)
        self.assertFalse(cadence.looks_regular)

    def test_other_peoples_meetings_are_ignored(self):
        rows = [
            row(1, "2026-07-28", "Morgan"), row(2, "2026-07-31", "Morgan"),
            row(3, "2026-08-04", "Morgan"),
            row(4, "2026-08-05", "Someone Else"), row(5, "2026-08-06", "Someone Else"),
        ]
        self.assertEqual(analyse("Morgan", rows).meeting_count, 3)

    def test_person_matching_ignores_case_and_padding(self):
        rows = [row(1, "2026-07-28", " morgan "), row(2, "2026-07-31", "MORGAN"),
                row(3, "2026-08-04", "Morgan")]
        self.assertEqual(analyse("Morgan", rows).meeting_count, 3)

    def test_nobody_met_yet_is_handled(self):
        cadence = analyse("Nobody", [])
        self.assertEqual(cadence.meeting_count, 0)
        self.assertFalse(cadence.looks_regular)
        self.assertEqual(cadence.weekday_pattern, [])

    def test_a_scattered_pattern_still_suggests_its_commonest_day(self):
        rows = [row(1, "2026-07-27", "Ad Hoc"), row(2, "2026-08-04", "Ad Hoc"),
                row(3, "2026-08-10", "Ad Hoc")]
        cadence = analyse("Ad Hoc", rows)
        self.assertEqual(cadence.weekday_pattern, [MONDAY])


class SeriesLookupTests(TempDbTestCase):
    def test_the_detected_pattern_matches_the_series_you_would_set_up(self):
        for day in ("2026-07-28", "2026-07-31", "2026-08-04", "2026-08-07"):
            self.add_meeting(day, "Morgan", notes="1:1")
        self.assertEqual(load_cadence("Morgan").weekday_pattern, [TUESDAY, FRIDAY])

    def test_series_lookup_finds_an_active_series_case_insensitively(self):
        RecurringMeetingManager.create("Morgan", [TUESDAY, FRIDAY])
        self.assertIsNotNone(RecurringMeetingManager.series_for_person("  morgan "))
        self.assertIsNone(RecurringMeetingManager.series_for_person("Someone Else"))
        self.assertIsNone(RecurringMeetingManager.series_for_person(""))

    def test_a_stopped_series_no_longer_counts(self):
        recurring_id = RecurringMeetingManager.create("Morgan", [TUESDAY])
        RecurringMeetingManager.deactivate(recurring_id)
        self.assertIsNone(RecurringMeetingManager.series_for_person("Morgan"))

    def test_briefs_can_be_toggled_on_an_existing_series(self):
        recurring_id = RecurringMeetingManager.create("Morgan", [TUESDAY])
        RecurringMeetingManager.set_catchup_enabled(recurring_id, False)
        self.assertFalse(RecurringMeetingManager.catchup_enabled(recurring_id))
        RecurringMeetingManager.set_catchup_enabled(recurring_id, True)
        self.assertTrue(RecurringMeetingManager.catchup_enabled(recurring_id))


if __name__ == "__main__":
    unittest.main()
