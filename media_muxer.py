"""Turns the captured screen video and its audio into one finished MP4.

Two things matter for a long meeting. The audio must not be trimmed to the
video's length — `-shortest` used to do exactly that, and since the WAV was
deleted straight afterwards, the last minutes of the meeting were gone for
good. And the fragmented file the recorder writes for crash-safety must be
rewritten into an ordinary MP4 at the end, so it seeks and streams normally.
"""

import os
import subprocess

from video_encoders import CREATE_NO_WINDOW, H264FfmpegEncoder

AUDIO_BITRATE = "128k"


class MuxError(RuntimeError):
    """ffmpeg refused to produce the output file."""


def muxing_available():
    return H264FfmpegEncoder.is_available()


def mux_audio_into_video(video_path, audio_path):
    """Write `audio_path` into `video_path` in place. Returns True on success.

    The video stream is copied rather than re-encoded, so this stays fast even
    for long meetings. Both streams are kept whole: if the capture drifted by a
    second the video simply ends slightly before the audio does.
    """
    if not (video_path and audio_path):
        return False
    if not (os.path.isfile(video_path) and os.path.isfile(audio_path)):
        return False
    return _rewrite_in_place(video_path, [
        "-i", video_path,
        "-i", audio_path,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", AUDIO_BITRATE,
    ])


def finalize_video(video_path):
    """Rewrite a fragmented capture as an ordinary seekable MP4."""
    if not (video_path and os.path.isfile(video_path)):
        return False
    return _rewrite_in_place(video_path, ["-i", video_path, "-c", "copy"])


def _rewrite_in_place(video_path, arguments):
    if not muxing_available():
        return False
    temp_path = f"{video_path}.muxed.tmp.mp4"
    command = [
        H264FfmpegEncoder.ffmpeg_executable(),
        "-y",
        "-loglevel", "error",
        *arguments,
        "-movflags", "+faststart",
        temp_path,
    ]
    try:
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            creationflags=CREATE_NO_WINDOW,
        )
        if not os.path.getsize(temp_path):
            raise MuxError("ffmpeg produced an empty file")
        os.replace(temp_path, video_path)
        return True
    except (subprocess.CalledProcessError, MuxError, OSError):
        _remove_quietly(temp_path)
        return False


def _remove_quietly(path):
    try:
        os.remove(path)
    except OSError:
        pass
