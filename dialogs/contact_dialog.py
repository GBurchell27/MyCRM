"""Contact add/edit dialog."""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from datetime import date

from dialogs.duplicate_warning_dialog import DuplicateWarningDialog
from duplicate_contacts import find_possible_duplicates
from offices import OFFICES, normalise_office
from people_memory import list_known_people
from widgets.dictation_button import DictationButton


class ContactDialog(tk.Toplevel):
    FIELDS = ["met_on", "name", "team", "office", "role", "manager", "how_we_met"]
    LABELS = [
        "Met On (date)", "Name", "Team", "Office", "Role", "Manager", "How We Met",
    ]
    DICTATION_FIELDS = ("team", "role", "how_we_met")

    def __init__(self, master, on_save, contact=None, initial=None, intro=""):
        """`initial` pre-fills a new contact (field -> value, plus "notes")."""
        super().__init__(master)
        self.title("Edit Contact" if contact else "Add Contact")
        self.on_save = on_save
        self.contact = contact
        self.geometry("480x600" if intro else "480x560")
        self.resizable(True, True)
        self.entries = {}
        known = list_known_people()

        if intro:
            banner = ttk.Frame(self, padding=(12, 12, 12, 0))
            banner.pack(fill="x")
            ttk.Label(banner, text=intro, wraplength=440, justify="left").pack(
                anchor="w"
            )

        form = ttk.Frame(self, padding=12)
        form.pack(fill="both", expand=True)

        for i, (field, label) in enumerate(zip(self.FIELDS, self.LABELS)):
            ttk.Label(form, text=label + ":").grid(row=i, column=0, sticky="w", pady=4)
            if field in ("name", "manager"):
                e = ttk.Combobox(form, width=38, values=known)
            elif field == "office":
                # Editable on purpose: new offices work before this list grows.
                e = ttk.Combobox(form, width=38, values=OFFICES)
            else:
                e = ttk.Entry(form, width=40)
            e.grid(row=i, column=1, sticky="ew", pady=4)
            if field in self.DICTATION_FIELDS:
                DictationButton(form, e, single_line=True).grid(
                    row=i, column=2, padx=(4, 0)
                )
            self.entries[field] = e
        form.columnconfigure(1, weight=1)

        ttk.Label(form, text="Notes:").grid(row=len(self.FIELDS), column=0, sticky="nw", pady=4)
        self.notes_box = ScrolledText(form, width=40, height=14, wrap="word")
        self.notes_box.grid(row=len(self.FIELDS), column=1, sticky="nsew", pady=4)
        DictationButton(form, self.notes_box).grid(
            row=len(self.FIELDS), column=2, sticky="n", pady=4, padx=(4, 0)
        )
        form.rowconfigure(len(self.FIELDS), weight=1)

        if contact:
            for field in self.FIELDS:
                self.entries[field].insert(0, contact[field] or "")
            self.notes_box.insert("1.0", contact["notes"] or "")
        else:
            prefill = dict(initial or {})
            if not prefill.get("met_on"):
                prefill["met_on"] = date.today().isoformat()
            for field in self.FIELDS:
                self.entries[field].insert(0, prefill.get(field) or "")
            self.notes_box.insert("1.0", prefill.get("notes") or "")

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="Save", command=self.save).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

        self.entries["name"].focus_set()
        self.transient(master)
        self.grab_set()

    def save(self):
        data = {f: self.entries[f].get().strip() for f in self.FIELDS}
        data["office"] = normalise_office(data["office"])
        if not data["name"]:
            messagebox.showwarning("Missing name", "Please enter a name.")
            return
        data["notes"] = self.notes_box.get("1.0", "end").strip()

        exclude_id = self.contact["id"] if self.contact else None
        matches = find_possible_duplicates(data["name"], exclude_id=exclude_id)
        if matches:
            warning = DuplicateWarningDialog(self, data["name"], matches)
            self.wait_window(warning)
            if warning.result is None:
                return
            if warning.result == "existing":
                master, on_save = self.master, self.on_save
                self.destroy()
                ContactDialog(master, on_save=on_save, contact=matches[0])
                return

        self.on_save(data, self.contact["id"] if self.contact else None)
        self.destroy()
