"""A stray non-UTF-8 byte in the database must never stop the app opening."""

import unittest

from support import TempDbTestCase

import db
from db import decode_stored_text
from task_manager import TaskManager


class DecodeStoredTextTests(unittest.TestCase):
    def test_valid_utf8_is_decoded_as_is(self):
        self.assertEqual(decode_stored_text("André".encode("utf-8")), "André")

    def test_windows_1252_bytes_are_recovered(self):
        self.assertEqual(decode_stored_text(b"Andr\xe9"), "André")


class LegacyEncodedRowTests(TempDbTestCase):
    def test_active_tasks_load_despite_a_windows_1252_title(self):
        task_id = TaskManager.create_task("placeholder")
        conn = db.get_conn()
        conn.execute(
            "UPDATE tasks SET title = CAST(? AS TEXT) WHERE id = ?",
            (b"Privacy assessment with Andr\xe9", task_id),
        )
        conn.commit()
        conn.close()

        titles = [row["title"] for row in TaskManager.list_active()]

        self.assertIn("Privacy assessment with André", titles)


if __name__ == "__main__":
    unittest.main()
