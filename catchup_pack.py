"""Assembles everything that has happened since you last saw someone.

This is the deterministic half of the catch-up feature: pure SQL and text, no
network call. It is what the AI brief is generated *from*, and it stands on its
own when there is no API key — "here is what happened since Friday" is most of
the value even before a model touches it.
"""

import attendees
from helpers import agenda_item_line, parse_agenda_items
from carry_over import CLOSED_BY_TASK, CarryOverManager
from config.app_settings import CATCHUP_MEETING_CHARS
from meeting_window import field, load_window
from task_manager import TaskManager

# One long transcript must not crowd out four other meetings. Configurable —
# this is the default the setting starts at.
MAX_MEETING_CHARS = CATCHUP_MEETING_CHARS.default


def clamp(text, limit=None):
    if limit is None:
        limit = CATCHUP_MEETING_CHARS.get()
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n[…trimmed]"


class MeetingDigest:
    """One meeting's contribution to the pack."""

    def __init__(self, row):
        self.row = row

    @property
    def person(self):
        """Everyone who was in it, as it reads in a sentence."""
        return attendees.describe(field(self.row, "person")) or "(no person)"

    @property
    def date(self):
        return field(self.row, "date")

    @property
    def body(self):
        """The best available account of the meeting, in preference order."""
        for key in ("ai_summary", "notes", "transcript"):
            text = str(field(self.row, key)).strip()
            if text:
                return clamp(text)
        return ""

    @property
    def agenda_lines(self):
        items = parse_agenda_items(field(self.row, "agenda_items"))
        return [agenda_item_line(item) for item in items if str(item.get("text", "")).strip()]

    def render(self, heading_level="###", include_agenda=True):
        parts = [f"{heading_level} {self.person} — {self.date}"]
        if self.body:
            parts.append(self.body)
        if include_agenda and self.agenda_lines:
            parts.append("Action items:\n" + "\n".join(self.agenda_lines))
        return "\n\n".join(parts)


class CatchupPack:
    """The full picture for one catch-up: window, carried items, what closed."""

    def __init__(self, window, carried, closed, completed_tasks):
        self.window = window
        self.carried = carried
        self.closed = closed
        self.completed_tasks = completed_tasks

    @property
    def has_anything(self):
        return bool(self.window.interim or self.carried or self.closed
                    or self.completed_tasks or self.window.has_anchor)

    def headline(self):
        """Counts for the panel header."""
        bits = [self.window.describe()]
        if self.carried:
            bits.append(f"{len(self.carried)} open item{'s' if len(self.carried) != 1 else ''}")
        done = len(self.closed) + len(self.completed_tasks)
        if done:
            bits.append(f"{done} closed")
        return " · ".join(bits)

    # -------------------------------------------------------------- rendering

    def render(self):
        sections = [
            f"# Catch-up for {self.window.person} — {self.window.meeting_date}",
            self.headline(),
        ]
        sections.extend(
            part for part in (
                self._render_anchor(),
                self._render_closed(),
                self._render_completed_tasks(),
                self._render_carried(),
                self._render_interim(),
            ) if part
        )
        return "\n\n".join(sections).strip() + "\n"

    def _render_anchor(self):
        """"Last time" — one block per previous meeting the people here were in."""
        anchors = self.window.anchors
        if not anchors:
            return (
                f"## No previous meeting with {self.window.person} on record\n"
                f"Covering the {self.window.day_count} days up to this meeting instead."
            )
        blocks = [self._render_one_anchor(row) for row in anchors.rows]
        if anchors.missing:
            blocks.append(
                f"## No previous meeting with {attendees.describe(anchors.missing)} on record"
            )
        return "\n\n".join(blocks)

    def _render_one_anchor(self, row):
        digest = MeetingDigest(row)
        # The agenda is deliberately left out: the closed / still-open sections
        # below say the same thing and say it more usefully.
        covered = self.window.anchors.people_for(row)
        if len(self.window.people) == 1 or attendees.keys(covered) == attendees.keys(
            field(row, "person")
        ):
            # Only one person here, so who this was "last time" for is not in doubt.
            heading = f"## Last time — {digest.person}, {digest.date}"
        else:
            # One of several blocks: say which of them this one is the last time for.
            heading = (f"## Last time with {attendees.describe(covered)} — "
                       f"{digest.person}, {digest.date}")
        return f"{heading}\n\n{digest.body}" if digest.body else f"{heading}\n\n(nothing written up)"

    def _render_closed(self):
        if not self.closed:
            return ""
        lines = []
        for item in self.closed:
            if item.closed_by == CLOSED_BY_TASK:
                note = f"completed in Tasks {item.completed_at}"
            else:
                note = "ticked off in the meeting"
            line = f"- {item.title} ({note})"
            if item.detail:
                line += f"\n  {item.detail}"
            lines.append(line)
        return "## Closed since then\n" + "\n".join(lines)

    def _render_completed_tasks(self):
        if not self.completed_tasks:
            return ""
        lines = [
            f"- {task['title']} (completed {task['completed_at']})"
            for task in self.completed_tasks
        ]
        return "## Other tasks completed in this window\n" + "\n".join(lines)

    def _render_carried(self):
        if not self.carried:
            return ""
        lines = []
        for carried in self.carried:
            line = f"- {carried.item.get('text', '')}"
            detail = str(carried.item.get("detail", "") or "").strip()
            if detail:
                line += f" — {detail}"
            if carried.carried_count > 1:
                line += (f"  [still open after {carried.carried_count} meetings, "
                         f"first raised {carried.first_raised}]")
            lines.append(line)
        return "## Still open from last time\n" + "\n".join(lines)

    def _render_interim(self):
        if not self.window.interim:
            return "## Meetings since\nNone logged."
        digests = [MeetingDigest(row).render() for row in self.window.interim]
        return "## Meetings since\n\n" + "\n\n".join(digests)


def build_pack(person, meeting_date, exclude_meeting_id=None):
    """Assemble the pack for a meeting with `person` on `meeting_date`.

    `person` may name several people; open items then come forward from each
    one's last meeting, deduped.
    """
    window = load_window(person, meeting_date, exclude_meeting_id=exclude_meeting_id)
    carried, closed = CarryOverManager.split_anchors(window.anchors.rows)
    completed_tasks = _other_completed_tasks(window, closed)
    return CatchupPack(window, carried, closed, completed_tasks)


def _other_completed_tasks(window, closed):
    """Tasks finished in the window that aren't already reported as closed items."""
    already_reported = {
        item.item.get("task_id") for item in closed if item.item.get("task_id") is not None
    }
    return [
        task
        for task in TaskManager.completed_between(window.start_date, window.meeting_date)
        if task["id"] not in already_reported
    ]
