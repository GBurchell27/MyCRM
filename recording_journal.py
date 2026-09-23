"""Tracks recordings that are in flight, so a crash leaves a trail to follow.

Media on disk is only half the job: after the app dies, nothing knows those
files were a meeting. A journal file is written beside each recording as it
starts and removed when it finishes cleanly, so anything left behind is by
definition a recording that was interrupted, and can be offered back to the
user instead of sitting unnoticed in the recordings folder.
"""

import json
import os
from datetime import datetime

from paths import RECORDINGS_DIR, ensure_recordings_dir

JOURNAL_SUFFIX = ".journal.json"
STATE_RECORDING = "recording"


class RecordingJournal:
    """The sidecar for one capture, from start to clean finish."""

    def __init__(self, stamp, recordings_dir=None):
        self.stamp = stamp
        self.recordings_dir = recordings_dir or RECORDINGS_DIR

    @property
    def path(self):
        return os.path.join(self.recordings_dir, f"meeting_{self.stamp}{JOURNAL_SUFFIX}")

    def open(self, media_paths, note_title=""):
        """Record that a capture has begun and which files it is writing."""
        ensure_recordings_dir()
        self._write({
            "stamp": self.stamp,
            "state": STATE_RECORDING,
            "started_at": datetime.now().isoformat(timespec="seconds"),
            "pid": os.getpid(),
            "note_title": note_title or "",
            "media": [p for p in media_paths if p],
        })

    def close(self):
        """Drop the sidecar — the recording finished and needs no recovery."""
        try:
            os.remove(self.path)
        except OSError:
            pass

    def _write(self, payload):
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
        except OSError:
            pass


class InterruptedRecording:
    """A capture whose journal outlived the process that was writing it."""

    def __init__(self, payload, journal_path):
        self._payload = payload
        self.journal_path = journal_path

    @property
    def stamp(self):
        return self._payload.get("stamp", "")

    @property
    def started_at(self):
        return self._payload.get("started_at", "")

    @property
    def note_title(self):
        return self._payload.get("note_title", "")

    @property
    def files(self):
        """The recorded files that actually survived, largest first."""
        existing = [
            path for path in self._payload.get("media", [])
            if isinstance(path, str) and os.path.isfile(path) and os.path.getsize(path) > 1024
        ]
        return sorted(existing, key=os.path.getsize, reverse=True)

    @property
    def is_recoverable(self):
        return bool(self.files)

    def describe(self):
        when = self.started_at.replace("T", " ") or self.stamp
        title = f" — {self.note_title}" if self.note_title else ""
        return f"{when}{title} ({len(self.files)} file(s))"

    def discard(self):
        """Forget this recording without touching the media it left behind."""
        try:
            os.remove(self.journal_path)
        except OSError:
            pass


def interrupted_recordings(recordings_dir=None):
    """Every recording left mid-flight by an earlier run, newest first.

    Journals belonging to this process are skipped: those are recordings
    happening right now, not wreckage.
    """
    directory = recordings_dir or RECORDINGS_DIR
    if not os.path.isdir(directory):
        return []
    found = []
    for name in sorted(os.listdir(directory), reverse=True):
        if not name.endswith(JOURNAL_SUFFIX):
            continue
        journal_path = os.path.join(directory, name)
        payload = _read(journal_path)
        if payload is None or payload.get("pid") == os.getpid():
            continue
        recording = InterruptedRecording(payload, journal_path)
        if recording.is_recoverable:
            found.append(recording)
    return found


def _read(path):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError):
        return None
    return payload if isinstance(payload, dict) else None
