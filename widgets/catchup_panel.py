"""Shows what has happened since you last saw this person.

A dumb view: it renders whatever it is handed and reports button presses back
through callbacks. Deciding what to render, and when, is the catch-up section's
job.
"""

import tkinter as tk
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText

import help_text
from widgets.tooltip import attach, attach_all

PLACEHOLDER = "Add someone and pick a date to see what has happened since you last met."


class CatchupPanel(ttk.LabelFrame):
    def __init__(self, master, on_refresh=None, on_pull_items=None, on_generate=None,
                 on_copy=None, on_make_recurring=None, **kwargs):
        kwargs.setdefault("text", "Since we last spoke")
        kwargs.setdefault("padding", 8)
        super().__init__(master, **kwargs)
        self.on_generate = on_generate

        self.headline_var = tk.StringVar(value=PLACEHOLDER)
        headline = ttk.Label(self, textvariable=self.headline_var, wraplength=320,
                             font=("Segoe UI", 9, "bold"))
        headline.pack(anchor="w")

        self.notice_var = tk.StringVar(value="")
        self.notice_label = tk.Label(self, textvariable=self.notice_var, wraplength=320,
                                     fg="#B36B00", justify="left", anchor="w")

        self.suggestion = tk.Frame(self, background="#E8F0FE", padx=6, pady=5)
        self.suggestion_var = tk.StringVar(value="")
        tk.Label(
            self.suggestion, textvariable=self.suggestion_var, background="#E8F0FE",
            wraplength=210, justify="left", anchor="w", font=("Segoe UI", 8),
        ).pack(side="left", fill="x", expand=True)
        self.make_recurring_btn = ttk.Button(
            self.suggestion, text="Set up", width=8, command=on_make_recurring
        )
        self.make_recurring_btn.pack(side="right", padx=(6, 0))

        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, pady=(6, 0))
        self.brief_box = self._add_tab("Brief", help_text.CATCHUP_BRIEF_TAB)
        self.pack_box = self._add_tab("What happened", help_text.CATCHUP_PACK_TAB)

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(6, 0))
        self.generate_btn = ttk.Button(actions, text="Generate brief", command=self._generate)
        self.generate_btn.pack(side="left")
        copy_btn = ttk.Button(actions, text="Copy", command=on_copy)
        copy_btn.pack(side="left", padx=4)
        refresh_btn = ttk.Button(actions, text="↻", width=3, command=on_refresh)
        refresh_btn.pack(side="left")
        self.pull_btn = ttk.Button(actions, text="Pull in open items", command=on_pull_items)
        self.pull_btn.pack(side="right")

        attach_all([
            (headline, help_text.CATCHUP_HEADLINE),
            (self.generate_btn, self._generate_tooltip),
            (copy_btn, help_text.CATCHUP_COPY),
            (refresh_btn, help_text.CATCHUP_REFRESH),
            (self.pull_btn, help_text.CATCHUP_PULL),
            (self.suggestion, help_text.CATCHUP_SUGGEST),
            (self.make_recurring_btn, help_text.CATCHUP_SUGGEST),
        ])

    def _generate_tooltip(self):
        """Reads differently once a brief exists, so resolve it on hover."""
        if "Regenerate" in str(self.generate_btn.cget("text")):
            return help_text.CATCHUP_REGENERATE
        return help_text.CATCHUP_GENERATE

    def _add_tab(self, title, tooltip):
        frame = ttk.Frame(self.tabs)
        box = ScrolledText(frame, wrap="word", height=8, width=34,
                           state="disabled", background="#FAFAFA")
        box.pack(fill="both", expand=True)
        attach(box, tooltip)
        self.tabs.add(frame, text=title)
        return box

    def show_suggestion(self, text):
        """Offer to turn an emerging pattern into a recurring meeting."""
        self.suggestion_var.set(text or "")
        if text:
            self.suggestion.pack(fill="x", pady=(4, 0), before=self.tabs)
        else:
            self.suggestion.pack_forget()

    # ------------------------------------------------------------------ state

    def _generate(self):
        if self.on_generate:
            self.on_generate()

    @staticmethod
    def _replace(box, text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text or "")
        box.configure(state="disabled")

    def show_headline(self, text):
        self.headline_var.set(text)

    def show_notice(self, text):
        """A one-line warning above the tabs — stale brief, no API key, and so on."""
        self.notice_var.set(text or "")
        if text:
            self.notice_label.pack(anchor="w", pady=(2, 0), before=self.tabs)
        else:
            self.notice_label.pack_forget()

    def show_pack(self, text):
        self._replace(self.pack_box, text)

    def show_brief(self, text):
        self._replace(self.brief_box, text)

    def select_brief_tab(self):
        self.tabs.select(0)

    def select_pack_tab(self):
        self.tabs.select(1)

    def set_generate_enabled(self, enabled, label=None):
        self.generate_btn.configure(state="normal" if enabled else "disabled")
        if label:
            self.generate_btn.configure(text=label)

    def set_pull_enabled(self, enabled, label=None):
        self.pull_btn.configure(state="normal" if enabled else "disabled")
        if label:
            self.pull_btn.configure(text=label)

    def visible_text(self):
        """Whichever tab is on top — what Copy should put on the clipboard."""
        box = self.brief_box if self.tabs.index(self.tabs.select()) == 0 else self.pack_box
        return box.get("1.0", "end").strip()
