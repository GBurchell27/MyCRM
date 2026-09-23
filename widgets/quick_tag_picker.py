"""File an untagged task under a project without leaving the list.

Sits on the row of a task that arrived without a tag — typically sent over from
a meeting note. Pick a project from the dropdown or type a new one and the task
is filed on the spot: no dialog, no Save. The repeat button reuses whatever tag
was applied last, which turns a run of untagged tasks into one click each.
"""

import tkinter as tk
from tkinter import ttk

from helpers import truncate
from task_manager import clean_tag


class QuickTagPicker(ttk.Frame):
    """Dropdown + repeat button that assign a tag the moment they are used."""

    PROMPT = "＋ tag…"
    REPEAT_LABEL_CHARS = 12

    def __init__(self, master, choices, on_assign, repeat_tag=""):
        super().__init__(master)
        self.on_assign = on_assign

        self.tag_var = tk.StringVar(value=self.PROMPT)
        self.combo = ttk.Combobox(
            self,
            textvariable=self.tag_var,
            values=list(choices),
            width=13,
        )
        self.combo.pack(side="left")
        self.combo.bind("<<ComboboxSelected>>", self._assign_chosen)
        self.combo.bind("<Return>", self._assign_chosen)
        self.combo.bind("<FocusIn>", self._clear_prompt)

        self.repeat_button = None
        if repeat_tag:
            self.repeat_button = ttk.Button(
                self,
                text=f"⤵ {truncate(repeat_tag, self.REPEAT_LABEL_CHARS)}",
                command=lambda: self.on_assign(repeat_tag),
            )
            self.repeat_button.pack(side="left", padx=(4, 0))

    def _clear_prompt(self, _event=None):
        """The prompt is a label, not a value — it goes as soon as you type."""
        if self.tag_var.get() == self.PROMPT:
            self.tag_var.set("")

    def _assign_chosen(self, _event=None):
        chosen = clean_tag(self.tag_var.get())
        if not chosen or chosen == self.PROMPT:
            return
        self.on_assign(chosen)
