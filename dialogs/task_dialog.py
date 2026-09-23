"""Task edit dialog."""

import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from widgets.dictation_button import DictationButton
from widgets.tag_field import TagField


class TaskDialog(tk.Toplevel):
    def __init__(self, master, on_save, task):
        super().__init__(master)
        self.title("Edit Task")
        self.on_save = on_save
        self.task = task
        self.geometry("420x380")
        self.resizable(True, True)

        form = ttk.Frame(self, padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(5, weight=1)

        ttk.Label(form, text="Title:").grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.title_var = tk.StringVar(value=task["title"] or "")
        title_entry = ttk.Entry(form, textvariable=self.title_var)
        title_entry.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        DictationButton(form, title_entry, single_line=True).grid(
            row=1, column=1, padx=(4, 0), pady=(0, 8)
        )

        ttk.Label(form, text="Project / tag:").grid(
            row=2, column=0, sticky="w", pady=(0, 4)
        )
        self.tag_field = TagField(form, value=task["tag"])
        self.tag_field.grid(row=3, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(form, text="Notes:").grid(row=4, column=0, sticky="w", pady=(0, 4))
        self.notes_box = ScrolledText(form, height=10, wrap="word")
        self.notes_box.grid(row=5, column=0, sticky="nsew")
        self.notes_box.insert("1.0", task["notes"] or "")
        DictationButton(form, self.notes_box).grid(
            row=5, column=1, sticky="n", padx=(4, 0)
        )

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="Save", command=self.save).pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

        title_entry.focus_set()
        title_entry.icursor("end")
        self.transient(master)
        self.grab_set()

    def save(self):
        title = self.title_var.get().strip()
        if not title:
            messagebox.showwarning("Missing title", "Please enter a title.")
            return
        notes = self.notes_box.get("1.0", "end").strip()
        self.on_save(
            {"title": title, "notes": notes, "tag": self.tag_field.tag()},
            self.task["id"],
        )
        self.destroy()
