"""Frame encoders that turn BGR frames into a playable MP4 file.

Windows Media Player and the "Films & TV" app cannot decode MPEG-4 Part 2
(`mp4v`), so H.264 is preferred and `mp4v` is only a last resort.

The H.264 encoder writes a fragmented MP4 while recording. A normal MP4 only
becomes playable when its index is written at the end, so a crash mid-meeting
would leave an hour of unopenable video; a fragmented one plays up to the last
complete fragment no matter how the process died. `media_muxer` rewrites it
into an ordinary MP4 when the recording finishes.
"""

import os
import subprocess
from abc import ABC, abstractmethod

CREATE_NO_WINDOW = 0x08000000

# Seconds between keyframes while recording. Each keyframe starts a new MP4
# fragment, so this is also the most video a hard crash can cost.
KEYFRAME_SECONDS = 4


class FrameEncoder(ABC):
    """Writes fixed-size BGR frames to a video file."""

    def __init__(self, path, fps, size):
        self.path = path
        self.fps = float(fps)
        self.width, self.height = size

    @property
    @abstractmethod
    def codec_name(self):
        ...

    @property
    def is_fragmented(self):
        """True when the part-written file is already playable after a crash."""
        return False

    @abstractmethod
    def write(self, frame):
        ...

    @abstractmethod
    def close(self):
        ...


class H264FfmpegEncoder(FrameEncoder):
    """Pipes raw frames into the ffmpeg binary bundled with imageio-ffmpeg."""

    @staticmethod
    def ffmpeg_executable():
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()

    @staticmethod
    def is_available():
        try:
            return os.path.isfile(H264FfmpegEncoder.ffmpeg_executable())
        except Exception:
            return False

    def __init__(self, path, fps, size):
        super().__init__(path, fps, size)
        self._process = subprocess.Popen(
            self._build_command(),
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW,
        )

    @property
    def codec_name(self):
        return "h264"

    def _build_command(self):
        return [
            self.ffmpeg_executable(),
            "-y",
            "-loglevel", "error",
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-s", f"{self.width}x{self.height}",
            "-r", f"{self.fps:g}",
            "-i", "-",
            "-an",
            "-c:v", "libx264",
            "-preset", "veryfast",
            "-crf", "26",
            "-g", str(max(1, int(self.fps * KEYFRAME_SECONDS))),
            "-pix_fmt", "yuv420p",
            "-movflags", "frag_keyframe+empty_moov+default_base_moof",
            self.path,
        ]

    @property
    def is_fragmented(self):
        return True

    def write(self, frame):
        import numpy as np

        if self._process is None:
            raise RuntimeError("The video encoder has already been closed.")
        self._process.stdin.write(np.ascontiguousarray(frame).tobytes())

    def close(self):
        if self._process is None:
            return
        try:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.wait(timeout=30)
        except Exception:
            self._process.kill()
        finally:
            self._process = None


class Mp4vOpenCvEncoder(FrameEncoder):
    """Fallback encoder; the result needs VLC or a codec pack on Windows."""

    def __init__(self, path, fps, size):
        super().__init__(path, fps, size)
        import cv2

        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        self._writer = cv2.VideoWriter(path, fourcc, self.fps, (self.width, self.height))
        if not self._writer.isOpened():
            raise RuntimeError("Could not open video writer (mp4v).")

    @property
    def codec_name(self):
        return "mp4v"

    @property
    def is_fragmented(self):
        return False

    def write(self, frame):
        self._writer.write(frame)

    def close(self):
        if self._writer is not None:
            self._writer.release()
            self._writer = None


def create_frame_encoder(path, fps, size):
    """Return the best available encoder for `path`, preferring H.264."""
    if H264FfmpegEncoder.is_available():
        try:
            return H264FfmpegEncoder(path, fps, size)
        except Exception:
            pass
    return Mp4vOpenCvEncoder(path, fps, size)
