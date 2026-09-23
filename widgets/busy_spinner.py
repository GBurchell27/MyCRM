"""Animated busy spinner for long-running AI / capture work."""

import tkinter as tk


class BusySpinner(tk.Frame):
    """Inline spinner with a status label; pack when busy, hide when idle."""

    _BG = "#E3F2FD"
    _FG = "#0D47A1"
    _FRAMES = ("⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏")
    _TICK_MS = 90

    def __init__(self, master, **kwargs):
        super().__init__(master, bg=self._BG, padx=10, pady=8, **kwargs)
        self._active = False
        self._frame_i = 0
        self._job = None

        self._glyph = tk.Label(
            self,
            text=self._FRAMES[0],
            font=("Segoe UI", 18),
            fg=self._FG,
            bg=self._BG,
            width=2,
        )
        self._glyph.pack(side="left")
        self._label = tk.Label(
            self,
            text="",
            font=("Segoe UI", 11, "bold"),
            fg=self._FG,
            bg=self._BG,
            anchor="w",
        )
        self._label.pack(side="left", fill="x", expand=True, padx=(6, 0))
        self.pack_forget()

    @property
    def active(self):
        return self._active

    def start(self, message):
        self._label.configure(text=message)
        if self._active:
            return
        self._active = True
        self._frame_i = 0
        self.pack(fill="x", pady=(8, 0))
        self._tick()

    def update_message(self, message):
        self._label.configure(text=message)

    def stop(self):
        self._active = False
        if self._job is not None:
            self.after_cancel(self._job)
            self._job = None
        self.pack_forget()

    def _tick(self):
        if not self._active:
            return
        self._glyph.configure(text=self._FRAMES[self._frame_i % len(self._FRAMES)])
        self._frame_i += 1
        self._job = self.after(self._TICK_MS, self._tick)
