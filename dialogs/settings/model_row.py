"""The model + reasoning-effort controls for one AI job.

Storage keeps a job's model and its effort in a single "model:effort" string;
this splits that into the two controls people actually think in, and puts it
back together on save. The effort control greys itself out for models that have
no reasoning to spend — gpt-4o and the transcription models reject the
parameter, so offering it would only invite a confusing API error.
"""

import tkinter as tk
from tkinter import ttk

from config.ai_models import (
    CHAT,
    REASONING_EFFORT_CHOICES,
    combine_chat_model,
    resolve_chat_model,
    stored_value,
    supports_reasoning_effort,
)
from db import set_setting
from widgets.tooltip import attach

EFFORT_LABELS = [label for _, label in REASONING_EFFORT_CHOICES]

NOT_APPLICABLE = "—"

NO_EFFORT_HELP = (
    "This model takes no reasoning effort — only the gpt-5 family and the "
    "o-series do."
)


def effort_label(value):
    for candidate, label in REASONING_EFFORT_CHOICES:
        if candidate == value:
            return label
    return value or REASONING_EFFORT_CHOICES[0][1]


def effort_value(label):
    for value, candidate in REASONING_EFFORT_CHOICES:
        if candidate == label:
            return value
    return ""


class ModelRow:
    """One line of the AI models page: job name, model, reasoning effort."""

    def __init__(self, parent, setting, row):
        self.setting = setting
        model, effort = resolve_chat_model(stored_value(setting))

        label = ttk.Label(parent, text=setting["label"] + ":")
        label.grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
        attach(label, setting["help"])

        self.model_var = tk.StringVar(master=parent, value=model)
        model_combo = ttk.Combobox(
            parent, textvariable=self.model_var, values=setting["choices"], width=20
        )
        model_combo.grid(row=row, column=1, sticky="ew", pady=4)
        attach(model_combo, setting["help"])

        self.effort_var = tk.StringVar(master=parent, value=effort_label(effort))
        self.effort_combo = self._build_effort_control(parent, row)

        self.model_var.trace_add("write", lambda *_: self.sync_effort_state())
        self.sync_effort_state()

    @property
    def takes_effort(self):
        return self.setting["kind"] == CHAT

    def _build_effort_control(self, parent, row):
        if not self.takes_effort:
            placeholder = ttk.Label(parent, text=NOT_APPLICABLE, foreground="#888")
            placeholder.grid(row=row, column=2, sticky="w", padx=(10, 0), pady=4)
            attach(placeholder, NO_EFFORT_HELP)
            return None
        combo = ttk.Combobox(
            parent,
            textvariable=self.effort_var,
            values=EFFORT_LABELS,
            state="readonly",
            width=22,
        )
        combo.grid(row=row, column=2, sticky="ew", padx=(10, 0), pady=4)
        attach(combo, lambda: self._effort_help())
        return combo

    def _effort_help(self):
        if not supports_reasoning_effort(self.model_var.get()):
            return NO_EFFORT_HELP
        return (
            "How hard the model thinks before answering. Higher costs more and takes "
            "longer; leave it on the model default unless the job needs it."
        )

    def sync_effort_state(self):
        """Grey the effort control out for models that reject the parameter."""
        if self.effort_combo is None:
            return
        usable = supports_reasoning_effort(self.model_var.get())
        self.effort_combo.configure(state="readonly" if usable else "disabled")

    def save(self):
        value = combine_chat_model(self.model_var.get(), effort_value(self.effort_var.get()))
        set_setting(self.setting["key"], value or self.setting["default"])
