"""Summarise a stretch of time into the update you send someone who was away.

Pick a range — two weeks back by default — and the dialog assembles every
meeting and completed task in it. That pack is worth reading on its own, so it
is shown straight away and the AI write-up is a second tab you ask for.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

import ai_progress
import help_text
import progress_pack
from ai_client import has_api_key
from widgets.date_range_bar import DateRangeBar
from widgets.tooltip import attach, attach_all

NO_KEY_NOTICE = (
    "No OpenAI key set (⚙ or Ctrl+,) — “What happened” below still works."
)


class ProgressReportDialog(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("AI progress summary")
        self.geometry("720x620")
        self.minsize(560, 420)
        self._busy = False
        self._pack = None

        start, end = progress_pack.default_range()
        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        self.range_bar = DateRangeBar(
            frame, start_date=start, end_date=end, on_change=self.refresh
        )
        self.range_bar.pack(fill="x")

        self.headline_var = tk.StringVar()
        headline = ttk.Label(
            frame, textvariable=self.headline_var, font=("Segoe UI", 9, "bold")
        )
        headline.pack(anchor="w", pady=(0, 2))
        attach(headline, help_text.PROGRESS_HEADLINE)

        self.notice_var = tk.StringVar()
        self.notice_label = tk.Label(
            frame, textvariable=self.notice_var, fg="#B36B00", justify="left", anchor="w"
        )

        self.tabs = ttk.Notebook(frame)
        self.tabs.pack(fill="both", expand=True, pady=(4, 0))
        self.update_box = self._add_tab("Update", help_text.PROGRESS_UPDATE_TAB)
        self.pack_box = self._add_tab("What happened", help_text.PROGRESS_PACK_TAB)

        self._build_actions(frame)
        self.bind("<Escape>", lambda _event: self.destroy())
        self.transient(master)
        self.grab_set()
        self.refresh()

    def _add_tab(self, title, tooltip):
        holder = ttk.Frame(self.tabs)
        box = ScrolledText(holder, wrap="word", state="disabled", background="#FAFAFA")
        box.pack(fill="both", expand=True)
        attach(box, tooltip)
        self.tabs.add(holder, text=title)
        return box

    def _build_actions(self, parent):
        actions = ttk.Frame(parent)
        actions.pack(fill="x", pady=(8, 0))
        self.summarise_btn = tk.Button(
            actions,
            text="✦ Summarise with AI",
            command=self.summarise,
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
        self.summarise_btn.pack(side="left")
        copy_btn = ttk.Button(actions, text="Copy", command=self.copy_to_clipboard)
        copy_btn.pack(side="left", padx=6)
        self.status_var = tk.StringVar()
        ttk.Label(actions, textvariable=self.status_var, foreground="#555555").pack(
            side="left", padx=(6, 0)
        )
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        attach_all([
            (self.summarise_btn, help_text.PROGRESS_SUMMARISE),
            (copy_btn, help_text.PROGRESS_COPY),
        ])

    # ------------------------------------------------------------ the pack

    def refresh(self, _event=None):
        """Rebuild the deterministic pack for whatever range is showing."""
        if self._busy:
            return
        start, end = self.range_bar.get_range()
        if not progress_pack.valid_range(start, end):
            self._pack = None
            self.headline_var.set("Enter both dates as YYYY-MM-DD, earliest first.")
            self._show(self.pack_box, "")
            self._update_controls()
            return
        self._pack = progress_pack.build_pack(start, end)
        self.headline_var.set(self._pack.headline())
        self._show(self.pack_box, self._pack.render())
        self._show_notice("" if has_api_key() else NO_KEY_NOTICE)
        self._update_controls()

    def _update_controls(self):
        ready = bool(self._pack and self._pack.has_anything and has_api_key())
        self.summarise_btn.configure(state="normal" if ready else "disabled")

    def _show_notice(self, text):
        self.notice_var.set(text or "")
        if text:
            self.notice_label.pack(anchor="w", pady=(2, 0), before=self.tabs)
        else:
            self.notice_label.pack_forget()

    @staticmethod
    def _show(box, text):
        box.configure(state="normal")
        box.delete("1.0", "end")
        box.insert("1.0", text or "")
        box.configure(state="disabled")

    # -------------------------------------------------------------- the AI

    def summarise(self):
        if self._busy or not self._pack:
            return
        if not self._pack.has_anything:
            messagebox.showinfo(
                "Nothing in this range",
                "No meetings or completed tasks between those dates.",
                parent=self,
            )
            return
        self._set_busy(True, "Summarising…")
        pack_text = self._pack.render()
        start, end = self._pack.start_date, self._pack.end_date

        def worker():
            try:
                update = ai_progress.summarize_progress(pack_text)
            except RuntimeError as exc:
                self._post(lambda: self._on_failed(exc))
                return
            text = ai_progress.render(update, start_date=start, end_date=end)
            self._post(lambda: self._on_summarised(text))

        threading.Thread(target=worker, daemon=True).start()

    def _on_summarised(self, text):
        self._set_busy(False, "Update ready — Copy sends it to the clipboard.")
        self._show(self.update_box, text or "The AI returned nothing to show.")
        self.tabs.select(0)

    def _on_failed(self, exc):
        self._set_busy(False)
        messagebox.showerror("AI summary failed", str(exc), parent=self)

    def _set_busy(self, busy, status=""):
        self._busy = busy
        self.range_bar.set_enabled(not busy)
        self.status_var.set(status)
        if busy:
            self.summarise_btn.configure(state="disabled")
        else:
            self._update_controls()

    def _post(self, fn):
        """Run fn on the Tk thread, ignoring it if the dialog was closed."""
        try:
            self.after(0, lambda: fn() if self.winfo_exists() else None)
        except tk.TclError:
            pass

    # -------------------------------------------------------------- export

    def copy_to_clipboard(self):
        box = self.update_box if self.tabs.index(self.tabs.select()) == 0 else self.pack_box
        text = box.get("1.0", "end").strip()
        if not text:
            self.status_var.set("Nothing to copy on this tab yet.")
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        self.status_var.set("Copied to the clipboard.")
