"""Dialog to set up a recurring meeting series (person + day-of-week pattern)."""

import tkinter as tk
from tkinter import ttk, messagebox

import help_text
from people_memory import list_known_people
from recurring_meetings import RecurringMeetingManager, WEEKDAY_NAMES
from widgets.tooltip import attach_all


class RecurringMeetingDialog(tk.Toplevel):
    def __init__(self, master, on_saved, person="", weekdays=()):
        super().__init__(master)
        self.title("Add Recurring Meeting")
        self.on_saved = on_saved
        self.resizable(False, False)

        form = ttk.Frame(self, padding=12)
        form.pack(fill="both", expand=True)

        ttk.Label(form, text="Person:").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.person_combo = ttk.Combobox(form, width=28, values=list_known_people())
        self.person_combo.grid(row=0, column=1, sticky="w", pady=(0, 8))

        self.person_combo.set(person)

        days_label = ttk.Label(form, text="Repeats every:")
        days_label.grid(row=1, column=0, sticky="nw")
        days_frame = ttk.Frame(form)
        days_frame.grid(row=1, column=1, sticky="w")
        self.day_vars = []
        preselected = set(weekdays or ())
        for i, name in enumerate(WEEKDAY_NAMES):
            var = tk.BooleanVar(value=i in preselected)
            ttk.Checkbutton(days_frame, text=name, variable=var).grid(
                row=i, column=0, sticky="w"
            )
            self.day_vars.append(var)

        self.catchup_var = tk.BooleanVar(value=True)
        catchup_check = ttk.Checkbutton(
            form,
            text="Prepare a catch-up brief for each meeting",
            variable=self.catchup_var,
        )
        catchup_check.grid(row=2, column=0, columnspan=2, sticky="w", pady=(10, 0))
        attach_all([
            (self.person_combo, help_text.MEETING_PERSON),
            (days_label, help_text.RECURRING_DAYS),
            (days_frame, help_text.RECURRING_DAYS),
            (catchup_check, help_text.RECURRING_CATCHUP),
        ])
        ttk.Label(
            form,
            text="Summarises every meeting since you last saw them, and rolls\n"
                 "unfinished items forward. Uses the catch-up model from ⚙ settings.",
            foreground="#555555",
        ).grid(row=3, column=0, columnspan=2, sticky="w")

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="Save", command=self.save).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

        self.person_combo.focus_set()
        self.transient(master)
        self.grab_set()

    def save(self):
        person = self.person_combo.get().strip()
        if not person:
            messagebox.showwarning(
                "Missing person", "Please enter who this recurring meeting is with.", parent=self
            )
            self.person_combo.focus_set()
            return
        weekdays = [i for i, var in enumerate(self.day_vars) if var.get()]
        if not weekdays:
            messagebox.showwarning(
                "Missing days", "Pick at least one day of the week.", parent=self
            )
            return
        RecurringMeetingManager.create(
            person, weekdays, catchup_enabled=self.catchup_var.get()
        )
        self.destroy()
        if self.on_saved:
            self.on_saved()
