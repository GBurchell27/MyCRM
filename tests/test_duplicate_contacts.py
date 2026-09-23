"""Fuzzy duplicate-contact matching must catch typos without over-matching."""

import unittest

from support import TempDbTestCase

import db
from duplicate_contacts import find_possible_duplicates, normalize_name


class FindPossibleDuplicatesTests(TempDbTestCase):
    def _add_contact(self, name, role="", team="", office=""):
        conn = db.get_conn()
        cursor = conn.execute(
            "INSERT INTO contacts (name, role, team, office) VALUES (?, ?, ?, ?)",
            (name, role, team, office),
        )
        conn.commit()
        contact_id = cursor.lastrowid
        conn.close()
        return contact_id

    def test_exact_name_match(self):
        self._add_contact("Casey Schmidt")
        matches = find_possible_duplicates("Casey Schmidt")
        self.assertEqual([row["name"] for row in matches], ["Casey Schmidt"])

    def test_case_and_padding_insensitive(self):
        self._add_contact("Casey Schmidt")
        matches = find_possible_duplicates("  casey schmidt ")
        self.assertEqual(len(matches), 1)

    def test_single_typo_still_matches(self):
        self._add_contact("Robin van Dijk")
        matches = find_possible_duplicates("Robin van Dyk")
        self.assertEqual([row["name"] for row in matches], ["Robin van Dijk"])

    def test_word_reorder_matches(self):
        self._add_contact("Casey Schmidt")
        matches = find_possible_duplicates("Schmidt Casey")
        self.assertEqual(len(matches), 1)

    def test_clearly_different_name_does_not_match(self):
        self._add_contact("Casey Schmidt")
        matches = find_possible_duplicates("Priya Natarajan")
        self.assertEqual(matches, [])

    def test_exclude_id_skips_the_record_being_edited(self):
        contact_id = self._add_contact("Casey Schmidt")
        matches = find_possible_duplicates("Casey Schmidt", exclude_id=contact_id)
        self.assertEqual(matches, [])

    def test_best_match_sorts_first(self):
        self._add_contact("Robin van Dijk")
        self._add_contact("Robin")
        matches = find_possible_duplicates("Robin van Dyk")
        self.assertEqual(matches[0]["name"], "Robin van Dijk")

    def test_blank_name_returns_no_matches(self):
        self._add_contact("Casey Schmidt")
        self.assertEqual(find_possible_duplicates("   "), [])


class NormalizeNameTests(unittest.TestCase):
    def test_collapses_whitespace_and_case(self):
        self.assertEqual(normalize_name("  Casey   Schmidt "), "casey schmidt")

    def test_none_is_empty_string(self):
        self.assertEqual(normalize_name(None), "")


if __name__ == "__main__":
    unittest.main()
