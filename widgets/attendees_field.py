"""Who was in the meeting: pick or type a name, add it, see it as a chip.

One name at a time, because that is how a meeting fills up — someone else walks
in and joins. Each name added shows as a chip you can remove, so a group meeting
is as easy to correct as it is to build, and there is no separator to remember.

A dumb widget: it holds names and reports them. What they mean is the meeting
dialog's business.
"""

import tkinter as tk
from tkinter import ttk

import attendees

CHIP_BG = "#E8F0FE"
CHIP_FG = "#174EA6"
# Chips are laid out by hand, so their width has to be guessed before they exist.
PIXELS_PER_CHAR = 7
CHIP_PADDING_PX = 34


class AttendeesField(ttk.Frame):
    """A combobox of known people plus the chips for everyone added so far."""

    def __init__(self, master, known_people=(), wrap_px=430, on_change=None, width=26):
        super().__init__(master)
        self._names = []
        self._wrap_px = wrap_px
        self._on_change = on_change

        entry_row = ttk.Frame(self)
        entry_row.pack(fill="x")
        self.combo = ttk.Combobox(entry_row, width=width, values=list(known_people))
        self.combo.pack(side="left")
        self.combo.bind("<Return>", self._add_typed)
        self.combo.bind("<<ComboboxSelected>>", self._add_typed)
        add_btn = ttk.Button(entry_row, text="+ Add", width=7, command=self._add_typed)
        add_btn.pack(side="left", padx=(4, 0))
        self.add_button = add_btn

        self._chips = ttk.Frame(self)

    # ---------------------------------------------------------------- reading

    def get_names(self):
        """Everyone in the meeting, in the order they were added."""
        return list(self._names)

    def get(self):
        """The canonical value for the meetings row's person column."""
        return attendees.join(self._names)

    def describe(self):
        return attendees.describe(self._names)

    def count(self):
        return len(self._names)

    # ---------------------------------------------------------------- writing

    def set(self, value):
        """Replace everyone with the names in `value` (a person column or list)."""
        self._names = attendees.parse(value)
        self._redraw()

    def add(self, name):
        """Add one name, ignoring blanks and anyone already there."""
        merged = attendees.parse(self._names + attendees.parse(name))
        if merged == self._names:
            return False
        self._names = merged
        self._redraw()
        return True

    def remove(self, name):
        wanted = str(name).casefold()
        self._names = [n for n in self._names if n.casefold() != wanted]
        self._redraw()

    def set_known_people(self, people):
        self.combo.configure(values=list(people))

    def focus_set(self):
        self.combo.focus_set()

    # --------------------------------------------------------------- internals

    def _add_typed(self, _event=None):
        typed = self.combo.get().strip()
        if not typed:
            return "break"
        self.add(typed)
        self.combo.set("")
        self.combo.focus_set()
        return "break"

    def _redraw(self):
        for child in self._chips.winfo_children():
            child.destroy()
        if not self._names:
            self._chips.pack_forget()
        else:
            self._chips.pack(fill="x", pady=(4, 0))
            self._lay_out_chips()
        if self._on_change:
            self._on_change(self.get_names())

    def _lay_out_chips(self):
        """Pack chips left to right, starting a new line before they overflow."""
        line, used = self._new_chip_line(), 0
        for name in self._names:
            width = len(name) * PIXELS_PER_CHAR + CHIP_PADDING_PX
            if used and used + width > self._wrap_px:
                line, used = self._new_chip_line(), 0
            self._build_chip(line, name).pack(side="left", padx=(0, 4), pady=1)
            used += width

    def _new_chip_line(self):
        line = ttk.Frame(self._chips)
        line.pack(fill="x")
        return line

    def _build_chip(self, parent, name):
        chip = tk.Frame(parent, background=CHIP_BG, padx=6, pady=1)
        tk.Label(
            chip, text=name, background=CHIP_BG, foreground=CHIP_FG,
            font=("Segoe UI", 8),
        ).pack(side="left")
        close = tk.Label(
            chip, text="x", background=CHIP_BG, foreground=CHIP_FG,
            font=("Segoe UI", 8, "bold"), cursor="hand2", padx=4,
        )
        close.pack(side="left")
        close.bind("<Button-1>", lambda _e, person=name: self.remove(person))
        return chip
