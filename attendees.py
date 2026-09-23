"""Who was in a meeting.

A meeting note's `person` column holds one name for a 1:1 and several for a
group meeting, joined with "; ". Reusing the column the app already has means
every note ever written is already a valid one-attendee meeting — no migration,
and search, export and the meetings list keep working on the raw string.

Every question the rest of the app asks about that column — was this person
there, who else was, how does it read in a sentence — is answered here, so no
other module has to know the format.
"""

import re

SEPARATOR = "; "

# What counts as "and then this person". Commas are deliberately left alone:
# "Quinn, Pat" is one person, and the attendees field adds names one at a time
# so nobody has to type a separator at all.
_SPLIT = re.compile(r"[;\n&]+|\s+\band\b\s+", re.IGNORECASE)


def parse(value):
    """The names in a person column (or a list), in order, without duplicates."""
    parts = value if isinstance(value, (list, tuple, set)) else _SPLIT.split(str(value or ""))
    names, seen = [], set()
    for part in parts:
        name = " ".join(str(part).split())
        key = name.casefold()
        if not name or key in seen:
            continue
        seen.add(key)
        names.append(name)
    return names


def join(names):
    """The canonical stored form of a set of names."""
    return SEPARATOR.join(parse(names))


def keys(value):
    """Casefolded names, for membership tests."""
    return {name.casefold() for name in parse(value)}


def includes(value, person):
    """Was `person` in this meeting?"""
    wanted = " ".join(str(person or "").split()).casefold()
    return bool(wanted) and wanted in keys(value)


def shares_anyone(value, people):
    """Does this meeting have anybody in common with `people`?"""
    return bool(keys(value) & keys(people))


def count(value):
    return len(parse(value))


def first(value):
    names = parse(value)
    return names[0] if names else ""


def describe(value):
    """The names as they read in a sentence: "Pat, Erin and Sam"."""
    names = parse(value)
    if not names:
        return ""
    if len(names) == 1:
        return names[0]
    return f"{', '.join(names[:-1])} and {names[-1]}"
