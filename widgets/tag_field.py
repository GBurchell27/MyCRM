"""Pick or type the project a task belongs to.

A dumb widget: it offers the tags already in use and accepts anything typed.
Which tasks a tag then groups is the Tasks tab's business.
"""

import tkinter as tk
from tkinter import ttk

from task_manager import TaskManager, clean_tag


class TagField(ttk.Combobox):
    """Free-text combobox pre-filled with every tag already on a task."""

    def __init__(self, master, value="", **kwargs):
        self.var = tk.StringVar(value=clean_tag(value))
        super().__init__(
            master, textvariable=self.var, values=TaskManager.list_tags(), **kwargs
        )

    def tag(self):
        """What the user chose or typed, tidied."""
        return clean_tag(self.var.get())

    def set_tag(self, value):
        self.var.set(clean_tag(value))

    def refresh_choices(self):
        """Re-read the known tags — call after a task is saved with a new one."""
        self.configure(values=TaskManager.list_tags())
