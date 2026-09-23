"""Offers a meeting note the recordings an earlier crash left behind.

Files surviving on disk is not the same as getting them back: without this the
user would have to know the recordings folder exists, work out which stray file
was their meeting, and attach it by hand. The journal already knows which
captures never finished, so they can simply be offered.
"""

import threading
import tkinter as tk
from tkinter import ttk, messagebox

from recording_journal import interrupted_recordings
from recording_recovery import RecordingRestorer


class RecordingRecoveryFlow:
    """Finds interrupted recordings and attaches a chosen one to the note."""

    def __init__(self, dialog):
        self._dialog = dialog

    @staticmethod
    def available():
        return interrupted_recordings()

    def prompt(self):
        """Ask which interrupted recording to recover, then restore it."""
        candidates = self.available()
        if not candidates:
            messagebox.showinfo(
                "Nothing to recover",
                "No interrupted recordings were found.",
                parent=self._dialog,
            )
            return
        chosen = self._choose(candidates)
        if chosen is not None:
            self._restore(chosen)

    def _choose(self, candidates):
        if len(candidates) == 1:
            return candidates[0] if self._confirm_single(candidates[0]) else None
        return RecoveryChooser(self._dialog, candidates).result

    def _confirm_single(self, recording):
        return messagebox.askyesno(
            "Recover interrupted recording?",
            "A recording from "
            f"{recording.describe()} was never finished — the app closed while it "
            "was still running.\n\nRecover it and attach it to this meeting note?",
            parent=self._dialog,
        )

    def _restore(self, recording):
        dialog = self._dialog
        dialog._set_pipeline_busy(True, "Recovering recording…")
        dialog.status_var.set("Repairing the interrupted recording — this can take a minute…")

        def worker():
            restorer = RecordingRestorer()
            try:
                recovered = restorer.restore(recording)
                error = None
            except Exception as exc:
                recovered, error = None, exc
            dialog.after(0, lambda: self._finish(recording, recovered, error))

        threading.Thread(target=worker, daemon=True).start()

    def _finish(self, recording, recovered, error):
        dialog = self._dialog
        dialog._set_pipeline_busy(False)
        if error is not None or recovered is None or not recovered.recovered_anything:
            dialog.status_var.set(
                f"Could not recover that recording{f': {error}' if error else ''}. "
                "The original files are still in the recordings folder."
            )
            return

        for path in recovered.paths:
            dialog.artifacts.attach_media(path)
        dialog.artifacts_bar.refresh()
        recording.discard()

        note = " ".join(recovered.notes)
        dialog.status_var.set(
            f"Recovered {len(recovered.paths)} file(s) from the interrupted recording. "
            f"{note}".strip()
        )
        if recovered.transcription_path:
            dialog._attachment_transcriber.handle_attached(recovered.transcription_path)


class RecoveryChooser(tk.Toplevel):
    """Modal list of interrupted recordings; `result` is the chosen one."""

    def __init__(self, parent, candidates):
        super().__init__(parent)
        self.title("Recover an interrupted recording")
        self.transient(parent)
        self.resizable(False, False)
        self._candidates = candidates
        self.result = None

        ttk.Label(
            self,
            text="These recordings were interrupted before they finished.\n"
                 "Choose one to repair and attach to this meeting note.",
            justify="left",
        ).pack(anchor="w", padx=12, pady=(12, 6))

        self._listbox = tk.Listbox(self, width=64, height=min(8, len(candidates)))
        for recording in candidates:
            self._listbox.insert("end", recording.describe())
        self._listbox.selection_set(0)
        self._listbox.pack(fill="x", padx=12)

        buttons = ttk.Frame(self)
        buttons.pack(fill="x", padx=12, pady=12)
        ttk.Button(buttons, text="Recover", command=self._accept).pack(side="right")
        ttk.Button(buttons, text="Cancel", command=self.destroy).pack(side="right", padx=(0, 6))

        self.bind("<Return>", lambda _e: self._accept())
        self.bind("<Escape>", lambda _e: self.destroy())
        self.grab_set()
        self.wait_window(self)

    def _accept(self):
        selection = self._listbox.curselection()
        if selection:
            self.result = self._candidates[selection[0]]
        self.destroy()
