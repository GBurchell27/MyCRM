"""The one window where every preference is edited.

A shell around a notebook of pages: the AI page, which needs controls of its
own, plus a generated page per section of the settings registry. The shell only
knows that a page has a `title` and a `save()`, so a new page is one line here.
"""

import tkinter as tk
from tkinter import ttk, messagebox

from config.app_settings import SETTING_SECTIONS
from dialogs.settings.ai_models_page import AIModelsPage
from dialogs.settings.preferences_page import PreferencesPage

# The main window styles TNotebook.Tab for its own oversized nav; these pages
# need their own style or they inherit it.
NOTEBOOK_STYLE = "Settings.TNotebook"


class SettingsDialog(tk.Toplevel):
    """Settings, one page per area."""

    def __init__(self, master):
        super().__init__(master)
        self.title("Settings")
        self.geometry("620x500")
        self.minsize(560, 420)
        self._configure_tab_style()

        notebook = ttk.Notebook(self, style=NOTEBOOK_STYLE)
        notebook.pack(fill="both", expand=True, padx=12, pady=(12, 0))

        self.pages = [AIModelsPage(notebook)]
        self.pages.extend(PreferencesPage(notebook, section) for section in SETTING_SECTIONS)
        for page in self.pages:
            notebook.add(page, text=page.title)

        buttons = ttk.Frame(self, padding=12)
        buttons.pack(fill="x")
        save = ttk.Button(buttons, text="Save", command=self.save, default="active")
        save.pack(side="right", padx=(6, 0))
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right")

        self.bind("<Escape>", lambda _event: self.destroy())
        self.transient(master)
        self.grab_set()
        save.focus_set()

    def _configure_tab_style(self):
        style = ttk.Style(self)
        style.configure(NOTEBOOK_STYLE, tabmargins=(2, 4, 2, 0))
        style.configure(
            NOTEBOOK_STYLE + ".Tab", font=("Segoe UI", 9), padding=(14, 6)
        )

    def save(self):
        for page in self.pages:
            page.save()
        messagebox.showinfo(
            "Saved", "Settings saved locally in crm_data.db.", parent=self
        )
        self.destroy()
