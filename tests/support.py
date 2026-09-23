"""Test scaffolding: run each test against a throwaway database.

`db.get_conn` reads `db.DB_PATH` on every call, so pointing that at a temp file
redirects the whole app — no dependency injection needed in the modules
themselves.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import db  # noqa: E402  (path set up above)


class TempDbTestCase(unittest.TestCase):
    """Base case with an empty, real-schema database per test."""

    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self._previous_path = db.DB_PATH
        db.DB_PATH = os.path.join(self._tempdir.name, "test_crm.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self._previous_path
        self._tempdir.cleanup()

    # ------------------------------------------------------------- fixtures

    def add_meeting(self, meeting_date, person, agenda_items="", notes="",
                    ai_summary="", transcript="", recurring_id=None):
        conn = db.get_conn()
        cursor = conn.execute(
            "INSERT INTO meetings (date, person, agenda_items, notes, ai_summary, "
            "transcript, recurring_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (meeting_date, person, agenda_items, notes, ai_summary, transcript, recurring_id),
        )
        conn.commit()
        meeting_id = cursor.lastrowid
        conn.close()
        return meeting_id

    def all_meetings(self):
        conn = db.get_conn()
        rows = conn.execute("SELECT * FROM meetings ORDER BY date, id").fetchall()
        conn.close()
        return rows

    def meeting(self, meeting_id):
        conn = db.get_conn()
        row = conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
        conn.close()
        return row
