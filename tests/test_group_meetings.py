"""Meetings with more than one person, and what they feed afterwards.

The case these exist for: a meeting with Pat Quinn, Erin and Sam, then a 1:1
with Pat the following week that should open with what that meeting agreed.
"""

import json
import unittest

from support import TempDbTestCase

from carry_over import CarryOverManager
from catchup_pack import build_pack
from meeting_window import load_window, resolve_window
from people_memory import list_known_people


def agenda(*items):
    return json.dumps(list(items))


def item(text, **fields):
    payload = {"text": text, "detail": "", "checked": False, "in_tasks": False}
    payload.update(fields)
    return payload


def row(meeting_id, meeting_date, person, **content):
    entry = {
        "id": meeting_id, "date": meeting_date, "person": person,
        "agenda_items": "", "notes": "", "ai_summary": "", "transcript": "",
    }
    entry.update(content)
    return entry


class GroupMeetingAnchorsTests(unittest.TestCase):
    """Whose last meeting a group meeting counts as."""

    def test_a_group_meeting_is_the_anchor_for_each_person_in_it(self):
        rows = [
            row(1, "2026-08-04", "Pat Quinn; Erin; Sam", notes="the three of us"),
            row(2, "2026-08-11", "Pat Quinn"),
        ]
        window = resolve_window("Pat Quinn", "2026-08-11", rows, exclude_meeting_id=2)
        self.assertEqual(window.anchor["id"], 1)
        self.assertEqual(window.start_date, "2026-08-04")

    def test_a_more_recent_one_to_one_wins_over_the_group_meeting(self):
        rows = [
            row(1, "2026-08-04", "Pat Quinn; Erin", notes="the group"),
            row(2, "2026-08-06", "Pat Quinn", notes="just us"),
            row(3, "2026-08-11", "Pat Quinn"),
        ]
        window = resolve_window("Pat Quinn", "2026-08-11", rows, exclude_meeting_id=3)
        self.assertEqual(window.anchor["id"], 2)

    def test_each_person_brings_their_own_anchor(self):
        rows = [
            row(1, "2026-07-28", "Erin", notes="Erin, a while back"),
            row(2, "2026-08-06", "Pat Quinn", notes="Pat, recently"),
            row(3, "2026-08-11", "Pat Quinn; Erin"),
        ]
        window = resolve_window("Pat Quinn; Erin", "2026-08-11", rows, exclude_meeting_id=3)
        self.assertEqual(sorted(window.anchor_ids), [1, 2])
        self.assertEqual(
            window.start_date, "2026-07-28",
            "the window opens at the oldest last-time, so Erin's items still carry",
        )

    def test_one_group_meeting_anchoring_everyone_is_counted_once(self):
        rows = [
            row(1, "2026-08-04", "Pat Quinn; Erin", notes="the group"),
            row(2, "2026-08-11", "Pat Quinn; Erin"),
        ]
        window = resolve_window("Pat Quinn; Erin", "2026-08-11", rows, exclude_meeting_id=2)
        self.assertEqual(window.anchor_ids, [1])

    def test_a_meeting_anyone_here_was_in_is_not_reported_back_to_them(self):
        rows = [
            row(1, "2026-08-04", "Pat Quinn", notes="Pat last time"),
            row(2, "2026-08-05", "Erin; Sam", notes="Erin was there"),
            row(3, "2026-08-06", "Jordan Lee", notes="news to both"),
            row(4, "2026-08-11", "Pat Quinn; Erin"),
        ]
        window = resolve_window("Pat Quinn; Erin", "2026-08-11", rows, exclude_meeting_id=4)
        self.assertEqual([m["id"] for m in window.interim], [3])

    def test_somebody_new_is_called_out_rather_than_silently_missing(self):
        rows = [
            row(1, "2026-08-04", "Pat Quinn", notes="Pat last time"),
            row(2, "2026-08-11", "Pat Quinn; Erin"),
        ]
        window = resolve_window("Pat Quinn; Erin", "2026-08-11", rows, exclude_meeting_id=2)
        self.assertEqual(window.anchors.missing, ["Erin"])
        self.assertIn("first time with Erin", window.describe())

    def test_the_people_read_as_a_sentence_for_the_prompt(self):
        window = resolve_window("Pat Quinn; Erin; Sam", "2026-08-11", [])
        self.assertEqual(window.person, "Pat Quinn, Erin and Sam")


class CarryOverAcrossPeopleTests(TempDbTestCase):
    """Open items from several previous meetings, folded into one agenda."""

    def test_open_items_from_every_anchor_come_forward(self):
        self.add_meeting("2026-07-28", "Erin", ai_summary="Erin",
                         agenda_items=agenda(item("Erin's open thing")))
        self.add_meeting("2026-08-06", "Pat Quinn", ai_summary="Pat",
                         agenda_items=agenda(item("Pat's open thing")))
        target = self.add_meeting("2026-08-11", "Pat Quinn; Erin")

        pack = build_pack("Pat Quinn; Erin", "2026-08-11", exclude_meeting_id=target)
        self.assertEqual(
            sorted(c.item["text"] for c in pack.carried),
            ["Erin's open thing", "Pat's open thing"],
        )

    def test_the_same_item_raised_with_two_people_carries_once(self):
        self.add_meeting("2026-07-28", "Erin", ai_summary="Erin",
                         agenda_items=agenda(item("Dashboard credentials")))
        self.add_meeting("2026-08-06", "Pat Quinn", ai_summary="Pat",
                         agenda_items=agenda(item("Dashboard credentials")))
        target = self.add_meeting("2026-08-11", "Pat Quinn; Erin")

        pack = build_pack("Pat Quinn; Erin", "2026-08-11", exclude_meeting_id=target)
        self.assertEqual([c.item["text"] for c in pack.carried], ["Dashboard credentials"])
        self.assertEqual(
            pack.carried[0].as_agenda_item()["first_raised"], "2026-07-28",
            "its age is the oldest one it has anywhere",
        )

    def test_ticked_in_one_meeting_beats_still_open_in_another(self):
        self.add_meeting("2026-07-28", "Erin", ai_summary="Erin",
                         agenda_items=agenda(item("Dashboard credentials")))
        self.add_meeting("2026-08-06", "Pat Quinn", ai_summary="Pat",
                         agenda_items=agenda(item("Dashboard credentials", checked=True)))
        target = self.add_meeting("2026-08-11", "Pat Quinn; Erin")

        pack = build_pack("Pat Quinn; Erin", "2026-08-11", exclude_meeting_id=target)
        self.assertEqual(pack.carried, [])
        self.assertEqual([c.title for c in pack.closed], ["Dashboard credentials"])

    def test_no_anchors_at_all_is_still_a_valid_split(self):
        self.assertEqual(CarryOverManager.split_anchors([]), ([], []))


class FollowUpAfterAGroupMeetingTests(TempDbTestCase):
    """The whole point: a 1:1 that opens with what the group agreed."""

    def test_a_later_one_to_one_briefs_from_the_group_meeting(self):
        self.add_meeting(
            "2026-08-11", "Pat Quinn; Erin; Sam",
            ai_summary="agreed Pat would price the Dashboard rollout",
            agenda_items=agenda(item("Price the Dashboard rollout"),
                                item("Book the workshop", checked=True)),
        )
        self.add_meeting("2026-08-12", "Jordan Lee", ai_summary="reporting dashboard")
        target = self.add_meeting("2026-08-18", "Pat Quinn")

        pack = build_pack("Pat Quinn", "2026-08-18", exclude_meeting_id=target)
        text = pack.render()

        self.assertIn("Last time — Pat Quinn, Erin and Sam, 2026-08-11", text)
        self.assertIn("agreed Pat would price the Dashboard rollout", text)
        self.assertEqual([c.item["text"] for c in pack.carried], ["Price the Dashboard rollout"])
        self.assertEqual([c.title for c in pack.closed], ["Book the workshop"])
        self.assertIn("reporting dashboard", text, "the other meeting is still news")

    def test_a_group_meeting_standing_in_for_one_person_says_whose(self):
        self.add_meeting("2026-08-04", "Pat Quinn; Erin", ai_summary="the group")
        self.add_meeting("2026-08-06", "Sam", ai_summary="Sam alone")
        target = self.add_meeting("2026-08-11", "Pat Quinn; Sam")

        text = build_pack("Pat Quinn; Sam", "2026-08-11", exclude_meeting_id=target).render()
        self.assertIn("Last time with Pat Quinn — Pat Quinn and Erin, 2026-08-04", text)
        self.assertIn("Last time — Sam, 2026-08-06", text)

    def test_the_window_reads_the_same_rows_out_of_the_database(self):
        self.add_meeting("2026-08-11", "Pat Quinn; Erin", ai_summary="the group")
        target = self.add_meeting("2026-08-18", "Erin")
        window = load_window("Erin", "2026-08-18", exclude_meeting_id=target)
        self.assertEqual(window.anchor_date, "2026-08-11")


class KnownPeopleTests(TempDbTestCase):
    def test_everyone_in_a_group_meeting_becomes_a_name_you_can_pick(self):
        self.add_meeting("2026-08-11", "Pat Quinn; Erin", notes="the group")
        self.assertEqual(list_known_people(), ["Erin", "Pat Quinn"])


if __name__ == "__main__":
    unittest.main()
