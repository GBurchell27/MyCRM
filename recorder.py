"""Mic, system audio, screen video, and Windows activity logging for meetings.

Built so a long meeting cannot quietly lose material. Audio and video stream to
disk throughout rather than being held in memory, a journal marks the capture
as in-flight so a crash leaves something recoverable, devices that drop out are
reopened while the meeting is still running, and the raw audio is kept in a
compact form even after it has been folded into the MP4.
"""

import os
import threading
import time
from datetime import datetime

from audio.audio_archive import archive_audio
from audio.audio_recording_manager import AudioRecordingManager
from media_muxer import finalize_video, mux_audio_into_video
from paths import RECORDINGS_DIR, ensure_recordings_dir, free_recording_space_bytes
from recording_journal import RecordingJournal
from screen_capture import ScreenVideoRecorder, screen_deps_available

ACTIVITY_POLL_SECONDS = 1.5
# Refuse to start below this, and warn below the comfortable mark. Screen video
# runs at roughly 250 MB an hour, with the audio adding another 130 MB.
MINIMUM_FREE_BYTES = 1024 ** 3
COMFORTABLE_FREE_BYTES = 5 * 1024 ** 3
BYTES_PER_RECORDED_HOUR = 400 * 1024 ** 2


class MeetingCaptureResult:
    """The files and log a finished recording produced."""

    def __init__(self, audio_path=None, video_path=None, activity_log="", audio_in_video=False):
        self.audio_path = audio_path
        self.video_path = video_path
        self.activity_log = activity_log
        self.audio_in_video = audio_in_video

    @property
    def transcription_path(self):
        """The file holding the meeting audio, whether standalone or muxed."""
        if self.audio_path:
            return self.audio_path
        return self.video_path if self.audio_in_video else None

    @property
    def has_media(self):
        return bool(self.audio_path or self.video_path)


def recording_deps_available():
    try:
        import numpy  # noqa: F401
        return AudioRecordingManager.microphone_available()
    except ImportError:
        return False


def system_audio_available():
    return AudioRecordingManager.system_audio_available()


def get_active_window_title():
    """Return the foreground window title on Windows, else empty string."""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return buf.value.strip()
    except Exception:
        return ""


class MeetingRecorder:
    """Records microphone + system audio, optional screen video, and window titles."""

    def __init__(self, sample_rate=16000):
        self.sample_rate = sample_rate
        self._recording = False
        self._activity = []
        self._activity_thread = None
        self._lock = threading.Lock()
        self._last_title = ""
        self._stamp = ""
        self._started_at = None
        self._include_video = False
        self._screen = ScreenVideoRecorder()
        self._audio = AudioRecordingManager(RECORDINGS_DIR, sample_rate=sample_rate)
        self._journal = None
        self._unseen_problems = []
        self._video_failure_reported = False

    @property
    def is_recording(self):
        return self._recording

    @property
    def elapsed_seconds(self):
        return time.monotonic() - self._started_at if self._started_at else 0.0

    def take_problems(self):
        """Problems noticed since this was last called, for the UI to surface."""
        with self._lock:
            problems, self._unseen_problems = self._unseen_problems, []
        return problems

    # ------------------------------------------------------------------ start

    def start(self, include_video=True, include_system_audio=True, note_title=""):
        if self._recording:
            return
        self._check_dependencies(include_video)
        self._activity = []
        self._check_disk_space()

        ensure_recordings_dir()
        self._include_video = bool(include_video)
        self._unseen_problems = []
        self._video_failure_reported = False
        self._last_title = ""
        self._stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._started_at = time.monotonic()
        self._recording = True

        if self._include_video:
            self._screen.start(stamp=self._stamp)
        self._audio.start(self._stamp, capture_system_audio=include_system_audio)
        self._open_journal(note_title)

        self._activity_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._activity_thread.start()

    def _check_dependencies(self, include_video):
        if not recording_deps_available():
            raise RuntimeError(
                "Recording packages are not installed.\n\n"
                "Run: pip install sounddevice numpy"
            )
        if include_video and not screen_deps_available():
            raise RuntimeError(
                "Screen recording packages are not installed.\n\n"
                "Run: pip install opencv-python mss\n\n"
                "Or uncheck the screen video option to record audio only."
            )

    def _check_disk_space(self):
        """Stop a long meeting from running the drive dry halfway through."""
        free = free_recording_space_bytes()
        if free is None:
            return
        if free < MINIMUM_FREE_BYTES:
            raise RuntimeError(
                f"Only {free // (1024 ** 2)} MB of disk space is free.\n\n"
                "A meeting recording needs room to grow. Free up some space "
                "before starting, or the recording will be cut short."
            )
        if free < COMFORTABLE_FREE_BYTES:
            hours = max(1, free // BYTES_PER_RECORDED_HOUR)
            self._activity.append(
                f"[disk warning] Only {free // (1024 ** 3)} GB free at the start "
                f"of this recording — roughly {hours} hour(s) of capture."
            )

    def _open_journal(self, note_title):
        self._journal = RecordingJournal(self._stamp)
        media = list(self._audio.part_paths)
        if self._include_video:
            media.append(os.path.join(RECORDINGS_DIR, f"meeting_{self._stamp}.mp4"))
        self._journal.open(media, note_title=note_title)

    # ------------------------------------------------------------------- stop

    def stop(self):
        """Stop recording and finalize the media. Returns a MeetingCaptureResult."""
        if not self._recording:
            return MeetingCaptureResult()
        self._recording = False
        if self._activity_thread:
            self._activity_thread.join(timeout=ACTIVITY_POLL_SECONDS * 3)
            self._activity_thread = None

        wav_path = self._audio.stop(self._stamp)
        video_path = self._stop_video() if self._include_video else None
        audio_path, audio_in_video = self._finish_media(wav_path, video_path)
        self._close_journal()

        with self._lock:
            self._activity.extend(self._audio.warnings)
            activity_text = "\n".join(self._activity)
        return MeetingCaptureResult(
            audio_path=audio_path,
            video_path=video_path,
            activity_log=activity_text,
            audio_in_video=audio_in_video,
        )

    def _finish_media(self, wav_path, video_path):
        """Fold the audio into the MP4, then keep a compact copy of the audio.

        The audio is never deleted on the strength of a successful mux. An MP4
        can be damaged, re-encoded or moved, and a meeting whose only record of
        the conversation lives inside a video file is one bad file away from
        being gone for good.
        """
        audio_in_video = False
        if wav_path and video_path:
            audio_in_video = mux_audio_into_video(video_path, wav_path)
            if not audio_in_video:
                self._note(
                    "[video note] Could not add the audio to the MP4; "
                    "it is still in the matching audio file."
                )
        elif video_path:
            finalize_video(video_path)
        return (archive_audio(wav_path) if wav_path else None), audio_in_video

    def _stop_video(self):
        video_path = self._screen.stop()
        if self._screen.error and not self._video_failure_reported:
            self._note(f"[video error] {self._screen.error}")
        elif video_path and self._screen.codec_name == "mp4v":
            self._note(
                "[video note] Saved as MPEG-4 Part 2; Windows Media Player cannot "
                "open it. Install imageio-ffmpeg for H.264, or play it in VLC."
            )
        if video_path and self._screen.error:
            self._note(
                "[video note] The screen recording stopped early; the part that "
                "was captured before that was kept."
            )
        if video_path and self._screen.back_filled_frames:
            self._note(
                f"[video note] {self._screen.back_filled_frames} frame(s) were "
                "duplicated to keep the picture in step with the audio; the "
                "screen changed faster than it could be captured."
            )
        return video_path

    def _close_journal(self):
        if self._journal is not None:
            self._journal.close()
            self._journal = None

    # ---------------------------------------------------------------- monitor

    def _monitor_loop(self):
        """Log window titles and reopen any audio device that has dropped out."""
        while self._recording:
            self._log_active_window()
            self._check_capture_health()
            time.sleep(ACTIVITY_POLL_SECONDS)

    def _log_active_window(self):
        title = get_active_window_title()
        if title and title != self._last_title:
            self._note(f"{datetime.now().strftime('%H:%M:%S')} — {title}")
            self._last_title = title

    def _check_capture_health(self):
        problems = self._audio.check_health()
        problems.extend(self._video_problem())
        if not problems:
            return
        with self._lock:
            self._activity.extend(problems)
            self._unseen_problems.extend(problems)

    def _video_problem(self):
        """Report screen capture dying once, without disowning the part-written
        file — it still has to be closed and finalized when the user stops."""
        if not self._include_video or self._video_failure_reported:
            return []
        if self._screen.is_capturing or not self._screen.error:
            return []
        self._video_failure_reported = True
        return [
            f"[video error] Screen capture stopped: {self._screen.error}. "
            "Audio is still recording."
        ]

    def _note(self, message):
        with self._lock:
            self._activity.append(message)
