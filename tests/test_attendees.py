"""The one place that knows a meeting's person column can name several people."""

import unittest

from support import TempDbTestCase  # noqa: F401  (keeps sys.path set up)

import attendees


class ParseTests(unittest.TestCase):
    def test_a_single_name_is_one_person(self):
        self.assertEqual(attendees.parse("Morgan"), ["Morgan"])

    def test_the_canonical_separator_splits(self):
        self.assertEqual(
            attendees.parse("Pat Quinn; Erin; Jordan Lee"),
            ["Pat Quinn", "Erin", "Jordan Lee"],
        )

    def test_typed_separators_are_understood_too(self):
        self.assertEqual(attendees.parse("Pat & Erin"), ["Pat", "Erin"])
        self.assertEqual(attendees.parse("Pat and Erin"), ["Pat", "Erin"])

    def test_a_comma_stays_inside_one_name(self):
        """Surname-first names must survive: "Quinn, Pat" is one person."""
        self.assertEqual(attendees.parse("Quinn, Pat"), ["Quinn, Pat"])

    def test_padding_and_repeats_are_dropped(self):
        self.assertEqual(attendees.parse("  Erin ;; erin ;Pat  "), ["Erin", "Pat"])

    def test_a_list_is_cleaned_the_same_way(self):
        self.assertEqual(attendees.parse(["Erin", " ", "ERIN", "Pat"]), ["Erin", "Pat"])

    def test_nothing_parses_to_nobody(self):
        self.assertEqual(attendees.parse(""), [])
        self.assertEqual(attendees.parse(None), [])


class MembershipTests(unittest.TestCase):
    def test_a_person_is_found_inside_a_group(self):
        self.assertTrue(attendees.includes("Pat Quinn; Erin", "erin"))
        self.assertTrue(attendees.includes("Pat Quinn; Erin", "  Pat Quinn "))

    def test_a_partial_name_is_not_a_match(self):
        self.assertFalse(attendees.includes("Pat Quinn; Erin", "Pat"))

    def test_nobody_is_never_a_match(self):
        self.assertFalse(attendees.includes("Pat Quinn", ""))

    def test_overlap_between_two_meetings(self):
        self.assertTrue(attendees.shares_anyone("Pat; Erin", ["Sam", "Erin"]))
        self.assertFalse(attendees.shares_anyone("Pat; Erin", ["Sam"]))


class FormattingTests(unittest.TestCase):
    def test_the_stored_form_is_semicolon_separated(self):
        self.assertEqual(attendees.join(["Pat Quinn", "Erin"]), "Pat Quinn; Erin")

    def test_the_spoken_form_reads_as_a_sentence(self):
        self.assertEqual(attendees.describe("Morgan"), "Morgan")
        self.assertEqual(attendees.describe("Pat; Erin"), "Pat and Erin")
        self.assertEqual(attendees.describe("Pat; Erin; Sam"), "Pat, Erin and Sam")


if __name__ == "__main__":
    unittest.main()
