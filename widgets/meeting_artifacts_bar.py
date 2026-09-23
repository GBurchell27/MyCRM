"""Buttons for opening a meeting note's recordings and raw transcript."""

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import help_text
from dialogs.transcript_window import TranscriptWindow
from widgets.tooltip import attach
from paths import RECORDINGS_DIR
from recording_journal import interrupted_recordings


class MeetingArtifactsBar(ttk.Frame):
    """Menubutton listing playable media, plus a raw-transcript viewer button."""

    def __init__(self, parent, artifacts, transcript_title="Raw transcript",
                 on_attach=None, on_recover=None):
        super().__init__(parent)
        self._artifacts = artifacts
        self._transcript_title = transcript_title
        self._on_attach = on_attach
        self._on_recover = on_recover
        self._recover_btn = None
        self._recover_shown = False
        self._transcript_window = None

        self.media_menu = tk.Menu(self, tearoff=0)
        self.media_btn = ttk.Menubutton(
            self, text="Open recording ▾", menu=self.media_menu, state="disabled"
        )
        self.media_btn.pack(side="left")
        self.transcript_btn = ttk.Button(
            self, text="View transcript", command=self.open_transcript, state="disabled"
        )
        self.transcript_btn.pack(side="left", padx=(4, 0))
        if on_attach is not None:
            ttk.Button(self, text="Attach recording…", command=self.attach_recording).pack(
                side="left", padx=(4, 0)
            )
        if on_recover is not None:
            # Only worth showing when something actually needs rescuing, so the
            # bar stays quiet for the overwhelming majority of meetings.
            self._recover_btn = ttk.Button(
                self, text="⟳ Recover interrupted…", command=self._on_recover
            )
            attach(self._recover_btn, help_text.RECOVER_RECORDING)
        self.refresh()

    def attach_recording(self):
        """Link a file already on disk (e.g. from an older session) to this note."""
        path = filedialog.askopenfilename(
            parent=self.winfo_toplevel(),
            title="Choose a recording for this meeting note",
            initialdir=RECORDINGS_DIR if os.path.isdir(RECORDINGS_DIR) else None,
            filetypes=[
                ("Recordings", "*.mp4 *.avi *.mkv *.mov *.wav *.mp3 *.m4a"),
                ("All files", "*.*"),
            ],
        )
        if not path:
            return
        if not self._artifacts.attach_media(path):
            messagebox.showinfo(
                "Already attached",
                "That file is already linked to this meeting note.",
                parent=self.winfo_toplevel(),
            )
            return
        self.refresh()
        self._on_attach(path)

    def refresh(self):
        self._rebuild_media_menu()
        state = "normal" if self._artifacts.has_transcript else "disabled"
        self.transcript_btn.configure(state=state)
        self._refresh_recover_button()

    def _refresh_recover_button(self):
        """Show the button only while something is actually waiting to be rescued.

        Tracked with a flag rather than `winfo_ismapped`, which reports "not
        shown" for every widget in a window that has not been drawn yet.
        """
        if self._recover_btn is None:
            return
        wanted = bool(interrupted_recordings())
        if wanted == self._recover_shown:
            return
        if wanted:
            self._recover_btn.pack(side="left", padx=(4, 0))
        else:
            self._recover_btn.pack_forget()
        self._recover_shown = wanted

    def _rebuild_media_menu(self):
        self.media_menu.delete(0, "end")
        items = self._artifacts.media_items()
        if not items:
            self.media_btn.configure(state="disabled")
            return
        self.media_btn.configure(state="normal")
        for item in items:
            path = item["path"]
            self.media_menu.add_command(
                label=item["label"],
                command=lambda p=path: self.open_media(p),
            )

    def open_media(self, path):
        """Hand the file to the OS so it plays in its own player window."""
        if not path or not os.path.isfile(path):
            messagebox.showinfo(
                "Missing file",
                "That recording file is no longer available on disk.",
                parent=self.winfo_toplevel(),
            )
            self.refresh()
            return
        try:
            os.startfile(path)
        except OSError as exc:
            messagebox.showerror("Could not open", str(exc), parent=self.winfo_toplevel())

    def open_transcript(self):
        text = self._artifacts.transcript_text
        if not text:
            return
        if self._transcript_window is not None and self._transcript_window.winfo_exists():
            self._transcript_window.destroy()
        self._transcript_window = TranscriptWindow(
            self.winfo_toplevel(), text, title=self._transcript_title
        )
        self._transcript_window.lift()
