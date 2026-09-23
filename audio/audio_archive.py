"""Keeps a compact, playable copy of the meeting's raw audio.

The WAV that comes out of the mixdown is the truth, but at 115 MB an hour it
is not something to keep for every meeting. It is re-encoded to a mono AAC
file — about 14 MB an hour, and playable by Windows without extra codecs — so
the audio survives independently of the MP4 and can always be transcribed
again, however the video turns out.
"""

import os
import subprocess

from video_encoders import CREATE_NO_WINDOW, H264FfmpegEncoder

ARCHIVE_EXTENSION = ".m4a"
ARCHIVE_BITRATE = "32k"
ARCHIVE_SAMPLE_RATE = "16000"


def archiving_available():
    return H264FfmpegEncoder.is_available()


def archive_path_for(wav_path):
    return os.path.splitext(wav_path)[0] + ARCHIVE_EXTENSION


def archive_audio(wav_path):
    """Replace the WAV with a compact AAC copy. Returns the path that now holds
    the audio — the new file on success, the untouched WAV on any failure."""
    if not wav_path or not os.path.isfile(wav_path):
        return wav_path
    if not archiving_available():
        return wav_path

    destination = archive_path_for(wav_path)
    command = [
        H264FfmpegEncoder.ffmpeg_executable(),
        "-y",
        "-loglevel", "error",
        "-i", wav_path,
        "-ac", "1",
        "-ar", ARCHIVE_SAMPLE_RATE,
        "-c:a", "aac",
        "-b:a", ARCHIVE_BITRATE,
        "-movflags", "+faststart",
        destination,
    ]
    try:
        subprocess.run(
            command, check=True, capture_output=True, creationflags=CREATE_NO_WINDOW
        )
        if not os.path.getsize(destination):
            raise OSError("empty archive")
    except (subprocess.CalledProcessError, OSError):
        _remove_quietly(destination)
        return wav_path

    _remove_quietly(wav_path)
    return destination


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
