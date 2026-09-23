"""Accumulates multiple capture segments for one meeting note session."""

import os

from recorder import MeetingCaptureResult


class MeetingSessionCapture:
    """Holds several recordings made while editing a single meeting note."""

    def __init__(self):
        self._segments = []

    def __len__(self):
        return len(self._segments)

    @property
    def has_media(self):
        return bool(self.list_openable_media())

    def transcript_for(self, index):
        return (self._segments[index].get("transcript") or "").strip()

    def activity_for(self, index):
        return (self._segments[index]["result"].activity_log or "").strip()

    @property
    def combined_transcript(self):
        parts = []
        for i, segment in enumerate(self._segments, start=1):
            text = (segment.get("transcript") or "").strip()
            if not text:
                continue
            if len(self._segments) > 1:
                parts.append(f"--- Recording {i} ---\n{text}")
            else:
                parts.append(text)
        return "\n\n".join(parts)

    @property
    def combined_activity(self):
        parts = []
        for i, segment in enumerate(self._segments, start=1):
            text = (segment["result"].activity_log or "").strip()
            if not text:
                continue
            if len(self._segments) > 1:
                parts.append(f"--- Recording {i} ---\n{text}")
            else:
                parts.append(text)
        return "\n\n".join(parts)

    def add_result(self, result: MeetingCaptureResult):
        """Append a finished capture. Returns the new segment index."""
        self._segments.append({"result": result, "transcript": ""})
        return len(self._segments) - 1

    def set_transcript(self, index, text):
        self._segments[index]["transcript"] = text or ""

    def transcription_path_for(self, index):
        return self._segments[index]["result"].transcription_path

    def list_openable_media(self):
        """Return [{label, path}, ...] for every video/audio file still on disk."""
        items = []
        for i, segment in enumerate(self._segments, start=1):
            result = segment["result"]
            if result.video_path and os.path.isfile(result.video_path):
                kind = "Video + audio" if result.audio_in_video else "Video"
                items.append({
                    "label": f"Recording {i} — {kind}: {os.path.basename(result.video_path)}",
                    "path": result.video_path,
                })
            if result.audio_path and os.path.isfile(result.audio_path):
                items.append({
                    "label": f"Recording {i} — Audio: {os.path.basename(result.audio_path)}",
                    "path": result.audio_path,
                })
        return items

    def describe(self):
        if not self._segments:
            return "No recordings yet"
        n = len(self._segments)
        return f"{n} recording{'s' if n != 1 else ''} in this session"
