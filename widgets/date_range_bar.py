"""From/to date entries with the presets people actually ask for.

A dumb view: it holds two dates, offers the common windows as one-click presets,
and calls back when the range changes. Working out what a range means is the
caller's job.
"""

import tkinter as tk
from datetime import date, timedelta
from tkinter import ttk

from helpers import resolve_meeting_date_input

# (button label, days the window covers, counting the end date itself)
PRESETS = [
    ("Last week", 7),
    ("Last 2 weeks", 14),
    ("Last month", 30),
]


class DateRangeBar(ttk.Frame):
    def __init__(self, master, start_date="", end_date="", on_change=None, **kwargs):
        kwargs.setdefault("padding", (0, 0, 0, 6))
        super().__init__(master, **kwargs)
        self.on_change = on_change

        self.start_var = tk.StringVar(value=start_date)
        self.end_var = tk.StringVar(value=end_date)

        ttk.Label(self, text="From").pack(side="left")
        self._entry(self.start_var).pack(side="left", padx=(4, 10))
        ttk.Label(self, text="To").pack(side="left")
        self._entry(self.end_var).pack(side="left", padx=(4, 12))

        for label, days in PRESETS:
            ttk.Button(
                self,
                text=label,
                width=max(10, len(label) + 1),
                command=lambda d=days: self.apply_preset(d),
            ).pack(side="left", padx=(0, 4))

    def _entry(self, variable):
        entry = ttk.Entry(self, textvariable=variable, width=12)
        entry.bind("<Return>", lambda _event: self._changed())
        entry.bind("<FocusOut>", lambda _event: self._changed())
        return entry

    def apply_preset(self, days, today=None):
        """Set the window to the `days` days ending today."""
        end = today or date.today()
        self.start_var.set((end - timedelta(days=days - 1)).isoformat())
        self.end_var.set(end.isoformat())
        self._changed()

    def _changed(self):
        if self.on_change:
            self.on_change()

    # ------------------------------------------------------------------ state

    def get_range(self):
        """(start, end) as YYYY-MM-DD; either is '' if blank or None if unreadable."""
        return (
            resolve_meeting_date_input(self.start_var.get()),
            resolve_meeting_date_input(self.end_var.get()),
        )

    def set_enabled(self, enabled):
        state = "normal" if enabled else "disabled"
        for child in self.winfo_children():
            if isinstance(child, (ttk.Entry, ttk.Button)):
                child.configure(state=state)
