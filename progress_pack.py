"""Assembles everything that happened between two dates, for a progress update.

The catch-up pack answers "what has happened since I last saw this person" and
is anchored on that person's last meeting. This one answers a different
question — "what have I been up to between these two dates" — so it is anchored
on a date range and reads across every meeting rather than skipping the ones
one person was already in. That is the shape you need when someone comes back
from holiday.

Deterministic: pure SQL and text, no network call. It is what the AI update is
written from, and it stands on its own when there is no API key.
"""

from datetime import date, timedelta

import attendees
from catchup_pack import MeetingDigest
from db import get_conn
from helpers import parse_agenda_items, parse_meeting_date
from meeting_window import field, has_content
from task_manager import TaskManager

# Two weeks is the default because it is the length of the holiday this exists
# to cover. The dialog can move both ends.
DEFAULT_LOOKBACK_DAYS = 14


def default_range(today=None, lookback_days=DEFAULT_LOOKBACK_DAYS):
    """(start, end) as ISO dates: the last fortnight up to and including today."""
    end = today or date.today()
    return (end - timedelta(days=lookback_days - 1)).isoformat(), end.isoformat()


def valid_range(start_date, end_date):
    """True when both dates parse and the range runs forwards."""
    start, end = parse_meeting_date(start_date), parse_meeting_date(end_date)
    return bool(start and end and start <= end)


class AgendaItem:
    """One agenda line lifted out of a meeting, with where it came from."""

    def __init__(self, text, detail, person, meeting_date):
        self.text = text
        self.detail = detail
        self.person = person
        self.date = meeting_date

    def render(self):
        line = f"- {self.text}"
        if self.detail:
            line += f" — {self.detail}"
        return f"{line}  [{self.person}, {self.date}]"


class ProgressPack:
    """Everything that happened in one window: meetings, closed work, open work."""

    def __init__(self, start_date, end_date, meetings, completed_tasks, closed_items,
                 open_items):
        self.start_date = start_date
        self.end_date = end_date
        self.meetings = meetings
        self.completed_tasks = completed_tasks
        self.closed_items = closed_items
        self.open_items = open_items

    @property
    def day_count(self):
        start, end = parse_meeting_date(self.start_date), parse_meeting_date(self.end_date)
        return (end - start).days + 1 if start and end else 0

    @property
    def has_anything(self):
        return bool(self.meetings or self.completed_tasks or self.closed_items
                    or self.open_items)

    @property
    def people(self):
        """Who was met in the window, in the order they first appear.

        Counted one by one, so a meeting with three people is three people.
        """
        seen = []
        for row in self.meetings:
            for person in attendees.parse(field(row, "person")):
                if person not in seen:
                    seen.append(person)
        return seen

    def headline(self):
        """Counts for the dialog header."""
        done = len(self.completed_tasks) + len(self.closed_items)
        bits = [
            f"{self.start_date} → {self.end_date} ({self.day_count} days)",
            f"{len(self.meetings)} meeting{'s' if len(self.meetings) != 1 else ''}",
            f"{len(self.people)} {'person' if len(self.people) == 1 else 'people'}",
            f"{done} item{'s' if done != 1 else ''} closed",
        ]
        if self.open_items:
            bits.append(f"{len(self.open_items)} still open")
        return " · ".join(bits)

    # -------------------------------------------------------------- rendering

    def render(self):
        sections = [
            f"# Progress {self.start_date} to {self.end_date}",
            self.headline(),
        ]
        sections.extend(
            part for part in (
                self._render_completed_tasks(),
                self._render_closed_items(),
                self._render_open_items(),
                self._render_meetings(),
            ) if part
        )
        return "\n\n".join(sections).strip() + "\n"

    def _render_completed_tasks(self):
        if not self.completed_tasks:
            return ""
        lines = []
        for task in self.completed_tasks:
            line = f"- {task['title']} (completed {task['completed_at']})"
            notes = str(task["notes"] or "").strip()
            if notes:
                line += f"\n  {notes}"
            lines.append(line)
        return "## Tasks completed\n" + "\n".join(lines)

    def _render_closed_items(self):
        if not self.closed_items:
            return ""
        return ("## Action items ticked off in meetings\n"
                + "\n".join(item.render() for item in self.closed_items))

    def _render_open_items(self):
        if not self.open_items:
            return ""
        return ("## Still open\n"
                + "\n".join(item.render() for item in self.open_items))

    def _render_meetings(self):
        if not self.meetings:
            return "## Meetings\nNone logged in this window."
        digests = [
            MeetingDigest(row).render(include_agenda=False) for row in self.meetings
        ]
        return "## Meetings\n\n" + "\n\n".join(digests)


def load_meetings(start_date, end_date):
    """Meetings dated in [start, end] that actually hold something."""
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM meetings WHERE date >= ? AND date <= ? ORDER BY date, id",
        (start_date, end_date),
    ).fetchall()
    conn.close()
    return [row for row in rows if has_content(row)]


def split_agenda_items(meetings):
    """(closed, open) agenda items across the window, each tagged with its meeting."""
    closed, still_open = [], []
    for row in meetings:
        person = attendees.describe(field(row, "person")) or "(no person)"
        meeting_date = field(row, "date")
        for raw in parse_agenda_items(field(row, "agenda_items")):
            text = str(raw.get("text", "") or "").strip()
            if not text:
                continue
            item = AgendaItem(
                text, str(raw.get("detail", "") or "").strip(), person, meeting_date
            )
            (closed if raw.get("checked") else still_open).append(item)
    return closed, still_open


def build_pack(start_date, end_date):
    """Assemble the pack for the window [start_date, end_date], both inclusive."""
    meetings = load_meetings(start_date, end_date)
    closed_items, open_items = split_agenda_items(meetings)
    completed_tasks = TaskManager.completed_between(start_date, end_date)
    return ProgressPack(start_date, end_date, meetings, completed_tasks,
                        closed_items, open_items)
