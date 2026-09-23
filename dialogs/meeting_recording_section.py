"""Recording, media and transcription pipeline for one meeting note window.

Owns the recorder, the capture session, and every control that drives them, so
the dialog is left with layout, notes, and saving. The dialog supplies the
surrounding chrome (status line, busy state, title) and is called back when a
transcript lands, since deciding what to do with it is the dialog's business.
"""

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import help_text
from ai_summarizer import has_api_key
from config.app_settings import RECORD_INCLUDE_SYSTEM_AUDIO, RECORD_INCLUDE_VIDEO
from dialogs.meeting_transcription_runner import MeetingTranscriptionRunner, describe_failure
from meeting_session_capture import MeetingSessionCapture
from recorder import MeetingRecorder, system_audio_available
from widgets.recording_indicator import RecordingIndicator
from widgets.tooltip import attach_all

# How often the window checks whether a capture device has dropped out. Long
# enough to be invisible, short enough that a dead microphone is noticed while
# the meeting can still be rescued rather than an hour later.
HEALTH_POLL_MS = 3000


class MeetingRecordingSection:
    """Drives record → media → transcribe for one MeetingDialog."""

    def __init__(self, dialog):
        self._dialog = dialog
        self.recorder = MeetingRecorder()
        self.session = MeetingSessionCapture()
        self._transcription = MeetingTranscriptionRunner(dialog)
        self.pending_segment = None
        self.record_btn = None
        self.retry_btn = None
        self.indicator = None
        self._health_job = None
        self.include_video_var = tk.BooleanVar(
            master=dialog, value=RECORD_INCLUDE_VIDEO.get()
        )
        # A machine with no loopback device can't honour the preference either way.
        self.include_system_audio_var = tk.BooleanVar(
            master=dialog,
            value=RECORD_INCLUDE_SYSTEM_AUDIO.get() and system_audio_available(),
        )

    # ------------------------------------------------------------------ state

    @property
    def is_recording(self):
        return self.recorder.is_recording

    @property
    def has_pending_transcription(self):
        return self.pending_segment is not None

    def clear_pending(self):
        """Drop the outstanding transcription requirement (user chose to discard)."""
        self.pending_segment = None
        if self.retry_btn is not None:
            self.retry_btn.configure(state="disabled")

    def set_record_enabled(self, enabled):
        if self.record_btn is not None:
            self.record_btn.configure(state="normal" if enabled else "disabled")

    # --------------------------------------------------------------- controls

    def build_record_button(self, parent):
        self.record_btn = ttk.Button(
            parent, text="● Start recording (F9)", command=self.toggle, width=22
        )
        return self.record_btn

    def build_retry_button(self, parent):
        self.retry_btn = ttk.Button(
            parent,
            text="Retry transcription",
            command=self.retry_transcription,
            state="disabled",
        )
        return self.retry_btn

    def build_capture_options(self, parent):
        """The include-video / include-system-audio checkboxes, in one frame."""
        options = ttk.Frame(parent)
        video_check = ttk.Checkbutton(
            options, text="Include screen video", variable=self.include_video_var
        )
        video_check.pack(side="left", padx=(10, 0))
        system_audio_check = ttk.Checkbutton(
            options, text="Include system audio", variable=self.include_system_audio_var
        )
        system_audio_check.pack(side="left", padx=(10, 0))
        available = system_audio_available()
        if not available:
            system_audio_check.configure(state="disabled")
        attach_all([
            (video_check, help_text.INCLUDE_VIDEO),
            (system_audio_check, help_text.INCLUDE_SYSTEM_AUDIO if available else
             "No system-audio device was found on this machine."),
        ])
        return options

    def build_indicator(self, parent):
        self.indicator = RecordingIndicator(parent, stop_command=self.stop)
        return self.indicator

    def handle_shortcut(self, _event):
        if self.record_btn is not None and str(self.record_btn.cget("state")) != "disabled":
            self.toggle()
        return "break"

    # -------------------------------------------------------------- recording

    def toggle(self):
        if self.recorder.is_recording:
            self.stop()
        else:
            self.start()

    def start(self):
        dialog = self._dialog
        if dialog.is_busy() or self.has_pending_transcription:
            messagebox.showinfo(
                "Finish processing first",
                "Wait for transcription to succeed (or use Retry) before recording again.",
                parent=dialog,
            )
            return
        other = dialog.other_recording_dialog()
        if other is not None:
            other.lift()
            messagebox.showinfo(
                "Another recording is running",
                "Another meeting window is already recording the microphone.\n"
                "Stop that recording first.",
                parent=dialog,
            )
            return
        try:
            self.recorder.start(
                include_video=self.include_video_var.get(),
                include_system_audio=self.include_system_audio_var.get(),
                note_title=dialog.base_title,
            )
        except RuntimeError as exc:
            messagebox.showerror("Recording unavailable", str(exc), parent=dialog)
            return
        self.record_btn.configure(text="■ Stop recording (F9)")
        self.indicator.start()
        dialog.title("● RECORDING — " + dialog.base_title)
        dialog.status_var.set(
            f"● RECORDING clip {len(self.session) + 1} — {self.capture_summary()}"
        )
        self._start_health_polling()

    # ----------------------------------------------------------------- health

    def _start_health_polling(self):
        """Watch for a capture device dropping out while the meeting runs."""
        self._cancel_health_polling()
        self._health_job = self._dialog.after(HEALTH_POLL_MS, self._poll_health)

    def _cancel_health_polling(self):
        if self._health_job is not None:
            try:
                self._dialog.after_cancel(self._health_job)
            except Exception:
                pass
            self._health_job = None

    def _poll_health(self):
        self._health_job = None
        if not self.recorder.is_recording:
            return
        for problem in self.recorder.take_problems():
            self._announce_problem(problem)
        self.indicator.set_elapsed(self.recorder.elapsed_seconds)
        self._health_job = self._dialog.after(HEALTH_POLL_MS, self._poll_health)

    def _announce_problem(self, problem):
        """Say it in the window rather than burying it in the activity log.

        The recording carries on regardless — the point is that the user finds
        out now, while they can still switch device or start a second clip.
        """
        self._dialog.status_var.set(f"● RECORDING — {problem}")
        self.indicator.set_warning(problem)

    def capture_summary(self):
        sources = ["mic"]
        if self.include_system_audio_var.get():
            sources.append("system audio")
        if self.include_video_var.get():
            sources.append("screen")
        sources.append("active windows")
        return " + ".join(sources) + "…"

    def stop(self):
        if not self.recorder.is_recording:
            return
        dialog = self._dialog
        self._cancel_health_polling()
        self.indicator.set_stopping()
        dialog.title(dialog.base_title)
        dialog._set_pipeline_busy(True, "Finalizing recording…")
        dialog.status_var.set("Stopping recording (finalizing video if enabled)…")
        self.set_record_enabled(False)

        def worker():
            result = self.recorder.stop()
            dialog.after(0, lambda: self._on_stopped(result))

        threading.Thread(target=worker, daemon=True).start()

    def _on_stopped(self, result):
        dialog = self._dialog
        self.indicator.stop()
        self.record_btn.configure(text="● Start recording (F9)")
        segment_index = self.session.add_result(result)
        dialog.artifacts_bar.refresh()

        saved = self._describe_saved_media(result)
        session_label = self.session.describe()
        if not result.transcription_path:
            dialog._set_pipeline_busy(False)
            dialog.status_var.set(
                f"{saved}. {session_label}. You can record again or AI Summarize notes."
            )
            return

        if not has_api_key():
            dialog._set_pipeline_busy(False)
            dialog.status_var.set(
                f"{saved}. {session_label}. Set an API key (⚙ settings) "
                "then use Retry transcription, or paste notes and AI Summarize."
            )
            self.pending_segment = segment_index
            self.retry_btn.configure(state="normal")
            return

        self.pending_segment = segment_index
        self.retry_btn.configure(state="disabled")
        dialog.status_var.set(f"{saved}. {session_label}. Transcribing audio…")
        dialog._set_pipeline_busy(True, "Transcribing recording…")
        self._begin_transcription(segment_index, result.transcription_path)

    @staticmethod
    def _describe_saved_media(result):
        parts = []
        if result.audio_path:
            parts.append(f"Audio: {os.path.basename(result.audio_path)}")
        if result.video_path:
            label = "Video with audio" if result.audio_in_video else "Video"
            parts.append(f"{label}: {os.path.basename(result.video_path)}")
        return " · ".join(parts) if parts else "No media captured"

    # ---------------------------------------------------------- transcription

    def retry_transcription(self):
        dialog = self._dialog
        if dialog.is_busy() or not self.has_pending_transcription:
            return
        if not has_api_key():
            messagebox.showerror(
                "API key needed",
                "Set an OpenAI API key via the ⚙ settings button (Ctrl+,) first.",
                parent=dialog,
            )
            return
        index = self.pending_segment
        path = self.session.transcription_path_for(index)
        if not path:
            messagebox.showinfo("Nothing to transcribe", "That clip has no audio.", parent=dialog)
            self.clear_pending()
            return
        self.retry_btn.configure(state="disabled")
        dialog.status_var.set("Retrying transcription…")
        dialog._set_pipeline_busy(True, "Transcribing recording…")
        self._begin_transcription(index, path)

    def _begin_transcription(self, segment_index, media_path):
        self._transcription.run(
            media_path,
            lambda text, error: self._on_transcribed(segment_index, text, error),
            label=f"recording {segment_index + 1}",
        )

    def _on_transcribed(self, segment_index, text, error):
        dialog = self._dialog
        if error:
            self._on_transcription_failed(segment_index, text, error)
            return

        self.session.set_transcript(segment_index, text)
        dialog.artifacts_bar.refresh()
        self.clear_pending()
        dialog.status_var.set(
            f"Transcript ready ({self.session.describe()}). Running AI summarize…"
        )
        dialog.on_transcript_ready(segment_index)

    def _on_transcription_failed(self, segment_index, partial_text, error):
        """Keep whatever did transcribe, and leave the clip retryable.

        Nothing is discarded on a failure: the parts that came back are stored
        against the clip, and the audio file itself is untouched on disk, so a
        retry later costs nothing but time.
        """
        dialog = self._dialog
        if partial_text.strip():
            self.session.set_transcript(segment_index, partial_text)
            dialog.artifacts_bar.refresh()
        dialog._set_pipeline_busy(False)
        self.pending_segment = segment_index
        self.retry_btn.configure(state="normal")
        dialog.status_var.set(describe_failure(error))
