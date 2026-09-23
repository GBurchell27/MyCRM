"""Transcribes a recording that was attached to a meeting note after the fact."""

import os
from tkinter import messagebox

from ai_summarizer import has_api_key
from dialogs.meeting_transcription_runner import MeetingTranscriptionRunner, describe_failure


class MeetingAttachmentTranscriber:
    """Runs the transcribe-on-attach flow for one MeetingDialog.

    Kept apart from the live recording pipeline: an attachment never becomes a
    session segment, so it can't block saving the way a pending clip does.
    """

    def __init__(self, dialog):
        self._dialog = dialog
        self._transcription = MeetingTranscriptionRunner(dialog)

    def handle_attached(self, path):
        dialog = self._dialog
        name = os.path.basename(path)
        dialog.status_var.set(f"Attached {name}. Save the note to keep the link.")
        if dialog.is_busy():
            return
        if not has_api_key():
            dialog.status_var.set(
                f"Attached {name}. Set an API key (⚙ settings) to transcribe it."
            )
            return
        if not self._confirm(name):
            return
        dialog._set_pipeline_busy(True, "Transcribing attached recording…")
        dialog.status_var.set(f"Transcribing {name}…")
        self._transcription.run(
            path, lambda text, error: self._finish(name, text, error), label=name
        )

    def _confirm(self, name):
        return messagebox.askyesno(
            "Transcribe this recording?",
            f"Transcribe {name} now and add it to this note's raw transcript?\n\n"
            "This sends the audio to the transcription API.",
            parent=self._dialog,
        )

    def _finish(self, name, text, error):
        """Keep any text that arrived, even when a later part failed."""
        dialog = self._dialog
        dialog._set_pipeline_busy(False)
        if text.strip():
            dialog.artifacts.add_transcript_text(text, heading=name)
            dialog.artifacts_bar.refresh()
        if error:
            dialog.status_var.set(describe_failure(error))
            return
        dialog.artifacts_bar.refresh()
        dialog.status_var.set(
            f"Transcript added from {name} — use View transcript, then Save the note."
        )
