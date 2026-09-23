"""A settings page built straight from a section of the registry.

Every non-model page is this one class: it reads the section it was handed and
draws a field per setting. New preferences appear here by being added to
config/app_settings.py.
"""

from tkinter import ttk

from dialogs.settings.setting_fields import build_field


class PreferencesPage(ttk.Frame):
    """One SettingsSection, rendered as rows of controls."""

    def __init__(self, master, section):
        super().__init__(master, padding=16)
        self.section = section

        if section.blurb:
            ttk.Label(self, text=section.blurb, wraplength=520, foreground="#555").grid(
                row=0, column=0, columnspan=3, sticky="w", pady=(0, 12)
            )
        self.fields = [
            build_field(self, setting, row)
            for row, setting in enumerate(section, start=1)
        ]
        self.columnconfigure(2, weight=1)

    @property
    def title(self):
        return self.section.title

    def save(self):
        for field in self.fields:
            field.save()
