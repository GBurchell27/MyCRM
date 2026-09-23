"""The AI page of the settings window: the API key, and a model per job.

Every AI job in the app is listed here with its own model and reasoning effort,
so the cheap model can run the routine work and a stronger one can be reserved
for the jobs that earn it.
"""

from tkinter import ttk

from ai_client import ENV_VAR
from config.ai_models import MODEL_SETTINGS
from dialogs.settings.api_key_field import ApiKeyField
from dialogs.settings.model_row import ModelRow

FOOTER = (
    "Any OpenAI model name can be typed in, not just the suggestions. Reasoning "
    f"effort applies to the gpt-5 family and the o-series only.\nA key set as "
    f"{ENV_VAR} in your environment or .env file is used as-is; one entered here "
    "is stored locally in crm_data.db and takes priority over it."
)


class AIModelsPage(ttk.Frame):
    """API key plus the model and reasoning effort behind each AI feature."""

    title = "AI models"

    def __init__(self, master):
        super().__init__(master, padding=16)

        ttk.Label(self, text="OpenAI API key:").grid(row=0, column=0, sticky="nw", pady=4)
        self.api_key = ApiKeyField(self)
        self.api_key.grid(row=0, column=1, columnspan=2, sticky="ew", pady=4)

        ttk.Separator(self, orient="horizontal").grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(10, 8)
        )
        ttk.Label(self, text="Model", font=("Segoe UI", 9, "bold")).grid(
            row=3, column=1, sticky="w"
        )
        ttk.Label(self, text="Reasoning effort", font=("Segoe UI", 9, "bold")).grid(
            row=3, column=2, sticky="w", padx=(10, 0)
        )

        self.rows = [
            ModelRow(self, setting, row)
            for row, setting in enumerate(MODEL_SETTINGS, start=4)
        ]

        ttk.Label(self, text=FOOTER, wraplength=520, foreground="#555").grid(
            row=4 + len(self.rows), column=0, columnspan=3, sticky="w", pady=(14, 0)
        )
        self.columnconfigure(1, weight=1)
        self.columnconfigure(2, weight=1)

    def save(self):
        self.api_key.save()
        for row in self.rows:
            row.save()
