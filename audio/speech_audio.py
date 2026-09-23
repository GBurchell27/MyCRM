"""Prepares meeting audio for the transcription API.

The API takes files up to 25 MB, and raw meeting audio blows past that fast: a
16 kHz WAV is 115 MB an hour, so anything longer than about thirteen minutes
used to be rejected outright when video was switched off. Everything is
therefore re-encoded to Opus first — roughly 10 MB an hour, speech-transparent
at this bitrate — and anything long enough to be worth splitting is cut into
parts so no single upload approaches the limit and a failure only costs the
part that failed.
"""

import contextlib
import os
import re
import shutil
import subprocess
import tempfile

from video_encoders import CREATE_NO_WINDOW, H264FfmpegEncoder

SPEECH_SAMPLE_RATE = "16000"
SPEECH_BITRATE = "24k"
CHUNK_EXTENSION = ".ogg"
# Formats already small enough to upload untouched. Re-encoding one of these
# would only lose quality for no saving.
COMPACT_SUFFIXES = (".ogg", ".m4a", ".mp3", ".webm")

# Well under the API's 25 MB so a bitrate overshoot can't tip a part over.
MAX_UPLOAD_BYTES = 20 * 1024 * 1024
# Recordings longer than this are split; each part covers CHUNK_SECONDS.
SPLIT_ABOVE_SECONDS = 25 * 60
CHUNK_SECONDS = 20 * 60

DURATION_PATTERN = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")


class SpeechAudioError(RuntimeError):
    """The recording could not be made ready for transcription."""


def ffmpeg_available():
    return H264FfmpegEncoder.is_available()


def media_duration_seconds(path):
    """Length of a media file in seconds, or None if it cannot be read."""
    if not ffmpeg_available() or not path or not os.path.isfile(path):
        return None
    result = subprocess.run(
        [H264FfmpegEncoder.ffmpeg_executable(), "-i", path],
        capture_output=True,
        text=True,
        creationflags=CREATE_NO_WINDOW,
    )
    match = DURATION_PATTERN.search(result.stderr or "")
    if not match:
        return None
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


@contextlib.contextmanager
def speech_chunks(media_path):
    """Yield the list of files to transcribe, cleaning up any temporaries.

    One entry for a short recording, several for a long one. Raises
    SpeechAudioError if the file cannot be made small enough to upload.
    """
    if not media_path or not os.path.isfile(media_path):
        raise SpeechAudioError("The recording file is no longer on disk.")
    if not ffmpeg_available():
        yield [_verified_original(media_path)]
        return

    workspace = tempfile.mkdtemp(prefix="mycrm_speech_")
    try:
        yield _build_chunks(media_path, workspace)
    finally:
        shutil.rmtree(workspace, ignore_errors=True)


def _verified_original(media_path):
    """Fall back to uploading the file as-is, if it is small enough to accept."""
    size = os.path.getsize(media_path)
    if size <= MAX_UPLOAD_BYTES:
        return media_path
    raise SpeechAudioError(
        f"This recording is {size // (1024 * 1024)} MB, over the transcription "
        "service's 25 MB limit, and it cannot be compressed because ffmpeg is "
        "not installed.\n\nRun: pip install imageio-ffmpeg\n\n"
        "The recording itself is safe on disk — transcribe it again afterwards."
    )


def _build_chunks(media_path, workspace):
    duration = media_duration_seconds(media_path)
    needs_split = bool(duration and duration > SPLIT_ABOVE_SECONDS)
    if not needs_split and _is_already_compact(media_path):
        return [media_path]
    if needs_split:
        chunks = _encode_segments(media_path, workspace)
    else:
        chunks = _encode_single(media_path, workspace)
    if not chunks:
        raise SpeechAudioError(
            "The recording could not be prepared for transcription — it may be "
            "empty or damaged. The file itself is still on disk."
        )
    _reject_oversized(chunks)
    return chunks


def _is_already_compact(media_path):
    return (
        media_path.lower().endswith(COMPACT_SUFFIXES)
        and os.path.getsize(media_path) <= MAX_UPLOAD_BYTES
    )


def _encode_single(media_path, workspace):
    out_path = os.path.join(workspace, f"speech{CHUNK_EXTENSION}")
    _run_ffmpeg(_speech_command(media_path) + [out_path])
    return [out_path] if _has_content(out_path) else []


def _encode_segments(media_path, workspace):
    pattern = os.path.join(workspace, f"speech_%04d{CHUNK_EXTENSION}")
    _run_ffmpeg(_speech_command(media_path) + [
        "-f", "segment",
        "-segment_time", str(CHUNK_SECONDS),
        "-reset_timestamps", "1",
        pattern,
    ])
    produced = sorted(
        os.path.join(workspace, name)
        for name in os.listdir(workspace)
        if name.startswith("speech_") and name.endswith(CHUNK_EXTENSION)
    )
    return [path for path in produced if _has_content(path)]


def _speech_command(media_path):
    return [
        H264FfmpegEncoder.ffmpeg_executable(),
        "-y",
        "-loglevel", "error",
        "-i", media_path,
        "-vn",
        "-ac", "1",
        "-ar", SPEECH_SAMPLE_RATE,
        "-c:a", "libopus",
        "-b:a", SPEECH_BITRATE,
    ]


def _run_ffmpeg(command):
    try:
        subprocess.run(
            command, check=True, capture_output=True, creationflags=CREATE_NO_WINDOW
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or b"").decode("utf-8", "replace").strip().splitlines()
        raise SpeechAudioError(
            "Could not extract the speech track from this recording"
            + (f" ({detail[-1]})" if detail else "")
            + ". The recording itself is still on disk."
        ) from exc
    except OSError as exc:
        raise SpeechAudioError(f"Could not run ffmpeg: {exc}") from exc


def _reject_oversized(chunks):
    for path in chunks:
        if os.path.getsize(path) > MAX_UPLOAD_BYTES:
            raise SpeechAudioError(
                "Part of this recording is still too large to upload after "
                "compression. The recording is safe on disk; please report this."
            )


def _has_content(path):
    return os.path.isfile(path) and os.path.getsize(path) > 0
