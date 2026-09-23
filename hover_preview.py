"""Hover preview popup for Treeview rows.

Shows a small floating window with the full details of the row under the
mouse, so rows can be scanned without opening each one. Clicking a row
hides the preview and leaves the normal open/edit behaviour untouched.
"""

import tkinter as tk

from config.app_settings import HOVER_PREVIEWS

BG = "#ffffe0"


class TreeHoverPreview:
    SHOW_DELAY_MS = 350
    MAX_FIELD_CHARS = 600
    WRAP_LENGTH = 420

    def __init__(self, tree, provider):
        """provider(iid) returns a list of (label, value) pairs, or None."""
        self.tree = tree
        self.provider = provider
        self.tip = None
        self.current_iid = None
        self._after_id = None
        tree.bind("<Motion>", self._on_motion, add="+")
        tree.bind("<Leave>", lambda e: self.hide(), add="+")
        tree.bind("<ButtonPress>", lambda e: self.hide(), add="+")
        tree.bind("<MouseWheel>", lambda e: self.hide(), add="+")
        tree.bind("<Destroy>", lambda e: self.hide(), add="+")

    def _on_motion(self, event):
        iid = self.tree.identify_row(event.y)
        if not iid:
            self.hide()
            return
        if iid == self.current_iid and self.tip is not None:
            return
        self._cancel_pending()
        self.current_iid = iid
        if self.tip is not None:
            # Already showing for another row: switch immediately.
            self._show(iid, event.x_root, event.y_root)
        else:
            self._after_id = self.tree.after(
                self.SHOW_DELAY_MS,
                lambda: self._show(iid, event.x_root, event.y_root),
            )

    def _show(self, iid, x_root, y_root):
        self._after_id = None
        # Read here rather than on <Motion>: this runs at most once per row, so
        # turning previews off takes hold immediately without a query per pixel.
        if not HOVER_PREVIEWS.get():
            self.hide()
            return
        fields = self.provider(iid)
        if not fields:
            self.hide()
            return
        self._destroy_tip()

        tip = tk.Toplevel(self.tree)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(tip, background=BG, borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)
        for label, value in fields:
            value = str(value or "").strip()
            if not value:
                continue
            if len(value) > self.MAX_FIELD_CHARS:
                value = value[: self.MAX_FIELD_CHARS - 1] + "…"
            tk.Label(
                frame, text=label, background=BG, anchor="w",
                font=("Segoe UI", 9, "bold"),
            ).pack(anchor="w", padx=8, pady=(6, 0))
            tk.Label(
                frame, text=value, background=BG, anchor="w", justify="left",
                wraplength=self.WRAP_LENGTH, font=("Segoe UI", 9),
            ).pack(anchor="w", padx=8)
        tk.Frame(frame, background=BG, height=6).pack()

        tip.update_idletasks()
        w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
        sw, sh = tip.winfo_screenwidth(), tip.winfo_screenheight()
        x = min(x_root + 16, max(0, sw - w - 8))
        y = y_root + 12
        if y + h > sh - 8:
            y = max(8, y_root - h - 12)
        tip.geometry(f"+{x}+{y}")
        self.tip = tip

    def hide(self):
        self._cancel_pending()
        self._destroy_tip()
        self.current_iid = None

    def _cancel_pending(self):
        if self._after_id is not None:
            try:
                self.tree.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _destroy_tip(self):
        if self.tip is not None:
            try:
                self.tip.destroy()
            except tk.TclError:
                pass
            self.tip = None
