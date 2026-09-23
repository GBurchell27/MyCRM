"""Modal warning shown when a contact name closely matches an existing one."""

import tkinter as tk
from tkinter import ttk


class DuplicateWarningDialog(tk.Toplevel):
    """Blocks until the user says how to handle a likely-duplicate name.

    Sets `self.result` to "existing" (edit the matched contact instead),
    "new" (save as a separate contact anyway), or None (go back and keep editing).
    """

    def __init__(self, master, new_name, matches):
        super().__init__(master)
        self.title("Possible duplicate contact")
        self.resizable(False, False)
        self.result = None

        body = ttk.Frame(self, padding=14)
        body.pack(fill="both", expand=True)

        best = matches[0]
        ttk.Label(
            body,
            text=f'"{new_name}" looks like it might already be in your CRM.',
            font=("Segoe UI", 10, "bold"),
            wraplength=380,
            justify="left",
        ).pack(anchor="w")

        for row in matches[:3]:
            detail = ", ".join(v for v in (row["role"], row["team"], row["office"]) if v)
            text = f"• {row['name']}" + (f" — {detail}" if detail else "")
            ttk.Label(body, text=text, wraplength=380, justify="left").pack(
                anchor="w", pady=(8, 0)
            )

        btns = ttk.Frame(body)
        btns.pack(fill="x", pady=(16, 0))
        ttk.Button(btns, text="Cancel", command=self._cancel).pack(side="left")
        ttk.Button(btns, text="Save as new contact", command=self._save_new).pack(
            side="right"
        )
        ttk.Button(
            btns, text=f"Edit {best['name']} instead", command=self._use_existing
        ).pack(side="right", padx=(0, 8))

        self.protocol("WM_DELETE_WINDOW", self._cancel)
        self.transient(master)
        self.grab_set()

    def _use_existing(self):
        self.result = "existing"
        self.destroy()

    def _save_new(self):
        self.result = "new"
        self.destroy()

    def _cancel(self):
        self.result = None
        self.destroy()
