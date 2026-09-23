"""Turns the wreckage of an interrupted recording back into usable files.

What a crash leaves behind is not quite a finished recording: the audio sits in
per-source part-files whose headers stop a few seconds short of the data, and
the video is a fragmented MP4 that plays but does not seek well. This puts both
right — mixing the parts, repairing what the writer never got to finalize — and
hands back files no different from a recording that ended normally.
"""

import os

from audio.audio_archive import archive_audio
from audio.audio_recording_manager import PART_SUFFIX
from audio.wav_mixdown import mix_wav_files
from audio.wav_writer import repair_wav_header
from media_muxer import finalize_video

SAMPLE_RATE = 16000
VIDEO_SUFFIX = ".mp4"


class RecoveredRecording:
    """The files rescued from one interrupted capture."""

    def __init__(self, audio_path=None, video_path=None, notes=()):
        self.audio_path = audio_path
        self.video_path = video_path
        self.notes = list(notes)

    @property
    def paths(self):
        return [path for path in (self.audio_path, self.video_path) if path]

    @property
    def transcription_path(self):
        return self.audio_path or self.video_path

    @property
    def recovered_anything(self):
        return bool(self.paths)


class RecordingRestorer:
    """Rebuilds finished media from the part-files a crash left behind."""

    def __init__(self, sample_rate=SAMPLE_RATE):
        self.sample_rate = sample_rate

    def restore(self, interrupted):
        """Repair and combine `interrupted`'s files. Returns a RecoveredRecording."""
        files = interrupted.files
        notes = []
        audio_path = self._restore_audio(interrupted.stamp, files, notes)
        video_path = self._restore_video(files, notes)
        return RecoveredRecording(audio_path, video_path, notes)

    # ----------------------------------------------------------------- audio

    def _restore_audio(self, stamp, files, notes):
        parts = [path for path in files if path.endswith(PART_SUFFIX)]
        if not parts:
            return self._existing_finished_audio(files)
        for path in parts:
            repair_wav_header(path)

        mixed_path = os.path.join(os.path.dirname(parts[0]), f"meeting_{stamp}.wav")
        try:
            mixed = mix_wav_files(sorted(parts), mixed_path, self.sample_rate)
        except Exception as exc:
            notes.append(f"The audio tracks could not be mixed ({exc}); kept as-is.")
            return max(parts, key=os.path.getsize)
        if not mixed:
            notes.append("The recovered audio was empty.")
            return None

        for path in parts:
            _remove_quietly(path)
        return archive_audio(mixed)

    @staticmethod
    def _existing_finished_audio(files):
        audio = [f for f in files if f.lower().endswith((".wav", ".m4a"))]
        return max(audio, key=os.path.getsize) if audio else None

    # ----------------------------------------------------------------- video

    @staticmethod
    def _restore_video(files, notes):
        videos = [path for path in files if path.lower().endswith(VIDEO_SUFFIX)]
        if not videos:
            return None
        video_path = max(videos, key=os.path.getsize)
        if not finalize_video(video_path):
            notes.append(
                "The video was left in its recording format — it will play, but "
                "may not seek smoothly."
            )
        return video_path


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
