"""The cog that sits at the right-hand end of the main tab strip.

A ttk.Notebook has no notion of a control in its tab row, so the cog is placed
over one. Its vertical position is measured from the notebook rather than
guessed: the first page's top edge is exactly where the tab strip ends, so the
cog stays centred if the tab font, padding or display scaling ever changes.
"""

from tkinter import ttk

from widgets.tooltip import attach

GLYPH = "⚙"
IDLE_FG = "#4a4a4a"
HOVER_FG = "#0b6ab8"

# Used only until the notebook has been laid out and can be measured.
ASSUMED_STRIP_HEIGHT = 38


class SettingsCog(ttk.Label):
    """A clickable cog, positioned over a notebook's tab strip."""

    def __init__(self, master, command, help_text="", **kwargs):
        kwargs.setdefault("text", GLYPH)
        kwargs.setdefault("font", ("Segoe UI Symbol", 15))
        kwargs.setdefault("foreground", IDLE_FG)
        kwargs.setdefault("cursor", "hand2")
        super().__init__(master, **kwargs)
        self.command = command
        self._notebook = None
        self._page = None
        self._padx = 12
        self.bind("<Button-1>", self._on_click)
        self.bind("<Enter>", lambda _e: self.configure(foreground=HOVER_FG))
        self.bind("<Leave>", lambda _e: self.configure(foreground=IDLE_FG))
        if help_text:
            attach(self, help_text)

    def attach_to(self, notebook, page, padx=12):
        """Place the cog at the right of `notebook`'s tab strip.

        `page` is any tab body in that notebook — its top edge is the measurement
        the vertical centring is based on.
        """
        self._notebook = notebook
        self._page = page
        self._padx = padx
        self._reposition()
        notebook.after_idle(self._reposition)
        notebook.bind("<Configure>", lambda _e: self._reposition(), add="+")

    def _reposition(self):
        if self._notebook is None:
            return
        strip_height = self._page.winfo_y() or ASSUMED_STRIP_HEIGHT
        y = max(0, (strip_height - self.winfo_reqheight()) // 2)
        self.place(in_=self._notebook, relx=1.0, x=-self._padx, y=y, anchor="ne")

    def _on_click(self, _event):
        self.command()
        return "break"
