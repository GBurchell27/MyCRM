"""One editable control per setting type.

The settings pages don't know what a checkbox or a spinbox is: they hand a
Setting to `build_field` and get back something that can draw itself into a grid
row and write itself back. Supporting a new type of preference means adding a
field class here, not touching any page.
"""

import tkinter as tk
from tkinter import ttk

from widgets.tooltip import attach

LABEL_PAD = (0, 10)
ROW_PAD = (0, 8)


class SettingField:
    """Base: owns the variable behind one setting's control."""

    def __init__(self, setting, var):
        self.setting = setting
        self.var = var

    def value(self):
        return self.var.get()

    def save(self):
        self.setting.save(self.value())


class BoolField(SettingField):
    """A checkbox that carries its own label."""

    def __init__(self, parent, setting, row):
        super().__init__(setting, tk.BooleanVar(master=parent, value=setting.get()))
        check = ttk.Checkbutton(parent, text=setting.label, variable=self.var)
        check.grid(row=row, column=0, columnspan=3, sticky="w", pady=ROW_PAD)
        _explain(check, setting)


class IntField(SettingField):
    """A number box with its unit spelled out beside it."""

    def __init__(self, parent, setting, row):
        super().__init__(setting, tk.StringVar(master=parent, value=str(setting.get())))
        label = ttk.Label(parent, text=setting.label + ":")
        label.grid(row=row, column=0, sticky="w", padx=LABEL_PAD, pady=ROW_PAD)
        spin = ttk.Spinbox(
            parent,
            from_=setting.minimum,
            to=setting.maximum,
            increment=1,
            width=8,
            textvariable=self.var,
        )
        spin.grid(row=row, column=1, sticky="w", pady=ROW_PAD)
        if setting.unit:
            ttk.Label(parent, text=setting.unit).grid(
                row=row, column=2, sticky="w", padx=(6, 0), pady=ROW_PAD
            )
        _explain(label, setting)
        _explain(spin, setting)

    def value(self):
        """Anything unreadable falls back to what is stored, never raises."""
        try:
            return self.setting.clamp(int(float(self.var.get())))
        except (TypeError, ValueError):
            return self.setting.get()


class ChoiceField(SettingField):
    """A read-only dropdown showing labels, storing values."""

    def __init__(self, parent, setting, row):
        super().__init__(
            setting, tk.StringVar(master=parent, value=setting.label_for(setting.get()))
        )
        label = ttk.Label(parent, text=setting.label + ":")
        label.grid(row=row, column=0, sticky="w", padx=LABEL_PAD, pady=ROW_PAD)
        combo = ttk.Combobox(
            parent,
            state="readonly",
            values=setting.labels,
            textvariable=self.var,
            width=24,
        )
        combo.grid(row=row, column=1, columnspan=2, sticky="w", pady=ROW_PAD)
        _explain(label, setting)
        _explain(combo, setting)

    def value(self):
        return self.setting.value_for(self.var.get())


FIELD_TYPES = {
    "bool": BoolField,
    "int": IntField,
    "choice": ChoiceField,
}


def build_field(parent, setting, row):
    """Draw `setting` into `parent` at `row`. Raises on a type with no field class."""
    try:
        field_class = FIELD_TYPES[setting.kind]
    except KeyError:
        raise ValueError(f"No settings control for a {setting.kind!r} setting") from None
    return field_class(parent, setting, row)


def _explain(widget, setting):
    if setting.help_text:
        attach(widget, setting.help_text)
