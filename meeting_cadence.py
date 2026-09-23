"""Notices when someone has quietly become a regular.

The catch-up window already works for anybody with a previous meeting. What it
can't do by itself is spot that you've started seeing someone every week and
offer to set that up — which is what this is for.
"""

from collections import Counter

from db import get_conn
from helpers import parse_meeting_date
from meeting_window import attended, field, has_content

MIN_MEETINGS = 3
MIN_AVERAGE_GAP_DAYS = 1
MAX_AVERAGE_GAP_DAYS = 21

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


class MeetingCadence:
    """How often you actually meet someone, read off your notes."""

    def __init__(self, person, dates):
        self.person = person
        self.dates = dates

    @property
    def meeting_count(self):
        return len(self.dates)

    @property
    def average_gap_days(self):
        if self.meeting_count < 2:
            return 0.0
        span = (self.dates[-1] - self.dates[0]).days
        return span / (self.meeting_count - 1)

    @property
    def weekday_pattern(self):
        """The weekdays worth pre-booking: those you've met on more than once.

        Falls back to the single most common day, so a fortnightly meeting still
        suggests something sensible.
        """
        counts = Counter(day.weekday() for day in self.dates)
        repeated = sorted(day for day, n in counts.items() if n >= 2)
        if repeated:
            return repeated
        return [counts.most_common(1)[0][0]] if counts else []

    @property
    def looks_regular(self):
        if self.meeting_count < MIN_MEETINGS:
            return False
        gap = self.average_gap_days
        if not MIN_AVERAGE_GAP_DAYS <= gap <= MAX_AVERAGE_GAP_DAYS:
            return False
        return bool(self.weekday_pattern)

    def describe_frequency(self):
        gap = self.average_gap_days
        if gap <= 4:
            return "a couple of times a week"
        if gap <= 10:
            return "about weekly"
        if gap <= 17:
            return "about every two weeks"
        return "about every three weeks"

    def describe(self):
        """One line offering the observation back to the user."""
        days = [WEEKDAY_NAMES[day] for day in self.weekday_pattern]
        if len(days) == 1:
            when = f" on {days[0]}s"
        elif len(days) == 2:
            when = f" on {days[0]}s and {days[1]}s"
        else:
            when = ""
        return (
            f"You've met {self.person} {self.meeting_count} times, "
            f"{self.describe_frequency()}{when}."
        )


def analyse(person, rows):
    """Read the cadence for `person` out of every meeting row.

    Group meetings they were part of count: you have still seen them.
    """
    dates = sorted(
        day
        for row in rows
        if attended(row, person) and has_content(row)
        for day in [parse_meeting_date(field(row, "date"))]
        if day is not None
    )
    return MeetingCadence((person or "").strip(), dates)


def load_cadence(person):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM meetings").fetchall()
    conn.close()
    return analyse(person, rows)
