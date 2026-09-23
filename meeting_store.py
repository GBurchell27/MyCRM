"""Targeted reads and writes against a single meetings row.

The meetings tab owns saving a whole note from the editor. Derived data —
carried-forward items, a generated catch-up brief — needs to update one column
without touching what the user is typing, which is what these do.
"""

import json

from db import get_conn


def load_meeting(meeting_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM meetings WHERE id=?", (meeting_id,)).fetchone()
    conn.close()
    return row


def update_agenda_items(meeting_id, items):
    """Persist the agenda list without disturbing notes, summary or media."""
    conn = get_conn()
    conn.execute(
        "UPDATE meetings SET agenda_items=? WHERE id=?",
        (json.dumps(items), meeting_id),
    )
    conn.commit()
    conn.close()


def update_catchup(meeting_id, brief, meta):
    """Store a generated brief and the metadata describing what it covered."""
    conn = get_conn()
    conn.execute(
        "UPDATE meetings SET catchup_brief=?, catchup_meta=? WHERE id=?",
        (brief or "", json.dumps(meta or {}), meeting_id),
    )
    conn.commit()
    conn.close()
