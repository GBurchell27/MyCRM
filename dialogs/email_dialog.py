"""Dialog to turn a task into an email draft, opened in Outlook for the user to send."""

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from email_drafter import build_email_context, draft_email, open_outlook_draft
from widgets.dictation_button import DictationButton


class EmailDialog(tk.Toplevel):
    def __init__(self, master, task):
        super().__init__(master)
        self.title("Draft email from task")
        self.task = task
        self.geometry("560x640")
        self.resizable(True, True)
        self._busy = False

        form = ttk.Frame(self, padding=12)
        form.pack(fill="both", expand=True)
        form.columnconfigure(0, weight=1)
        form.rowconfigure(4, weight=1)
        form.rowconfigure(9, weight=2)

        ttk.Label(
            form, text=task["title"] or "", font=("Segoe UI", 10, "bold")
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(form, text="To (name or email — Outlook will look names up):").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        self.to_var = tk.StringVar()
        ttk.Entry(form, textvariable=self.to_var).grid(
            row=2, column=0, columnspan=2, sticky="ew", pady=(0, 8)
        )

        ttk.Label(
            form,
            text="What should the email say? (task prefilled — add context or details):",
        ).grid(row=3, column=0, sticky="w", pady=(0, 4))
        self.context_box = ScrolledText(form, height=6, wrap="word")
        self.context_box.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.context_box.insert(
            "1.0", build_email_context(task["title"], notes=task["notes"]) + "\n\n"
        )
        self.context_box.mark_set("insert", "end")
        DictationButton(
            form, self.context_box, on_status=self._dictation_status
        ).grid(row=3, column=1, sticky="e", pady=(0, 4))

        draft_bar = ttk.Frame(form)
        draft_bar.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        self.draft_btn = tk.Button(
            draft_bar,
            text="✦ Draft with AI",
            command=self.draft_with_ai,
            font=("Segoe UI", 10, "bold"),
            fg="white",
            bg="#1565C0",
            activeforeground="white",
            activebackground="#0D47A1",
            disabledforeground="#90CAF9",
            padx=14,
            pady=6,
            cursor="hand2",
            relief="raised",
            bd=2,
        )
        self.draft_btn.pack(side="left")
        self.status_var = tk.StringVar()
        ttk.Label(draft_bar, textvariable=self.status_var, foreground="#555555").pack(
            side="left", padx=(10, 0)
        )

        ttk.Label(form, text="Subject:").grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(0, 4)
        )
        self.subject_var = tk.StringVar()
        subject_entry = ttk.Entry(form, textvariable=self.subject_var)
        subject_entry.grid(row=7, column=0, sticky="ew", pady=(0, 8))
        DictationButton(
            form, subject_entry, single_line=True, on_status=self._dictation_status
        ).grid(row=7, column=1, sticky="e", padx=(4, 0), pady=(0, 8))

        ttk.Label(form, text="Email body (edit before opening in Outlook):").grid(
            row=8, column=0, sticky="w", pady=(0, 4)
        )
        self.body_box = ScrolledText(form, height=10, wrap="word")
        self.body_box.grid(row=9, column=0, columnspan=2, sticky="nsew")
        DictationButton(
            form, self.body_box, on_status=self._dictation_status
        ).grid(row=8, column=1, sticky="e", pady=(0, 4))

        btns = ttk.Frame(self, padding=(12, 8, 12, 12))
        btns.pack(fill="x")
        self.open_btn = ttk.Button(
            btns, text="Open in Outlook", command=self.open_in_outlook
        )
        self.open_btn.pack(side="right", padx=4)
        ttk.Button(btns, text="Cancel", command=self.destroy).pack(side="right")

        self.context_box.focus_set()
        self.transient(master)
        self.grab_set()

    def _dictation_status(self, message):
        if not self._busy:
            self.status_var.set(message)

    def _set_busy(self, busy, status=""):
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.draft_btn.configure(state=state)
        self.open_btn.configure(state=state)
        self.status_var.set(status)

    def draft_with_ai(self):
        if self._busy:
            return
        context = self.context_box.get("1.0", "end").strip()
        if not context:
            messagebox.showwarning(
                "Nothing to draft from",
                "Describe what the email should say first.",
                parent=self,
            )
            return
        self._set_busy(True, "Drafting…")
        recipient = self.to_var.get().strip()

        def worker():
            try:
                draft = draft_email(context, recipient=recipient)
            except RuntimeError as exc:
                self._post(lambda: self._on_draft_failed(exc))
                return
            self._post(lambda: self._on_drafted(draft))

        threading.Thread(target=worker, daemon=True).start()

    def _on_drafted(self, draft):
        self._set_busy(False, "Draft ready — review and edit below.")
        if draft["to_name"] and not self.to_var.get().strip():
            self.to_var.set(draft["to_name"])
        if draft["subject"]:
            self.subject_var.set(draft["subject"])
        if draft["body"]:
            self.body_box.delete("1.0", "end")
            self.body_box.insert("1.0", draft["body"])

    def _on_draft_failed(self, exc):
        self._set_busy(False)
        messagebox.showerror("AI drafting failed", str(exc), parent=self)

    def open_in_outlook(self):
        if self._busy:
            return
        body = self.body_box.get("1.0", "end").strip()
        if not body:
            messagebox.showwarning(
                "Empty email",
                "Write the email body first (or use Draft with AI).",
                parent=self,
            )
            return
        self._set_busy(True, "Opening Outlook draft…")
        to = self.to_var.get().strip()
        subject = self.subject_var.get().strip()

        def worker():
            try:
                how = open_outlook_draft(to, subject, body)
            except RuntimeError as exc:
                self._post(lambda: self._on_open_failed(exc))
                return
            self._post(lambda: self._on_opened(how))

        threading.Thread(target=worker, daemon=True).start()

    def _on_opened(self, how):
        if how == "mailto":
            messagebox.showinfo(
                "Draft opened",
                "Outlook automation was unavailable, so the draft was opened "
                "via your default mail handler. Check the recipient before sending.",
                parent=self,
            )
        self.destroy()

    def _on_open_failed(self, exc):
        self._set_busy(False)
        messagebox.showerror("Could not open draft", str(exc), parent=self)

    def _post(self, fn):
        """Run fn on the Tk thread, ignoring it if the dialog was closed."""
        try:
            self.after(0, lambda: fn() if self.winfo_exists() else None)
        except tk.TclError:
            pass
