"""Hover tooltips for individual controls.

The row previews in hover_preview.py explain *data*; these explain *controls* —
what a button will do before you press it. Same yellow popup so the two feel
like one idea.
"""

import tkinter as tk

BG = "#ffffe0"
SHOW_DELAY_MS = 450
WRAP_LENGTH = 260


class Tooltip:
    """A delayed hover label for one widget."""

    def __init__(self, widget, text, wraplength=WRAP_LENGTH, delay=SHOW_DELAY_MS):
        self.widget = widget
        self.text = text
        self.wraplength = wraplength
        self.delay = delay
        self._tip = None
        self._after_id = None
        widget.bind("<Enter>", self._on_enter, add="+")
        widget.bind("<Leave>", self._on_leave, add="+")
        widget.bind("<ButtonPress>", self._on_leave, add="+")
        widget.bind("<Destroy>", self._on_leave, add="+")

    def _resolve_text(self):
        """Text may be a callable, so a tooltip can describe current state."""
        value = self.text() if callable(self.text) else self.text
        return str(value or "").strip()

    def _on_enter(self, event):
        self._cancel()
        x_root, y_root = event.x_root, event.y_root
        self._after_id = self.widget.after(
            self.delay, lambda: self._show(x_root, y_root)
        )

    def _on_leave(self, _event=None):
        self._cancel()
        self._destroy()

    def _cancel(self):
        if self._after_id is not None:
            try:
                self.widget.after_cancel(self._after_id)
            except tk.TclError:
                pass
            self._after_id = None

    def _show(self, x_root, y_root):
        self._after_id = None
        text = self._resolve_text()
        if not text or not self.widget.winfo_exists():
            return
        self._destroy()
        tip = tk.Toplevel(self.widget)
        tip.wm_overrideredirect(True)
        try:
            tip.attributes("-topmost", True)
        except tk.TclError:
            pass
        frame = tk.Frame(tip, background=BG, borderwidth=1, relief="solid")
        frame.pack(fill="both", expand=True)
        tk.Label(
            frame, text=text, background=BG, anchor="w", justify="left",
            wraplength=self.wraplength, font=("Segoe UI", 9),
        ).pack(padx=8, pady=5)

        tip.update_idletasks()
        w, h = tip.winfo_reqwidth(), tip.winfo_reqheight()
        sw, sh = tip.winfo_screenwidth(), tip.winfo_screenheight()
        x = min(x_root + 14, max(0, sw - w - 8))
        y = y_root + 20
        if y + h > sh - 8:
            y = max(8, y_root - h - 14)
        tip.geometry(f"+{x}+{y}")
        self._tip = tip

    def _destroy(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None


def attach(widget, text, **kwargs):
    """Give `widget` a hover tooltip. Returns it, so callers can ignore it."""
    return Tooltip(widget, text, **kwargs)


def attach_all(pairs):
    """attach() over an iterable of (widget, text)."""
    return [attach(widget, text) for widget, text in pairs if widget is not None]
