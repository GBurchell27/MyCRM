"""Editable meeting-date combo: upcoming week presets + custom dates."""

from tkinter import ttk

from helpers import (
    format_meeting_date_choice,
    parse_meeting_date,
    resolve_meeting_date_input,
    upcoming_week_date_choices,
)


class MeetingDateField:
    """Combobox for picking this week's dates or typing any YYYY-MM-DD."""

    def __init__(self, master, width=22):
        self.combo = ttk.Combobox(
            master,
            width=width,
            values=upcoming_week_date_choices(),
        )

    @property
    def widget(self):
        """The real widget underneath, for callers that need one (tooltips, focus)."""
        return self.combo

    def grid(self, **kwargs):
        self.combo.grid(**kwargs)

    def set(self, value):
        """Show a stored date, using a friendly label when it is this week."""
        day = parse_meeting_date(value)
        if day is None:
            self.combo.set((value or "").strip())
            return
        label = format_meeting_date_choice(day)
        choices = list(self.combo.cget("values"))
        if label in choices:
            self.combo.set(label)
        else:
            self.combo.set(day.isoformat())

    def get_raw(self):
        return self.combo.get().strip()

    def get_iso(self):
        """Return YYYY-MM-DD, '' if empty, or None if invalid."""
        return resolve_meeting_date_input(self.get_raw())

    def focus_set(self):
        self.combo.focus_set()
