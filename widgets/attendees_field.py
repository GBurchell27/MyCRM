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
MAX_SUGGESTIONS_SHOWN = 6


def matching_people(known_people, typed):
    """Known people with a first name or surname starting with what was typed."""
    prefix = typed.strip().casefold()
    if not prefix:
        return []
    return [
        name for name in known_people
        if name.casefold().startswith(prefix)
        or any(word.startswith(prefix) for word in name.casefold().split())
    ]


class AttendeesField(ttk.Frame):
    """A combobox of known people plus the chips for everyone added so far."""

    def __init__(self, master, known_people=(), wrap_px=430, on_change=None, width=26):
        super().__init__(master)
        self._names = []
        self._wrap_px = wrap_px
        self._on_change = on_change
        self._known_people = list(known_people)

        entry_row = ttk.Frame(self)
        entry_row.pack(fill="x")
        self.combo = ttk.Combobox(entry_row, width=width, values=list(known_people))
        self.combo.pack(side="left")
        self.combo.bind("<Return>", self._add_typed)
        self.combo.bind("<<ComboboxSelected>>", self._add_typed)
        self.combo.bind("<KeyRelease>", self._refresh_suggestions)
        self.combo.bind("<Down>", lambda _e: self._move_highlight(1))
        self.combo.bind("<Up>", lambda _e: self._move_highlight(-1))
        self.combo.bind("<Escape>", self._hide_suggestions)
        add_btn = ttk.Button(entry_row, text="+ Add", width=7, command=self._add_typed)
        add_btn.pack(side="left", padx=(4, 0))
        self.add_button = add_btn

        # Names matching what is typed, so nobody has to scroll the whole list.
        self._suggestions = tk.Listbox(self, height=1, activestyle="none", exportselection=False)
        self._suggestions.bind("<ButtonRelease-1>", self._add_highlighted)

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
        self._known_people = list(people)
        self.combo.configure(values=self._known_people)

    def focus_set(self):
        self.combo.focus_set()

    # --------------------------------------------------------------- internals

    def _add_typed(self, _event=None):
        highlighted = self._suggestions.curselection()
        typed = self._suggestions.get(highlighted[0]) if highlighted else self.combo.get().strip()
        self._hide_suggestions()
        if not typed:
            return "break"
        self.add(typed)
        self.combo.set("")
        self.combo.focus_set()
        return "break"

    def _add_highlighted(self, _event=None):
        if self._suggestions.curselection():
            self._add_typed()

    def _refresh_suggestions(self, event):
        if event.keysym in ("Down", "Up", "Return", "Escape", "Tab"):
            return
        matches = matching_people(self._known_people, self.combo.get())
        self._suggestions.delete(0, "end")
        if not matches:
            self._suggestions.pack_forget()
            return
        self._suggestions.insert("end", *matches)
        self._suggestions.configure(height=min(len(matches), MAX_SUGGESTIONS_SHOWN))
        self._suggestions.pack(fill="x", pady=(2, 0), before=self._chips if self._names else None)

    def _move_highlight(self, step):
        """Arrow keys walk the suggestions while the cursor stays in the box."""
        count = self._suggestions.size()
        if not self._suggestions.winfo_ismapped() or not count:
            return None  # no suggestions: let the combobox open its full list
        current = self._suggestions.curselection()
        index = max(0, min(count - 1, current[0] + step if current else 0))
        self._suggestions.selection_clear(0, "end")
        self._suggestions.selection_set(index)
        self._suggestions.see(index)
        return "break"

    def _hide_suggestions(self, _event=None):
        self._suggestions.selection_clear(0, "end")
        self._suggestions.pack_forget()

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
