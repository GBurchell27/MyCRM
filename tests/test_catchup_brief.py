"""Brief storage, staleness detection, and shaping whatever the model returns."""

import unittest

from support import TempDbTestCase

import ai_catchup
from catchup_brief import CatchupBriefManager
from catchup_pack import build_pack


class NormaliseTests(unittest.TestCase):
    def test_a_well_formed_reply_survives_intact(self):
        brief = ai_catchup.normalise({
            "since_last_time": " Three things moved. ",
            "updates": [{"headline": "Dashboard", "detail": "narrowed scope",
                         "source": "Casey, 2026-08-11"}],
            "open_items_status": [{"item": "ProjectAtlas", "status": "blocked",
                                   "evidence": "vendor timeline still unset"}],
            "decisions_needed": ["Who owns the Marketing Control Room"],
            "risks": ["Dashboard credentials open for 3 meetings"],
            "suggested_agenda": [{"text": "Dashboard scope", "detail": "decide narrow or broad"}],
        })
        self.assertEqual(brief["since_last_time"], "Three things moved.")
        self.assertEqual(brief["updates"][0]["source"], "Casey, 2026-08-11")
        self.assertEqual(brief["open_items_status"][0]["status"], "blocked")

    def test_missing_fields_become_empty_not_crashes(self):
        brief = ai_catchup.normalise({})
        self.assertEqual(brief["since_last_time"], "")
        self.assertEqual(brief["updates"], [])
        self.assertEqual(brief["risks"], [])

    def test_junk_shapes_are_discarded(self):
        brief = ai_catchup.normalise({
            "updates": "not a list",
            "risks": [None, "", "  ", "real risk"],
            "suggested_agenda": [{"detail": "no title"}, 42, {"text": "kept"}],
        })
        self.assertEqual(brief["updates"], [])
        self.assertEqual(brief["risks"], ["real risk"])
        self.assertEqual([row["text"] for row in brief["suggested_agenda"]], ["kept"])

    def test_a_bare_string_is_promoted_to_the_first_field(self):
        brief = ai_catchup.normalise({"updates": ["just a sentence"]})
        self.assertEqual(brief["updates"][0]["headline"], "just a sentence")

    def test_render_lays_the_sections_out_in_reading_order(self):
        text = ai_catchup.render(ai_catchup.normalise({
            "since_last_time": "Opening line.",
            "updates": [{"headline": "Dashboard", "detail": "narrowed", "source": "Casey, 11 Aug"}],
            "open_items_status": [{"item": "ProjectAtlas", "status": "no movement",
                                   "evidence": "nothing in the notes"}],
            "decisions_needed": ["Who owns Dashboard"],
            "risks": ["Open 3 meetings running"],
            "suggested_agenda": [{"text": "Dashboard scope", "detail": ""}],
        }))
        for marker in ("Opening line.", "WHAT'S HAPPENED", "(Casey, 11 Aug)",
                       "[no movement] ProjectAtlas", "WHAT I NEED FROM YOU",
                       "RISKS", "SUGGESTED AGENDA"):
            self.assertIn(marker, text)

    def test_render_of_an_empty_brief_is_empty(self):
        self.assertEqual(ai_catchup.render(ai_catchup.normalise({})), "")

    def test_the_prompt_names_the_person_without_mangling_the_json_shape(self):
        prompt = ai_catchup._system_prompt("Morgan")
        self.assertIn("about to meet Morgan", prompt)
        self.assertNotIn("{person}", prompt)
        self.assertIn('"since_last_time"', prompt)


class BriefStorageTests(TempDbTestCase):
    def _pack(self, target_date="2026-08-11"):
        target = self.add_meeting(target_date, "Morgan")
        return build_pack("Morgan", target_date, exclude_meeting_id=target), target

    def test_a_saved_brief_comes_back_with_its_metadata(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1")
        pack, target = self._pack()
        meta = CatchupBriefManager.save(target, "the brief text", pack.window)

        brief, loaded = CatchupBriefManager.load(self.meeting(target))
        self.assertEqual(brief, "the brief text")
        self.assertEqual(loaded["source_meeting_ids"], meta["source_meeting_ids"])
        self.assertEqual(loaded["window"], ["2026-08-07", "2026-08-11"])
        self.assertTrue(loaded["generated_at"])
        self.assertIn("Brief written", CatchupBriefManager.describe_generation(loaded))

    def test_a_brief_covering_everything_is_not_stale(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1")
        self.add_meeting("2026-08-09", "Jordan Lee", ai_summary="weekend catch-up")
        pack, target = self._pack()
        meta = CatchupBriefManager.save(target, "brief", pack.window)

        self.assertEqual(CatchupBriefManager.staleness_notice(meta, pack.window), "")

    def test_a_meeting_logged_afterwards_makes_the_brief_stale(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1")
        pack, target = self._pack()
        meta = CatchupBriefManager.save(target, "brief", pack.window)

        self.add_meeting("2026-08-10", "Monday Person", ai_summary="logged after the brief")
        later = build_pack("Morgan", "2026-08-11", exclude_meeting_id=target)

        self.assertEqual(
            CatchupBriefManager.staleness_notice(meta, later.window),
            "1 new meeting logged since this brief was written — regenerate it.",
        )

    def test_meeting_them_again_makes_the_brief_stale(self):
        self.add_meeting("2026-08-07", "Morgan", ai_summary="last 1:1")
        pack, target = self._pack("2026-08-14")
        meta = CatchupBriefManager.save(target, "brief", pack.window)

        self.add_meeting("2026-08-11", "Morgan", ai_summary="the Tuesday 1:1 happened")
        later = build_pack("Morgan", "2026-08-14", exclude_meeting_id=target)

        self.assertIn("You've met since",
                      CatchupBriefManager.staleness_notice(meta, later.window))

    def test_no_metadata_means_no_notice(self):
        pack, _ = self._pack()
        self.assertEqual(CatchupBriefManager.staleness_notice({}, pack.window), "")

    def test_corrupt_metadata_is_survivable(self):
        target = self.add_meeting("2026-08-11", "Morgan")
        conn = __import__("db").get_conn()
        conn.execute("UPDATE meetings SET catchup_meta='{not json' WHERE id=?", (target,))
        conn.commit()
        conn.close()
        self.assertEqual(CatchupBriefManager.load(self.meeting(target)), ("", {}))


if __name__ == "__main__":
    unittest.main()
