"""Runs a recording through the transcription API on behalf of a dialog.

Kept separate from the recording controls because the two have different jobs:
one drives devices and buttons, this one shepherds a possibly very long upload
and keeps the window honest about how far it has got. A three-hour recording is
transcribed in parts, so "Transcribing…" can say which part it is on instead of
sitting still for twenty minutes and looking hung.
"""

import threading

from ai_summarizer import transcribe_audio
from audio.chunked_transcriber import ChunkedTranscriber, PartialTranscriptError


class MeetingTranscriptionRunner:
    """Transcribes one media file in the background for a Tk dialog."""

    def __init__(self, dialog):
        self._dialog = dialog

    def run(self, media_path, on_done, label="recording"):
        """Transcribe `media_path`, then call `on_done(text, error)` on the UI thread.

        `error` is None on success. A PartialTranscriptError carries whatever
        parts did transcribe, so the caller can keep them rather than throwing
        away forty minutes of work because the last part timed out.
        """
        threading.Thread(
            target=self._worker, args=(media_path, on_done, label), daemon=True
        ).start()

    def _worker(self, media_path, on_done, label):
        transcriber = ChunkedTranscriber(
            transcribe_audio, on_progress=lambda done, total: self._report(done, total, label)
        )
        try:
            text = transcriber.transcribe(media_path)
            self._finish(on_done, text, None)
        except PartialTranscriptError as exc:
            self._finish(on_done, exc.text, exc)
        except Exception as exc:
            self._finish(on_done, "", exc)

    def _report(self, done, total, label):
        message = f"Transcribing {label} — part {min(done + 1, total)} of {total}…"
        self._on_ui(lambda: self._dialog.status_var.set(message))

    def _finish(self, on_done, text, error):
        self._on_ui(lambda: on_done(text, error))

    def _on_ui(self, action):
        """Hop back to the Tk thread, ignoring a window closed underneath us."""
        try:
            self._dialog.after(0, action)
        except Exception:
            pass


def describe_failure(error):
    """A message for the user explaining a transcription failure."""
    if isinstance(error, PartialTranscriptError) and error.has_text:
        return (
            f"Transcription stopped after part {error.completed} of {error.total} "
            f"({error.cause}). The text from the finished parts was kept — "
            "use Retry transcription to do the whole recording again. "
            "The audio file is safe on disk either way."
        )
    return (
        f"Transcription failed: {error}. The recording is safe on disk — "
        "fix the issue, then Retry."
    )
