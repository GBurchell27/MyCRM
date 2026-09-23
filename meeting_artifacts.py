"""Transcript and media belonging to one meeting note.

Merges what was recorded in the current dialog session (held in memory by
`MeetingSessionCapture`) with what an earlier session persisted to the
meetings table, so a reopened note can still show its raw transcript and
play back its recordings.
"""

import json
import os

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov"}


def decode_media_paths(raw):
    """Parse the JSON list stored in meetings.media_paths. Never raises."""
    if not raw:
        return []
    try:
        paths = json.loads(raw)
    except (ValueError, TypeError):
        return []
    return [p for p in paths if isinstance(p, str) and p]


def encode_media_paths(paths):
    return json.dumps(list(paths))


class MeetingArtifacts:
    """Read-only view over a meeting's transcript and playable media files."""

    def __init__(self, session, saved_transcript="", saved_media_json=""):
        self._session = session
        self._saved_transcript = (saved_transcript or "").strip()
        self._saved_media = decode_media_paths(saved_media_json)

    @property
    def transcript_text(self):
        """Saved transcript first, then anything recorded in this session."""
        parts = [self._saved_transcript, self._session.combined_transcript.strip()]
        return "\n\n".join(part for part in parts if part)

    @property
    def has_transcript(self):
        return bool(self.transcript_text)

    def media_items(self):
        """[{label, path}, ...] for every media file that still exists on disk."""
        items = []
        seen = set()
        for path in self._saved_media:
            key = os.path.normcase(os.path.abspath(path))
            if key in seen or not os.path.isfile(path):
                continue
            seen.add(key)
            items.append({"label": self._saved_label(path), "path": path})
        for item in self._session.list_openable_media():
            key = os.path.normcase(os.path.abspath(item["path"]))
            if key in seen:
                continue
            seen.add(key)
            items.append(item)
        return items

    def attach_media(self, path):
        """Link an existing file on disk to this note. False if already linked."""
        key = os.path.normcase(os.path.abspath(path))
        known = {os.path.normcase(os.path.abspath(p)) for p in self.media_paths_for_saving()}
        if key in known:
            return False
        self._saved_media.append(path)
        return True

    def add_transcript_text(self, text, heading=""):
        """Append transcript text produced outside the recording session."""
        text = (text or "").strip()
        if not text:
            return
        block = f"--- {heading} ---\n{text}" if heading else text
        self._saved_transcript = (
            f"{self._saved_transcript}\n\n{block}" if self._saved_transcript else block
        )

    def media_paths_for_saving(self):
        """Every known media path — kept even if the file was moved or deleted."""
        paths = list(self._saved_media)
        seen = {os.path.normcase(os.path.abspath(p)) for p in paths}
        for item in self._session.list_openable_media():
            key = os.path.normcase(os.path.abspath(item["path"]))
            if key not in seen:
                seen.add(key)
                paths.append(item["path"])
        return paths

    @staticmethod
    def _saved_label(path):
        name = os.path.basename(path)
        kind = "Video" if os.path.splitext(path)[1].lower() in VIDEO_EXTENSIONS else "Audio"
        return f"Saved earlier — {kind}: {name}"
