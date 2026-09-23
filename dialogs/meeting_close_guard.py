"""Decides whether a meeting note window is allowed to close."""

from tkinter import messagebox


class MeetingCloseGuard:
    """Blocks closing while work is in flight, and prompts about unsaved edits."""

    def __init__(self, dialog):
        self._dialog = dialog

    def may_leave(self):
        dialog = self._dialog
        if dialog.recording.is_recording:
            messagebox.showinfo(
                "Recording in progress",
                "Stop the recording first. You can start again later — "
                "extra clips stay on this meeting note.",
                parent=dialog,
            )
            return False

        if dialog._pipeline_busy:
            messagebox.showinfo(
                "Please wait",
                "Transcription or AI summary is still running.\n\n"
                "You can’t close this window until that finishes — for a long "
                "meeting this can take several minutes. If it fails, a "
                "message will appear and the window will unlock automatically.",
                parent=dialog,
            )
            return False

        if dialog.recording.has_pending_transcription and not self._discard_pending_clip():
            return False

        if not dialog.has_unsaved_changes():
            return True
        return self._resolve_unsaved()

    def _discard_pending_clip(self):
        dialog = self._dialog
        if not messagebox.askyesno(
            "Transcription incomplete",
            "The latest recording has not been transcribed successfully yet.\n\n"
            "Yes — Discard that transcription requirement and close\n"
            "No — Keep the window open (use Retry transcription)",
            parent=dialog,
            icon="warning",
            default=messagebox.NO,
        ):
            return False
        dialog.recording.clear_pending()
        return True

    def _resolve_unsaved(self):
        dialog = self._dialog
        choice = messagebox.askyesnocancel(
            "Unsaved meeting note",
            "You have unsaved changes.\n\n"
            "Yes — Save and close\n"
            "No — Discard and close\n"
            "Cancel — Keep editing",
            parent=dialog,
            icon="warning",
            default=messagebox.YES,
        )
        if choice is True:
            return dialog.save(close_after=True)
        if choice is False:
            return True
        return False
