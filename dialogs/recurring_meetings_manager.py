"""See and change every standing meeting in one place.

Adding a series was previously one-way — this is where you check who it's on
for, turn briefs on or off per person, and stop a series that has ended.
"""

import json
import tkinter as tk
from tkinter import ttk, messagebox

import help_text
from dialogs.recurring_meeting_dialog import RecurringMeetingDialog
from recurring_meetings import RecurringMeetingManager, WEEKDAY_NAMES
from widgets.tooltip import attach

SHORT_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def describe_weekdays(weekdays_json):
    try:
        days = json.loads(weekdays_json or "[]")
    except (json.JSONDecodeError, TypeError):
        return ""
    return ", ".join(SHORT_DAYS[d] for d in sorted(days) if 0 <= d <= 6)


class RecurringMeetingsManager(tk.Toplevel):
    def __init__(self, master, on_changed=None):
        super().__init__(master)
        self.title("Recurring meetings")
        self.geometry("560x340")
        self.minsize(460, 260)
        self.on_changed = on_changed

        header = ttk.Frame(self, padding=(12, 12, 12, 4))
        header.pack(fill="x")
        ttk.Label(
            header,
            text="People you meet on a repeating pattern",
            font=("Segoe UI", 10, "bold"),
        ).pack(side="left")
        add_btn = ttk.Button(header, text="+ Add", command=self.add_series)
        add_btn.pack(side="right")
        attach(add_btn, "Set up a new standing meeting.")

        ttk.Label(
            self,
            text="Blank notes are created a week ahead for each day you pick. "
                 "A brief summarises everything since you last saw that person.",
            foreground="#555555",
            wraplength=520,
            justify="left",
        ).pack(fill="x", padx=12)

        self.rows_frame = ttk.Frame(self, padding=12)
        self.rows_frame.pack(fill="both", expand=True)

        ttk.Button(self, text="Close", command=self.destroy).pack(
            side="bottom", anchor="e", padx=12, pady=(0, 12)
        )

        self.refresh()
        self.transient(master)

    def refresh(self):
        for child in self.rows_frame.winfo_children():
            child.destroy()
        series = RecurringMeetingManager.list_active()
        if not series:
            ttk.Label(
                self.rows_frame,
                text="No standing meetings yet.\n\n"
                     "Add one for anybody you see on a regular pattern — the app also "
                     "offers to set one up when it notices a pattern in your notes.",
                foreground="#777777",
                justify="left",
            ).pack(anchor="w")
            return
        for row in series:
            self._add_row(row)

    def _add_row(self, series):
        frame = ttk.Frame(self.rows_frame, padding=(0, 4))
        frame.pack(fill="x")

        text = ttk.Frame(frame)
        text.pack(side="left", fill="x", expand=True)
        ttk.Label(text, text=series["person"], font=("Segoe UI", 10)).pack(anchor="w")
        ttk.Label(
            text,
            text=describe_weekdays(series["weekdays"]) or "no days set",
            foreground="#666666",
        ).pack(anchor="w")

        stop_btn = ttk.Button(
            frame, text="Stop", width=6, command=lambda s=series: self.stop_series(s)
        )
        stop_btn.pack(side="right", padx=(6, 0))
        attach(stop_btn, help_text.RECURRING_STOP)

        brief_var = tk.BooleanVar(value=bool(series["catchup_enabled"]))
        brief_check = ttk.Checkbutton(
            frame,
            text="Auto brief",
            variable=brief_var,
            command=lambda s=series, v=brief_var: self.toggle_brief(s, v),
        )
        brief_check.pack(side="right")
        attach(brief_check, help_text.RECURRING_TOGGLE_BRIEF)

    def toggle_brief(self, series, var):
        RecurringMeetingManager.set_catchup_enabled(series["id"], var.get())
        if self.on_changed:
            self.on_changed()

    def stop_series(self, series):
        weekdays = describe_weekdays(series["weekdays"])
        if not messagebox.askyesno(
            "Stop recurring meeting",
            f"Stop creating notes for {series['person']} ({weekdays})?\n\n"
            "Notes you have already written are kept.",
            parent=self,
            icon="warning",
            default="no",
        ):
            return
        RecurringMeetingManager.deactivate(series["id"])
        self.refresh()
        if self.on_changed:
            self.on_changed()

    def add_series(self):
        RecurringMeetingDialog(self, on_saved=self._after_add)

    def _after_add(self):
        self.refresh()
        if self.on_changed:
            self.on_changed()
