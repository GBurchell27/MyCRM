"""Works out what "since the last time I saw them" covers.

Given the people in a meeting and its date, resolves the *anchors* — for each
person, the previous meeting they were in that actually happened — and every
other meeting logged between the oldest of those and this one. Everything the
catch-up brief does is a projection of this window, so the rules live here on
their own and stay testable without a database or a window on screen.

A meeting with several people has several anchors, and a group meeting is the
anchor for everyone who was in it. That is what makes a follow-up 1:1 with one
attendee open with what the group agreed.

Meeting dates carry no time of day, so the anchor's whole day is included: the
app cannot tell whether Friday's other meetings ran before or after Friday's
1:1, and showing one meeting twice is cheaper than silently dropping one.
"""

from datetime import timedelta

import attendees
from config.app_settings import CATCHUP_FALLBACK_DAYS, CATCHUP_LOOKBACK_DAYS
from db import get_conn
from helpers import parse_meeting_date

# How far back the interim scan will reach when the last meeting was a long time
# ago, and the window used when there is no previous meeting at all. Both are
# defaults now: the settings dialog can move them, and every window records the
# figure it was actually built with so its description stays true.
MAX_LOOKBACK_DAYS = CATCHUP_LOOKBACK_DAYS.default
FALLBACK_LOOKBACK_DAYS = CATCHUP_FALLBACK_DAYS.default

CONTENT_FIELDS = ("agenda_items", "notes", "ai_summary", "transcript")


def field(row, key, default=""):
    """Read a column that may not exist on rows saved by an older version."""
    try:
        value = row[key]
    except (IndexError, KeyError):
        return default
    return default if value is None else value


def has_content(row):
    """True when a meeting row holds anything at all.

    Empty rows are the placeholders a recurring series generates ahead of time,
    plus weeks that were cancelled. Neither counts as "the last time I saw them",
    and neither is worth briefing on.
    """
    return any(str(field(row, key)).strip() for key in CONTENT_FIELDS)


def attended(row, person):
    """Was `person` in this meeting? True for a group meeting they were part of."""
    return attendees.includes(field(row, "person"), person)


def shares_anyone(row, people):
    """Does this meeting have anybody in common with `people`?"""
    return attendees.shares_anyone(field(row, "person"), people)


class AnchorSet:
    """The previous meetings a catch-up hangs off — one per person present.

    A group meeting anchors everyone who was in it, so it appears once here no
    matter how many of this meeting's people it covers.
    """

    def __init__(self, entries=(), missing=()):
        self._entries = list(entries)  # (person, row), in the order the people were listed
        self.missing = list(missing)   # people with no previous meeting at all
        self.rows = self._distinct_rows()

    def _distinct_rows(self):
        seen, rows = set(), []
        for _person, row in self._entries:
            if row["id"] in seen:
                continue
            seen.add(row["id"])
            rows.append(row)
        rows.sort(key=lambda row: (field(row, "date"), row["id"]))
        return rows

    def people_for(self, row):
        """Which of this meeting's people that anchor covers."""
        return [person for person, anchor in self._entries if anchor["id"] == row["id"]]

    @property
    def ids(self):
        return [row["id"] for row in self.rows]

    @property
    def primary(self):
        """The most recent anchor — what "last time" means without qualification."""
        return self.rows[-1] if self.rows else None

    @property
    def earliest_date(self):
        return field(self.rows[0], "date") if self.rows else ""

    @property
    def latest_date(self):
        return field(self.rows[-1], "date") if self.rows else ""

    def __bool__(self):
        return bool(self.rows)

    def __len__(self):
        return len(self.rows)


class CatchupWindow:
    """The stretch of time a catch-up brief covers."""

    def __init__(self, people, meeting_date, anchors, interim, start_date, capped=False,
                 lookback_days=MAX_LOOKBACK_DAYS):
        self.people = attendees.parse(people)
        self.meeting_date = meeting_date
        self.anchors = self._coerce(anchors)
        self.interim = interim
        self.start_date = start_date
        self.capped = capped
        self.lookback_days = lookback_days

    def _coerce(self, anchors):
        """Accept an AnchorSet, a bare meeting row, or None."""
        if isinstance(anchors, AnchorSet):
            return anchors
        if anchors is None:
            return AnchorSet(missing=self.people)
        return AnchorSet([(attendees.first(self.people), anchors)])

    @property
    def person(self):
        """The people as they read in a sentence — what the prompts are given."""
        return attendees.describe(self.people)

    @property
    def has_anchor(self):
        return bool(self.anchors)

    @property
    def anchor(self):
        return self.anchors.primary

    @property
    def anchor_date(self):
        """Where the window opens: the oldest "last time" among the people here."""
        return self.anchors.earliest_date

    @property
    def anchor_id(self):
        return self.anchors.primary["id"] if self.anchors else None

    @property
    def anchor_ids(self):
        return self.anchors.ids

    @property
    def source_meeting_ids(self):
        """Ids of the interim meetings, for staleness checks on a cached brief."""
        return [row["id"] for row in self.interim]

    @property
    def day_count(self):
        start = parse_meeting_date(self.start_date)
        end = parse_meeting_date(self.meeting_date)
        if not start or not end:
            return 0
        return (end - start).days + 1

    def describe(self):
        """One line for the panel header."""
        count = len(self.interim)
        meetings = f"{count} meeting{'s' if count != 1 else ''}"
        if not self.has_anchor:
            return (f"No previous meeting with {self.person} — showing the last "
                    f"{self.day_count} days ({meetings})")
        since = f"Since {self.anchor_date}"
        if self.capped:
            since += f" (showing the last {self.lookback_days} days)"
        line = f"{since} — {meetings}"
        if self.anchors.missing:
            line += f" · first time with {attendees.describe(self.anchors.missing)}"
        return line


def find_anchor(person, meeting_date, rows):
    """The most recent meeting `person` was in before `meeting_date` that happened.

    Rows without content are skipped, so an unfilled placeholder or a cancelled
    week widens the window instead of collapsing it to nothing. Where two rows
    share a person and date — which happens when a series laid a placeholder on
    top of a hand-written note — the later id wins, and the content filter has
    already dropped the empty one.
    """
    target = parse_meeting_date(meeting_date)
    if not target:
        return None
    best = None
    best_key = None
    for row in rows:
        day = parse_meeting_date(field(row, "date"))
        if not day or day >= target:
            continue
        if not attended(row, person):
            continue
        if not has_content(row):
            continue
        key = (day, row["id"])
        if best_key is None or key > best_key:
            best, best_key = row, key
    return best


def find_anchors(people, meeting_date, rows):
    """One anchor per person, plus whoever you have never met before."""
    entries, missing = [], []
    for person in people:
        anchor = find_anchor(person, meeting_date, rows)
        if anchor is None:
            missing.append(person)
        else:
            entries.append((person, anchor))
    return AnchorSet(entries, missing)


def resolve_window(person, meeting_date, rows, exclude_meeting_id=None,
                   max_lookback_days=None, fallback_lookback_days=None):
    """Build the CatchupWindow for a meeting. Pure — `rows` is every meeting.

    `person` is a person column: one name, or several for a group meeting.

    The two lookbacks default to the configured ones, read here rather than at
    import time so a change in the settings dialog applies to the next catch-up.
    """
    if max_lookback_days is None:
        max_lookback_days = CATCHUP_LOOKBACK_DAYS.get()
    if fallback_lookback_days is None:
        fallback_lookback_days = CATCHUP_FALLBACK_DAYS.get()

    people = attendees.parse(person)
    target = parse_meeting_date(meeting_date)
    if not target:
        return CatchupWindow(people, meeting_date, None, [], meeting_date,
                             lookback_days=max_lookback_days)

    anchors = find_anchors(people, meeting_date, rows)
    earliest = target - timedelta(days=max_lookback_days)
    capped = False
    if not anchors:
        start = target - timedelta(days=fallback_lookback_days)
    else:
        # The window opens at the oldest "last time", so nobody's open items are
        # left behind just because you saw one of the others more recently.
        start = parse_meeting_date(anchors.earliest_date)
        if start < earliest:
            start = earliest
            capped = True

    anchor_ids = set(anchors.ids)
    interim = []
    for row in rows:
        if exclude_meeting_id is not None and row["id"] == exclude_meeting_id:
            continue
        if row["id"] in anchor_ids:
            continue
        day = parse_meeting_date(field(row, "date"))
        if not day or day < start or day > target:
            continue
        # Meetings any of these people were already in are not news to them.
        if shares_anyone(row, people):
            continue
        if not has_content(row):
            continue
        interim.append(row)
    interim.sort(key=lambda row: (field(row, "date"), row["id"]))

    return CatchupWindow(people, meeting_date, anchors, interim, start.isoformat(), capped,
                         lookback_days=max_lookback_days)


def load_window(person, meeting_date, exclude_meeting_id=None):
    """Resolve the window straight from the database."""
    conn = get_conn()
    rows = conn.execute("SELECT * FROM meetings").fetchall()
    conn.close()
    return resolve_window(person, meeting_date, rows, exclude_meeting_id=exclude_meeting_id)
