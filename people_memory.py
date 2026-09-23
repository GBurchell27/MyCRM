"""Known people memory from CRM contacts and past meeting notes."""

import attendees
from db import get_conn


def list_known_people():
    """Return sorted unique people names from contacts and meetings."""
    conn = get_conn()
    names = set()
    for (name,) in conn.execute(
        "SELECT name FROM contacts WHERE name IS NOT NULL AND TRIM(name) != ''"
    ):
        names.add(name.strip())
    for (person,) in conn.execute(
        "SELECT person FROM meetings WHERE person IS NOT NULL AND TRIM(person) != ''"
    ):
        # A group meeting names several people; each is a person you know.
        names.update(attendees.parse(person))
    for (manager,) in conn.execute(
        "SELECT manager FROM contacts WHERE manager IS NOT NULL AND TRIM(manager) != ''"
    ):
        names.add(manager.strip())
    conn.close()
    return sorted(names, key=str.casefold)


def find_contact_by_name(name):
    """Return the contact row matching this name (case-insensitive), or None."""
    cleaned = (name or "").strip()
    if not cleaned:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT * FROM contacts WHERE TRIM(name) = ? COLLATE NOCASE", (cleaned,)
    ).fetchone()
    conn.close()
    return row


def is_known_contact(name):
    """True when this person already has a CRM contact record."""
    return find_contact_by_name(name) is not None
