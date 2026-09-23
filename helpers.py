"""Shared UI helpers."""

import json
import re
from datetime import date, timedelta

_ISO_DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def truncate(text, n=60):
    if not text:
        return ""
    text = text.replace("\n", " ")
    return text if len(text) <= n else text[: n - 1] + "…"


def parse_meeting_date(value):
    """Parse a YYYY-MM-DD meeting date, or None if missing/invalid."""
    if not value:
        return None
    try:
        return date.fromisoformat(str(value).strip())
    except ValueError:
        return None


def meeting_schedule_tag(value, today=None):
    """Return 'future', 'today', or '' for list-row styling."""
    meeting_day = parse_meeting_date(value)
    if meeting_day is None:
        return ""
    ref = today or date.today()
    if meeting_day > ref:
        return "future"
    if meeting_day == ref:
        return "today"
    return ""


def format_meeting_date_label(value, today=None):
    """Date cell text with Upcoming/Today prefix when relevant."""
    raw = (value or "").strip()
    tag = meeting_schedule_tag(raw, today=today)
    if tag == "future":
        return f"Upcoming · {raw}"
    if tag == "today":
        return f"Today · {raw}"
    return raw


def format_meeting_date_choice(day, today=None):
    """Friendly dropdown label that still embeds YYYY-MM-DD."""
    ref = today or date.today()
    iso = day.isoformat()
    if day == ref:
        return f"Today - {iso}"
    if day == ref + timedelta(days=1):
        return f"Tomorrow - {iso}"
    return f"{day.strftime('%a %d %b')} - {iso}"


def upcoming_week_date_choices(today=None, days=7):
    """Dropdown presets: today through the next several days."""
    ref = today or date.today()
    return [
        format_meeting_date_choice(ref + timedelta(days=offset), today=ref)
        for offset in range(days)
    ]


def resolve_meeting_date_input(value):
    """
    Turn combo text or a typed date into YYYY-MM-DD.
    Returns '' when empty, None when invalid.
    """
    text = (value or "").strip()
    if not text:
        return ""
    match = _ISO_DATE_RE.search(text)
    if not match:
        return None
    parsed = parse_meeting_date(match.group(1))
    return parsed.isoformat() if parsed else None


def parse_agenda_items(agenda_json):
    """Return the agenda item list stored as JSON, or [] when missing/corrupt."""
    try:
        items = json.loads(agenda_json) if agenda_json else []
    except (json.JSONDecodeError, TypeError):
        return []
    return items if isinstance(items, list) else []


def split_action_item(text, limit=60):
    """Split a long action item into a short title plus the full detail.

    Short items stay as a title with no detail, so nothing gets duplicated.
    """
    text = " ".join((text or "").split())
    if not text:
        return "", ""
    if len(text) <= limit:
        return text, ""
    head = text[: limit + 1]
    # Prefer the earliest natural break, so the title stays a readable phrase.
    breaks = [pos for sep in (" — ", " - ", ": ", ", ", ". ")
              if (pos := head.find(sep)) >= limit // 3]
    cut = min(breaks) if breaks else head.rfind(" ")
    if cut < limit // 3:
        cut = limit
    return text[:cut].rstrip(" —-:,.") + "…", text


def agenda_item_line(item, checked_mark="✔", unchecked_mark="○"):
    """One-line rendering of an agenda item for lists and exports."""
    mark = checked_mark if item.get("checked") else unchecked_mark
    title = str(item.get("text", ""))
    detail = str(item.get("detail", "") or "").strip()
    line = f"{mark} {title}"
    return f"{line} — {detail}" if detail else line


def agenda_progress_label(agenda_json):
    items = parse_agenda_items(agenda_json)
    if not items:
        return ""
    done = sum(1 for it in items if it.get("checked"))
    return f"{done}/{len(items)} done"
