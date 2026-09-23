"""Dialog to outsource a task to Claude Code in a chosen repo."""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText

from claude_launcher import build_prompt, launch_claude_code
from db import get_setting, set_setting
from widgets.dictation_button import DictationButton

LAST_REPO_KEY = "claude_last_repo"


class OutsourceDialog(tk.Toplevel):
    def __init__(self, master, task):
        super().__init__(master)
        self.title("Send to Claude Code")
        self.task = task
        self.geometry("520x420")
        self.resizable(True, True)

        form = ttk.Frame(self, padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(6, weight=1)

        ttk.Label(
            form, text=task["title"] or "", font=("Segoe UI", 10, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(form, text="Repo / project folder:").grid(
            row=1, column=0, sticky="w", pady=(0, 4)
        )
        self.repo_var = tk.StringVar(value=get_setting(LAST_REPO_KEY))
        repo_entry = ttk.Entry(form, textvariable=self.repo_var)
        repo_entry.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        ttk.Button(form, text="Browse...", command=self.browse_repo).grid(
            row=2, column=1, sticky="w", padx=(6, 0), pady=(0, 8)
        )

        ttk.Label(
            form,
            text="Instructions for Claude (task prefilled — add context or details):",
        ).grid(row=5, column=0, sticky="w", pady=(0, 4))
        self.instructions_box = ScrolledText(form, height=8, wrap="word")
        self.instructions_box.grid(row=6, column=0, columnspan=2, sticky="nsew")
        DictationButton(form, self.instructions_box).grid(
            row=5, column=1, sticky="e", pady=(0, 4)
        )
        self.instructions_box.insert(
            "1.0", build_prompt(task["title"], notes=task["notes"]) + "\n\n"
        )
        self.instructions_box.mark_set("insert", "end")

        self.auto_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            form,
            text="Start immediately (otherwise the prompt is copied so you can "
            "paste it and press Enter)",
            variable=self.auto_var,
        ).grid(row=7, column=0, columnspan=2, sticky="w", pady=(8, 0))

        btns = ttk.Frame(self, padding=(12, 0, 12, 12))
        btns.pack(fill="x")
        ttk.Button(btns, text="Launch Claude Code", command=self.launch).pack(
            side="right", padx=4
        )
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

        (repo_entry if not self.repo_var.get() else self.instructions_box).focus_set()
        self.transient(master)
        self.grab_set()

    def browse_repo(self):
        chosen = filedialog.askdirectory(
            parent=self, initialdir=self.repo_var.get() or None
        )
        if chosen:
            self.repo_var.set(chosen)

    def launch(self):
        repo = self.repo_var.get().strip()
        if not repo:
            messagebox.showwarning(
                "Missing folder", "Choose the repo folder first.", parent=self
            )
            return
        prompt = self.instructions_box.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning(
                "Empty prompt",
                "The prompt is empty — write what Claude should do.",
                parent=self,
            )
            return
        try:
            launch_claude_code(repo, prompt, auto_submit=self.auto_var.get())
        except (ValueError, OSError) as exc:
            messagebox.showerror("Launch failed", str(exc), parent=self)
            return
        set_setting(LAST_REPO_KEY, repo)
        self.destroy()
