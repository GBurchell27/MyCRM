"""The API key row, which asks for a key only when there isn't one already.

Three states, decided by where the key actually comes from:

- found in the environment (a .env file, or OPENAI_API_KEY set by hand) — say
  so and offer nothing to fill in, with a way through to the entry for anyone
  who wants to override it
- saved in settings — show it, and warn if it is shadowing an environment key,
  because a stale one here silently wins
- nowhere — the plain entry, which is the only case that needs asking
"""

import tkinter as tk
from tkinter import ttk

from ai_client import (
    ENV_VAR,
    FROM_ENVIRONMENT,
    SETTINGS_KEY,
    environment_key,
    resolve_key,
    stored_key,
)
from db import set_setting
from widgets.tooltip import attach

MASK_TAIL = 4

FOUND_HELP = (
    f"{ENV_VAR} is already set in your environment, so the app has a key to work "
    "with and there is nothing to enter here.\n\nA key typed into settings would "
    "take priority over it."
)

SHADOW_NOTE = (
    f"This key is used instead of the {ENV_VAR} in your environment. "
    "Clear the box to go back to that one."
)


def mask(key):
    """Show enough of a key to recognise it, never enough to leak it."""
    key = (key or "").strip()
    if len(key) <= MASK_TAIL:
        return "…"
    return "…" + key[-MASK_TAIL:]


class ApiKeyField(ttk.Frame):
    """Draws whichever of the three key states applies, and saves the entry."""

    def __init__(self, master):
        super().__init__(master)
        self.entry = None
        self.show_key = tk.BooleanVar(master=self, value=False)
        self.columnconfigure(0, weight=1)

        key, source = resolve_key()
        if source == FROM_ENVIRONMENT:
            self._build_found_note(key)
        else:
            self._build_entry(stored_key())

    @property
    def is_editing(self):
        """True once there is an entry on screen holding what should be saved."""
        return self.entry is not None

    # ------------------------------------------------------- environment found

    def _build_found_note(self, key):
        self.found = ttk.Frame(self)
        self.found.grid(row=0, column=0, sticky="ew")
        message = ttk.Label(
            self.found,
            text=f"✓ Found in your environment ({mask(key)}) — nothing to enter.",
            foreground="#1a7f37",
        )
        message.pack(side="left")
        attach(message, FOUND_HELP)
        override = ttk.Button(
            self.found, text="Use a different key", command=self._switch_to_entry, width=19
        )
        override.pack(side="left", padx=(10, 0))
        attach(
            override,
            "Enter a key here instead. It will be used in place of the one in your "
            "environment, for this app only.",
        )

    def _switch_to_entry(self):
        self.found.destroy()
        self._build_entry("")
        self.entry.focus_set()

    # -------------------------------------------------------------- plain entry

    def _build_entry(self, initial):
        holder = ttk.Frame(self)
        holder.grid(row=0, column=0, sticky="ew")
        holder.columnconfigure(0, weight=1)

        self.entry = ttk.Entry(holder, show="•")
        self.entry.grid(row=0, column=0, sticky="ew")
        if initial:
            self.entry.insert(0, initial)

        ttk.Checkbutton(
            holder, text="Show key", variable=self.show_key, command=self._toggle_show
        ).grid(row=1, column=0, sticky="w", pady=(2, 0))

        if initial and environment_key():
            ttk.Label(
                holder, text=SHADOW_NOTE, foreground="#8a6d00", wraplength=400
            ).grid(row=2, column=0, sticky="w", pady=(2, 0))

    def _toggle_show(self):
        self.entry.configure(show="" if self.show_key.get() else "•")

    # -------------------------------------------------------------------- save

    def save(self):
        """Only writes when an entry is on screen — the found state has nothing to say.

        Saving "" from an untouched found state would be harmless but misleading;
        leaving the row alone keeps "no key stored" meaning exactly that.
        """
        if self.entry is not None:
            set_setting(SETTINGS_KEY, self.entry.get().strip())
