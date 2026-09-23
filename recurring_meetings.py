"""Business logic for recurring meeting series that auto-populate upcoming meeting notes.

A series just remembers a person + weekday pattern (Monday=0 .. Sunday=6, per
date.weekday()). Placeholder meeting notes (date + person filled in, everything
else blank) are generated out to HORIZON_DAYS ahead. Every generated date is
logged in recurring_occurrences so a placeholder that gets deleted (meeting
cancelled that week) never gets silently recreated on the next top-up.
"""

import json
from datetime import date, timedelta

import attendees
from config.app_settings import RECURRING_HORIZON_DAYS
from db import get_conn

# The default horizon; the settings dialog moves it.
HORIZON_DAYS = RECURRING_HORIZON_DAYS.default

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class RecurringMeetingManager:
    @staticmethod
    def create(person, weekdays, catchup_enabled=True):
        person = (person or "").strip()
        if not person:
            raise ValueError("Person is required")
        weekdays = sorted({int(d) for d in weekdays if 0 <= int(d) <= 6})
        if not weekdays:
            raise ValueError("Pick at least one day of the week")
        conn = get_conn()
        cursor = conn.execute(
            "INSERT INTO recurring_meetings (person, weekdays, active, catchup_enabled) "
            "VALUES (?, ?, 1, ?)",
            (person, json.dumps(weekdays), 1 if catchup_enabled else 0),
        )
        conn.commit()
        recurring_id = cursor.lastrowid
        conn.close()
        RecurringMeetingManager._fill_occurrences(recurring_id, person, weekdays)
        return recurring_id

    @staticmethod
    def list_active():
        conn = get_conn()
        rows = conn.execute(
            "SELECT * FROM recurring_meetings WHERE active=1 ORDER BY person"
        ).fetchall()
        conn.close()
        return rows

    @staticmethod
    def series_for_person(person):
        """The active series for this person, or None."""
        cleaned = (person or "").strip()
        if not cleaned:
            return None
        conn = get_conn()
        row = conn.execute(
            "SELECT * FROM recurring_meetings WHERE active=1 "
            "AND TRIM(person)=? COLLATE NOCASE LIMIT 1",
            (cleaned,),
        ).fetchone()
        conn.close()
        return row

    @staticmethod
    def set_catchup_enabled(recurring_id, enabled):
        conn = get_conn()
        conn.execute(
            "UPDATE recurring_meetings SET catchup_enabled=? WHERE id=?",
            (1 if enabled else 0, recurring_id),
        )
        conn.commit()
        conn.close()

    @staticmethod
    def catchup_enabled(recurring_id):
        """True when occurrences of this series should brief themselves on open."""
        if recurring_id is None:
            return False
        conn = get_conn()
        row = conn.execute(
            "SELECT catchup_enabled FROM recurring_meetings WHERE id=?", (recurring_id,)
        ).fetchone()
        conn.close()
        return bool(row["catchup_enabled"]) if row else False

    @staticmethod
    def deactivate(recurring_id):
        conn = get_conn()
        conn.execute("UPDATE recurring_meetings SET active=0 WHERE id=?", (recurring_id,))
        conn.commit()
        conn.close()

    @staticmethod
    def _meeting_already_booked(conn, person, iso_date):
        """True when a meeting note with this person already sits on this date.

        Stops a series from laying an empty placeholder on top of a note you
        already wrote by hand — a duplicate that hides the real note from the
        catch-up window's "when did I last see them" lookup. A group meeting
        they are part of counts: you are already seeing them that day.
        """
        rows = conn.execute(
            "SELECT person FROM meetings WHERE date=?", (iso_date,)
        ).fetchall()
        return any(attendees.includes(row["person"], person) for row in rows)

    @classmethod
    def _fill_occurrences(cls, recurring_id, person, weekdays, today=None):
        """Insert a placeholder meeting note for every not-yet-handled occurrence up to the horizon."""
        today = today or date.today()
        horizon = today + timedelta(days=RECURRING_HORIZON_DAYS.get())
        conn = get_conn()
        handled = {
            row["occurrence_date"]
            for row in conn.execute(
                "SELECT occurrence_date FROM recurring_occurrences WHERE recurring_id=?",
                (recurring_id,),
            ).fetchall()
        }
        day = today
        while day <= horizon:
            iso = day.isoformat()
            if day.weekday() in weekdays and iso not in handled:
                if not cls._meeting_already_booked(conn, person, iso):
                    conn.execute(
                        "INSERT INTO meetings (date, person, agenda_items, notes, ai_summary, recurring_id) "
                        "VALUES (?, ?, '', '', '', ?)",
                        (iso, person, recurring_id),
                    )
                # Logged either way: the date is handled, so a later top-up must
                # not try again.
                conn.execute(
                    "INSERT INTO recurring_occurrences (recurring_id, occurrence_date) VALUES (?, ?)",
                    (recurring_id, iso),
                )
            day += timedelta(days=1)
        conn.commit()
        conn.close()

    @classmethod
    def top_up_all(cls, today=None):
        """Call on app startup to keep every active series populated up to the horizon."""
        for row in cls.list_active():
            cls._fill_occurrences(
                row["id"], row["person"], json.loads(row["weekdays"]), today=today
            )
