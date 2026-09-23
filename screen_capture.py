"""Primary-monitor screen capture to MP4."""

import os
import threading
import time
from datetime import datetime

from paths import RECORDINGS_DIR, ensure_recordings_dir
from video_encoders import create_frame_encoder

# The most frames one slow iteration may back-fill. Bounds the work done after
# a long stall (a locked screen, a sleeping laptop) while still letting the
# clock catch up over the following iterations.
MAX_CATCHUP_SECONDS = 5
# Below this a file holds only container headers and no watchable picture.
MINIMUM_USABLE_BYTES = 4096


def screen_deps_available():
    try:
        import cv2  # noqa: F401
        import mss  # noqa: F401
        import numpy  # noqa: F401
        return True
    except ImportError:
        return False


class ScreenVideoRecorder:
    """Captures the primary monitor to an MP4 file on a background thread.

    The file must stay in step with wall-clock time or it cannot be muxed with
    the audio: the container declares a fixed frame rate, so a capture that
    quietly falls behind produces a video *shorter* than the meeting, and the
    tail of the audio no longer has any video to sit against. Frames are
    therefore scheduled against a fixed start anchor, and a slot that was
    missed is back-filled with the frame that was actually grabbed.
    """

    def __init__(self, fps=8, max_width=1280):
        self.fps = fps
        self.max_width = max_width
        self._recording = False
        self._thread = None
        self._path = None
        self._error = None
        self._codec_name = None
        self._fragmented = False
        self._frames_written = 0
        self._dropped_slots = 0
        self._started_at = None

    @property
    def error(self):
        return self._error

    @property
    def codec_name(self):
        return self._codec_name

    @property
    def is_fragmented(self):
        """True while the part-written file would still play after a crash."""
        return self._fragmented

    @property
    def frames_written(self):
        return self._frames_written

    @property
    def back_filled_frames(self):
        """Frames duplicated to hold sync because capture could not keep up."""
        return self._dropped_slots

    @property
    def is_capturing(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self, stamp=None):
        if self._recording:
            return
        if not screen_deps_available():
            raise RuntimeError(
                "Screen recording packages are not installed.\n\n"
                "Run: pip install opencv-python mss"
            )
        ensure_recordings_dir()
        stamp = stamp or datetime.now().strftime("%Y%m%d_%H%M%S")
        self._path = os.path.join(RECORDINGS_DIR, f"meeting_{stamp}.mp4")
        self._error = None
        self._frames_written = 0
        self._dropped_slots = 0
        self._started_at = None
        self._recording = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self, timeout=120):
        """Stop and finalize. Returns the path, or None if nothing usable exists.

        The wait is generous because closing the encoder means flushing an
        entire meeting's video: returning early would hand `media_muxer` a file
        that is still being written, which is the one case that returns None
        despite a file existing.

        A capture that failed part-way still returns its file. Forty minutes of
        video is worth keeping even though the last twenty are missing; the
        error is reported separately rather than by throwing the file away.
        """
        self._recording = False
        if self._thread:
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                self._error = (
                    "The screen recorder did not finish writing in time; the video "
                    "file was left as-is so nothing overwrites it."
                )
                return None
            self._thread = None
        return self._path if self._has_usable_file() else None

    def _has_usable_file(self):
        return bool(
            self._path
            and os.path.isfile(self._path)
            and os.path.getsize(self._path) > MINIMUM_USABLE_BYTES
        )

    def _capture_loop(self):
        import mss

        encoder = None
        out_size = None
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]
                interval = 1.0 / max(self.fps, 1)
                self._started_at = time.perf_counter()

                while self._recording:
                    due_at = self._started_at + self._frames_written * interval
                    now = time.perf_counter()
                    if now < due_at:
                        time.sleep(min(0.01, due_at - now))
                        continue

                    frame = self._grab_frame(sct, monitor)
                    if encoder is None:
                        encoder, out_size, frame = self._open_encoder(frame)
                    else:
                        frame = self._conform(frame, out_size)

                    self._write_due_frames(encoder, frame, now, interval)
        except Exception as exc:
            self._error = str(exc) or exc.__class__.__name__
            self._recording = False
        finally:
            if encoder is not None:
                encoder.close()

    def _grab_frame(self, sct, monitor):
        import cv2
        import numpy as np

        shot = np.array(sct.grab(monitor))
        return self._scale(cv2.cvtColor(shot, cv2.COLOR_BGRA2BGR))

    def _open_encoder(self, frame):
        h, w = frame.shape[:2]
        w -= w % 2
        h -= h % 2
        out_size = (w, h)
        frame = frame[:h, :w]
        encoder = create_frame_encoder(self._path, self.fps, out_size)
        self._codec_name = encoder.codec_name
        self._fragmented = encoder.is_fragmented
        return encoder, out_size, frame

    @staticmethod
    def _conform(frame, out_size):
        import cv2

        w, h = out_size
        if frame.shape[1] != w or frame.shape[0] != h:
            return cv2.resize(frame, (w, h))
        return frame

    def _write_due_frames(self, encoder, frame, now, interval):
        """Write this frame into every slot that has come due since the last one."""
        elapsed_slots = int((now - self._started_at) / interval) + 1
        missing = elapsed_slots - self._frames_written
        catchup_limit = max(1, int(self.fps * MAX_CATCHUP_SECONDS))
        count = max(1, min(missing, catchup_limit))
        for _ in range(count):
            encoder.write(frame)
        self._frames_written += count
        self._dropped_slots += count - 1

    def _scale(self, frame):
        import cv2

        h, w = frame.shape[:2]
        if w <= self.max_width:
            return frame
        scale = self.max_width / float(w)
        new_w = int(w * scale)
        new_h = int(h * scale)
        new_w -= new_w % 2
        new_h -= new_h % 2
        return cv2.resize(frame, (new_w, new_h))
