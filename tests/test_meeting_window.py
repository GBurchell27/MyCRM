"""Window resolution: what counts as "since the last time I saw them"."""

import unittest

from support import TempDbTestCase

from meeting_window import MAX_LOOKBACK_DAYS, load_window, resolve_window


def row(meeting_id, meeting_date, person, **content):
    item = {
        "id": meeting_id, "date": meeting_date, "person": person,
        "agenda_items": "", "notes": "", "ai_summary": "", "transcript": "",
    }
    item.update(content)
    return item


class ResolveWindowTests(unittest.TestCase):
    """Pure resolution — plain dicts, no database."""

    def test_window_starts_on_the_day_of_the_last_meeting(self):
        rows = [
            row(1, "2026-08-04", "Morgan", notes="last 1:1"),
            row(2, "2026-08-04", "Jordan Lee", notes="same day, after the 1:1"),
            row(3, "2026-08-05", "Robin", notes="midweek"),
            row(4, "2026-08-07", "Morgan", notes="this one"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows, exclude_meeting_id=4)
        self.assertEqual(window.anchor["id"], 1)
        self.assertEqual(window.start_date, "2026-08-04")
        self.assertEqual([m["id"] for m in window.interim], [2, 3])

    def test_empty_placeholders_never_become_the_anchor(self):
        rows = [
            row(1, "2026-08-04", "Morgan", notes="the real one"),
            row(2, "2026-08-06", "Morgan"),  # generated placeholder, never filled in
            row(3, "2026-08-05", "Robin", notes="midweek"),
            row(4, "2026-08-07", "Morgan"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows, exclude_meeting_id=4)
        self.assertEqual(window.anchor["id"], 1)
        self.assertEqual([m["id"] for m in window.interim], [3])

    def test_duplicate_person_and_date_prefers_the_row_with_content(self):
        rows = [
            row(9, "2026-08-04", "Morgan", ai_summary="the note I actually wrote"),
            row(30, "2026-08-04", "Morgan"),  # placeholder laid on top
            row(31, "2026-08-07", "Morgan"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows, exclude_meeting_id=31)
        self.assertEqual(window.anchor["id"], 9)

    def test_other_meetings_with_the_same_person_are_not_interim(self):
        rows = [
            row(1, "2026-08-03", "Morgan", notes="older 1:1"),
            row(2, "2026-08-04", "Morgan", notes="ad-hoc coffee"),
            row(3, "2026-08-05", "Jordan Lee", notes="someone else"),
            row(4, "2026-08-07", "Morgan"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows, exclude_meeting_id=4)
        self.assertEqual(window.anchor["id"], 2, "the ad-hoc meeting resets the window")
        self.assertEqual([m["id"] for m in window.interim], [3])

    def test_person_match_ignores_case_and_padding(self):
        rows = [
            row(1, "2026-08-04", " morgan ", notes="last time"),
            row(2, "2026-08-07", "MORGAN"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows, exclude_meeting_id=2)
        self.assertEqual(window.anchor["id"], 1)

    def test_no_previous_meeting_falls_back_to_a_week(self):
        rows = [
            row(1, "2026-08-05", "Robin", notes="midweek"),
            row(2, "2026-08-07", "Morgan"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows, exclude_meeting_id=2)
        self.assertFalse(window.has_anchor)
        self.assertEqual(window.start_date, "2026-07-31")
        self.assertEqual([m["id"] for m in window.interim], [1])
        self.assertIn("No previous meeting", window.describe())

    def test_a_long_gap_caps_the_sweep_but_keeps_the_anchor(self):
        rows = [
            row(1, "2026-06-01", "Morgan", notes="before the holiday"),
            row(2, "2026-06-02", "Robin", notes="way outside the cap"),
            row(3, "2026-08-05", "Jordan Lee", notes="just before I got back"),
            row(4, "2026-08-07", "Morgan"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows, exclude_meeting_id=4)
        self.assertEqual(window.anchor["id"], 1, "open items from June still carry forward")
        self.assertTrue(window.capped)
        self.assertEqual(window.start_date, "2026-07-24")
        self.assertEqual([m["id"] for m in window.interim], [3])
        self.assertIn(str(MAX_LOOKBACK_DAYS), window.describe())

    def test_future_meetings_beyond_this_one_are_excluded(self):
        rows = [
            row(1, "2026-08-07", "Morgan", notes="last 1:1"),
            row(2, "2026-08-11", "Casey", notes="on the day"),
            row(3, "2026-08-13", "Taylor", notes="after this meeting"),
            row(4, "2026-08-11", "Morgan"),
        ]
        window = resolve_window("Morgan", "2026-08-11", rows, exclude_meeting_id=4)
        self.assertEqual([m["id"] for m in window.interim], [2])

    def test_unparseable_dates_are_skipped_not_fatal(self):
        rows = [
            row(1, "not a date", "Jordan Lee", notes="typo"),
            row(2, "2026-08-04", "Morgan", notes="last 1:1"),
            row(3, "2026-08-05", "Robin", notes="midweek"),
        ]
        window = resolve_window("Morgan", "2026-08-07", rows)
        self.assertEqual(window.anchor["id"], 2)
        self.assertEqual([m["id"] for m in window.interim], [3])

    def test_a_meeting_with_no_date_resolves_to_an_empty_window(self):
        window = resolve_window("Morgan", "", [row(1, "2026-08-04", "Morgan", notes="x")])
        self.assertFalse(window.has_anchor)
        self.assertEqual(window.interim, [])


class LoadWindowTests(TempDbTestCase):
    """The same rules, reading real rows out of SQLite."""

    def test_reproduces_the_07_august_window(self):
        anchor = self.add_meeting("2026-08-04", "Morgan", ai_summary="previous 1:1")
        self.add_meeting("2026-08-04", "Morgan")  # the duplicate placeholder
        self.add_meeting("2026-08-04", "Jordan Lee", ai_summary="reporting dashboard")
        self.add_meeting("2026-08-05", "Robin van Dijk", ai_summary="competitor intel")
        self.add_meeting("2026-08-06", "Riley Hart", ai_summary="prototype scope")
        self.add_meeting("2026-08-06", "Chris Baker", ai_summary="dutch transcription")
        target = self.add_meeting("2026-08-07", "Morgan")

        window = load_window("Morgan", "2026-08-07", exclude_meeting_id=target)

        self.assertEqual(window.anchor["id"], anchor)
        self.assertEqual(window.start_date, "2026-08-04")
        self.assertEqual(
            [m["person"] for m in window.interim],
            ["Jordan Lee", "Robin van Dijk", "Riley Hart", "Chris Baker"],
        )
        self.assertEqual(window.describe(), "Since 2026-08-04 — 4 meetings")

    def test_singular_wording_for_one_meeting(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="previous 1:1")
        self.add_meeting("2026-08-11", "Casey Smit", ai_summary="Dashboard walkthrough")
        target = self.add_meeting("2026-08-11", "Morgan")
        window = load_window("Morgan", "2026-08-11", exclude_meeting_id=target)
        self.assertEqual(window.describe(), "Since 2026-08-07 — 1 meeting")


if __name__ == "__main__":
    unittest.main()
