"""Transcribes a recording of any length, one part at a time.

A single long upload is the fragile way to do this: one dropped connection
after fifty minutes and the whole thing starts over. Splitting the work means a
failure costs one part, the finished parts are still handed back, and the user
gets to watch it progress instead of staring at a frozen status line.
"""

import time

from audio.speech_audio import speech_chunks

RETRY_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = (3, 10)
# How much of the previous part is offered to the model as context, so a
# sentence cut across a boundary is still transcribed in the right register.
CONTEXT_CHARACTERS = 200

# Errors no amount of retrying will fix — retrying an unusable key just makes
# the user wait longer for the same message.
PERMANENT_MARKERS = (
    "rejected the api key",
    "no openai api key",
    "openai package is not installed",
    "no longer on disk",
)


class PartialTranscriptError(RuntimeError):
    """Some parts transcribed, then one failed. Carries what did succeed."""

    def __init__(self, cause, text, completed, total):
        super().__init__(str(cause))
        self.cause = cause
        self.text = text
        self.completed = completed
        self.total = total

    @property
    def has_text(self):
        return bool(self.text.strip())


class ChunkedTranscriber:
    """Runs a whole recording through the transcription API, part by part."""

    def __init__(self, transcribe, on_progress=None, sleep=time.sleep):
        self._transcribe = transcribe
        self._on_progress = on_progress
        self._sleep = sleep

    def transcribe(self, media_path):
        """Return the joined transcript. Raises on failure, with partial text."""
        with speech_chunks(media_path) as chunks:
            return self.transcribe_chunks(chunks)

    def transcribe_chunks(self, chunks):
        """Transcribe already-prepared parts, in order, joining the results."""
        total = len(chunks)
        parts = []
        for index, chunk in enumerate(chunks):
            self._report(index, total)
            try:
                parts.append(self._transcribe_with_retries(chunk, self._context(parts)))
            except Exception as exc:
                raise PartialTranscriptError(exc, self._join(parts), index, total) from exc
        self._report(total, total)
        return self._join(parts)

    def _transcribe_with_retries(self, chunk, context):
        last_error = None
        for attempt in range(RETRY_ATTEMPTS):
            try:
                return (self._transcribe(chunk, prompt=context) or "").strip()
            except Exception as exc:
                last_error = exc
                if not _is_worth_retrying(exc) or attempt == RETRY_ATTEMPTS - 1:
                    break
                self._sleep(RETRY_BACKOFF_SECONDS[min(attempt, len(RETRY_BACKOFF_SECONDS) - 1)])
        raise last_error

    def _report(self, done, total):
        if self._on_progress is not None and total > 1:
            self._on_progress(done, total)

    @staticmethod
    def _context(parts):
        for text in reversed(parts):
            if text:
                return text[-CONTEXT_CHARACTERS:]
        return None

    @staticmethod
    def _join(parts):
        return "\n\n".join(part for part in parts if part).strip()


def _is_worth_retrying(exc):
    message = str(exc).lower()
    return not any(marker in message for marker in PERMANENT_MARKERS)
