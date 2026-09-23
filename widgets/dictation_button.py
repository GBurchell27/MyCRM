"""Mic toggle button that dictates speech into an Entry/Combobox/Text widget."""

import os
import tempfile
import threading
import time
import tkinter as tk
from tkinter import messagebox

from ai_summarizer import DICTATION_PROMPT, has_api_key, transcribe_audio
from audio.sources import MicrophoneSource
from audio.wav_writer import write_mono_wav
from config.app_settings import DICTATION_MAX_MINUTES


def max_seconds():
    """The dictation cut-off, from settings.

    16 kHz mono PCM16 hits Whisper's 25 MB upload cap around 13 minutes; the
    setting is capped below that so a forgotten mic never produces an
    untranscribable file.
    """
    return DICTATION_MAX_MINUTES.get() * 60


def dictation_available():
    try:
        import numpy  # noqa: F401
    except ImportError:
        return False
    return MicrophoneSource.is_available()


class DictationButton(tk.Button):
    """Click to record the mic, click again to insert the Whisper transcript.

    The transcript lands at the cursor of `target` (Entry, Combobox, Text, or
    ScrolledText). Only one DictationButton records at a time app-wide.
    `single_line` collapses the transcript to one line for short fields.
    `can_start` may return an error string to block recording (e.g. while a
    meeting recording already owns the mic). `on_status` receives progress text.
    """

    _recording_button = None

    _REC_BG = "#D32F2F"
    _REC_ACTIVE_BG = "#B71C1C"

    def __init__(self, master, target=None, single_line=False, on_status=None,
                 can_start=None, **kwargs):
        kwargs.setdefault("text", "🎤")
        kwargs.setdefault("font", ("Segoe UI Emoji", 9))
        kwargs.setdefault("relief", "flat")
        kwargs.setdefault("cursor", "hand2")
        kwargs.setdefault("takefocus", 0)
        kwargs.setdefault("padx", 5)
        kwargs.setdefault("pady", 0)
        super().__init__(master, command=self.toggle, **kwargs)
        self.target = target
        self.single_line = single_line
        self.on_status = on_status
        self.can_start = can_start
        self._idle_bg = self.cget("background")
        self._idle_fg = self.cget("foreground")
        self._source = None
        self._busy = False
        self._started_at = 0.0
        self._max_seconds = 0
        self._timer_job = None
        self.bind("<Destroy>", self._on_destroy)

    @property
    def is_recording(self):
        return self._source is not None

    def toggle(self):
        if self._busy:
            return
        if self._source is not None:
            self._finish()
        else:
            self._begin()

    # -- recording ---------------------------------------------------------

    def _begin(self):
        parent = self.winfo_toplevel()
        if DictationButton._recording_button is not None:
            messagebox.showinfo(
                "Dictation busy",
                "Another dictation is already recording — stop that one first.",
                parent=parent,
            )
            return
        blocked = self.can_start() if self.can_start else None
        if blocked:
            messagebox.showinfo("Dictation unavailable", blocked, parent=parent)
            return
        if not dictation_available():
            messagebox.showerror(
                "Dictation unavailable",
                "Recording packages are not installed.\n\n"
                "Run: pip install sounddevice numpy",
                parent=parent,
            )
            return
        if not has_api_key():
            messagebox.showerror(
                "API key needed",
                "Set an OpenAI API key via the ⚙ settings button (Ctrl+,) first.",
                parent=parent,
            )
            return

        self._source = MicrophoneSource()
        self._source.start()
        DictationButton._recording_button = self
        self._started_at = time.monotonic()
        # Read once per recording, so changing the setting can't cut short a
        # dictation that is already running.
        self._max_seconds = max_seconds()
        self.configure(
            text="⏹",
            background=self._REC_BG,
            foreground="white",
            activebackground=self._REC_ACTIVE_BG,
            activeforeground="white",
            relief="sunken",
        )
        self._tick()

    def _tick(self):
        if self._source is None:
            return
        elapsed = time.monotonic() - self._started_at
        if elapsed >= self._max_seconds:
            minutes = self._max_seconds // 60
            self._status(f"Dictation reached the {minutes}-minute limit — transcribing…")
            self._finish()
            return
        self._status(
            f"● Dictating {self._format_elapsed(elapsed)} — "
            "click ⏹ to stop and insert the transcript."
        )
        self._timer_job = self.after(500, self._tick)

    @staticmethod
    def _format_elapsed(seconds):
        minutes, secs = divmod(int(seconds), 60)
        return f"{minutes}:{secs:02d}"

    # -- transcription -----------------------------------------------------

    def _finish(self):
        self._cancel_timer()
        source, self._source = self._source, None
        DictationButton._recording_button = None
        self._busy = True
        self.configure(
            text="…",
            state="disabled",
            background=self._idle_bg,
            foreground=self._idle_fg,
            relief="flat",
        )
        self._status("Transcribing dictation…")

        def worker():
            text, error = "", None
            track = source.stop()
            if source.error:
                error = RuntimeError(source.error)
            elif track is not None and len(track):
                fd, wav_path = tempfile.mkstemp(prefix="dictation_", suffix=".wav")
                os.close(fd)
                try:
                    if write_mono_wav(wav_path, track, source.sample_rate):
                        text = transcribe_audio(wav_path, prompt=DICTATION_PROMPT)
                except Exception as exc:
                    error = exc
                finally:
                    try:
                        os.remove(wav_path)
                    except OSError:
                        pass
            self._post(lambda: self._on_transcribed(text, error))

        threading.Thread(target=worker, daemon=True).start()

    def _on_transcribed(self, text, error):
        self._busy = False
        self.configure(text="🎤", state="normal")
        if error:
            self._status("Dictation failed.")
            messagebox.showerror("Dictation failed", str(error), parent=self.winfo_toplevel())
            return
        text = self._clean(text)
        if not text:
            self._status("Dictation heard no speech — nothing inserted.")
            return
        self._insert(text)
        self._status(f"Dictation inserted ({len(text.split())} words).")

    def _clean(self, text):
        text = (text or "").strip()
        if self.single_line:
            text = " ".join(text.split())
            if text.endswith(".") and not text.endswith(".."):
                text = text[:-1]
        return text

    def _insert(self, text):
        widget = self.target
        if widget is None or not widget.winfo_exists():
            return
        if isinstance(widget, tk.Text):
            before = widget.get("insert-1c", "insert")
            if before and not before.isspace():
                text = " " + text
            widget.insert("insert", text)
            widget.see("insert")
        else:  # Entry / Combobox
            pos = widget.index("insert")
            value = widget.get()
            if pos > 0 and not value[pos - 1].isspace():
                text = " " + text
            widget.insert(pos, text)
            widget.icursor(pos + len(text))
        widget.focus_set()

    # -- plumbing ----------------------------------------------------------

    def _status(self, message):
        if self.on_status:
            self.on_status(message)

    def _cancel_timer(self):
        if self._timer_job is not None:
            self.after_cancel(self._timer_job)
            self._timer_job = None

    def _post(self, fn):
        """Run fn on the Tk thread, ignoring it if the widget was destroyed."""
        try:
            self.after(0, lambda: fn() if self.winfo_exists() else None)
        except tk.TclError:
            pass

    def _on_destroy(self, event):
        if event.widget is not self:
            return
        self._cancel_timer()
        source, self._source = self._source, None
        if DictationButton._recording_button is self:
            DictationButton._recording_button = None
        if source is not None:
            threading.Thread(target=lambda: source.stop(timeout=1), daemon=True).start()
