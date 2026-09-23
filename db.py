"""SQLite access for CRM contacts, meeting notes, and tasks."""

import sqlite3
import os

from offices import match_office
from paths import APP_DIR

DB_PATH = os.path.join(APP_DIR, "crm_data.db")


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS contacts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        met_on TEXT,
        name TEXT,
        team TEXT,
        role TEXT,
        manager TEXT,
        how_we_met TEXT,
        notes TEXT
    )""")
    contact_columns = {
        column[1] for column in c.execute("PRAGMA table_info(contacts)").fetchall()
    }
    if "office" not in contact_columns:
        c.execute("ALTER TABLE contacts ADD COLUMN office TEXT DEFAULT ''")
        _split_offices_out_of_team(c)
    c.execute("""CREATE TABLE IF NOT EXISTS meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        date TEXT,
        person TEXT,
        agenda_items TEXT,
        notes TEXT,
        ai_summary TEXT DEFAULT ''
    )""")
    meeting_columns = {
        column[1] for column in c.execute("PRAGMA table_info(meetings)").fetchall()
    }
    if "ai_summary" not in meeting_columns:
        c.execute("ALTER TABLE meetings ADD COLUMN ai_summary TEXT DEFAULT ''")
    if "recurring_id" not in meeting_columns:
        c.execute("ALTER TABLE meetings ADD COLUMN recurring_id INTEGER")
    if "transcript" not in meeting_columns:
        c.execute("ALTER TABLE meetings ADD COLUMN transcript TEXT DEFAULT ''")
    if "media_paths" not in meeting_columns:
        c.execute("ALTER TABLE meetings ADD COLUMN media_paths TEXT DEFAULT ''")
    if "catchup_brief" not in meeting_columns:
        c.execute("ALTER TABLE meetings ADD COLUMN catchup_brief TEXT DEFAULT ''")
    if "catchup_meta" not in meeting_columns:
        c.execute("ALTER TABLE meetings ADD COLUMN catchup_meta TEXT DEFAULT ''")
    c.execute("""CREATE TABLE IF NOT EXISTS app_settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        title TEXT NOT NULL,
        notes TEXT DEFAULT '',
        created_at TEXT NOT NULL,
        completed_at TEXT
    )""")
    task_columns = {
        column[1] for column in c.execute("PRAGMA table_info(tasks)").fetchall()
    }
    if "tag" not in task_columns:
        c.execute("ALTER TABLE tasks ADD COLUMN tag TEXT DEFAULT ''")
    c.execute("""CREATE TABLE IF NOT EXISTS recurring_meetings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        person TEXT NOT NULL,
        weekdays TEXT NOT NULL,
        active INTEGER DEFAULT 1
    )""")
    recurring_columns = {
        column[1] for column in c.execute("PRAGMA table_info(recurring_meetings)").fetchall()
    }
    if "catchup_enabled" not in recurring_columns:
        c.execute(
            "ALTER TABLE recurring_meetings ADD COLUMN catchup_enabled INTEGER DEFAULT 1"
        )
    c.execute("""CREATE TABLE IF NOT EXISTS recurring_occurrences (
        recurring_id INTEGER NOT NULL,
        occurrence_date TEXT NOT NULL,
        PRIMARY KEY (recurring_id, occurrence_date)
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS board_nodes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        kind TEXT NOT NULL DEFAULT 'contact',
        contact_id INTEGER,
        label TEXT DEFAULT '',
        x REAL NOT NULL DEFAULT 0,
        y REAL NOT NULL DEFAULT 0,
        notes TEXT DEFAULT '',
        color TEXT DEFAULT ''
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS board_edges (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        from_node INTEGER NOT NULL,
        to_node INTEGER NOT NULL,
        kind TEXT NOT NULL DEFAULT 'works_with',
        label TEXT DEFAULT ''
    )""")
    conn.commit()
    conn.close()


def _split_offices_out_of_team(cursor):
    """One-off backfill: `team` used to hold places as well as functions.

    Rows whose team names a known office ("Stockholm") move that value into
    the new office column; anything else ("Sales") is left alone.
    """
    for contact_id, team in cursor.execute("SELECT id, team FROM contacts").fetchall():
        office = match_office(team)
        if office:
            cursor.execute(
                "UPDATE contacts SET office=?, team='' WHERE id=?", (office, contact_id)
            )


def get_setting(key, default=""):
    conn = get_conn()
    row = conn.execute("SELECT value FROM app_settings WHERE key=?", (key,)).fetchone()
    conn.close()
    return row[0] if row else default


def set_setting(key, value):
    conn = get_conn()
    conn.execute(
        "INSERT INTO app_settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()
