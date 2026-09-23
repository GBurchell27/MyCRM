"""The project heading in the active task list — and its collapse control.

The whole heading is the button: the triangle, the project name and the count
all toggle, because a heading you have to hit a 12-pixel arrow on is a heading
you stop using. Collapsed groups keep their count on show so a rolled-up
project still tells you there is work waiting inside it.
"""

from tkinter import ttk

import help_text
from widgets.tooltip import attach_all


class TaskGroupHeading(ttk.Frame):
    """One clickable heading that rolls its group of tasks up or down."""

    UNTAGGED_TEXT = "Needs a tag"
    UNTAGGED_HINT = "— pick a tag on the row to file it, or tick it off"
    TAG_COLOUR = "#174EA6"
    UNTAGGED_COLOUR = "#B26A00"
    MUTED_COLOUR = "#888888"
    EXPANDED_ARROW = "▾"
    COLLAPSED_ARROW = "▸"

    def __init__(self, master, tag, task_count, collapsed, on_toggle):
        super().__init__(master)
        self._tag = tag
        self._on_toggle = on_toggle

        arrow = ttk.Label(
            self,
            text=self.COLLAPSED_ARROW if collapsed else self.EXPANDED_ARROW,
            foreground=self.MUTED_COLOUR,
            width=2,
        )
        arrow.pack(side="left")

        name = ttk.Label(
            self,
            text=tag or self.UNTAGGED_TEXT,
            font=("Segoe UI", 9, "bold"),
            foreground=self.TAG_COLOUR if tag else self.UNTAGGED_COLOUR,
        )
        name.pack(side="left")

        count = ttk.Label(self, text=f"({task_count})", foreground=self.MUTED_COLOUR)
        count.pack(side="left", padx=(4, 0))

        clickable = [self, arrow, name, count]
        if not tag and not collapsed:
            hint = ttk.Label(
                self, text=self.UNTAGGED_HINT, foreground=self.MUTED_COLOUR
            )
            hint.pack(side="left", padx=(6, 0))
            clickable.append(hint)

        # Every part of the heading behaves the same, tooltip included — a child
        # label under the pointer would otherwise swallow the frame's own hover.
        for widget in clickable:
            widget.configure(cursor="hand2")
            widget.bind("<Button-1>", self._toggle)
        attach_all([(widget, help_text.TASK_GROUP_TOGGLE) for widget in clickable])

    def _toggle(self, _event=None):
        self._on_toggle(self._tag)
