"""Mono WAV file output, one-shot and streaming.

The streaming writer exists so a long meeting is never held only in memory:
blocks land on disk as they arrive, and the RIFF size fields are refreshed
periodically, so a crash or power cut leaves a file that still plays up to the
last few seconds instead of nothing at all.
"""

import os
import struct

from audio.track_mixer import to_pcm16

SAMPLE_WIDTH_BYTES = 2
HEADER_BYTES = 44
PCM_FORMAT = 1
# How often the RIFF sizes are rewritten and flushed to the platter. Small
# enough that a crash costs seconds, large enough not to thrash the disk.
HEADER_REFRESH_SECONDS = 5.0


def mono_header(sample_rate, data_bytes=0):
    """The 44-byte RIFF/WAVE header for a mono PCM16 stream."""
    byte_rate = sample_rate * SAMPLE_WIDTH_BYTES
    return struct.pack(
        "<4sI4s4sIHHIIHH4sI",
        b"RIFF", 36 + data_bytes, b"WAVE",
        b"fmt ", 16, PCM_FORMAT, 1, sample_rate,
        byte_rate, SAMPLE_WIDTH_BYTES, SAMPLE_WIDTH_BYTES * 8,
        b"data", data_bytes,
    )


def write_mono_wav(path, track, sample_rate):
    """Write a float32 mono track to `path`. Returns the path, or None if empty."""
    if track is None or not len(track):
        return None
    payload = to_pcm16(track).tobytes()
    with open(path, "wb") as handle:
        handle.write(mono_header(sample_rate, len(payload)))
        handle.write(payload)
    return path


def repair_wav_header(path):
    """Point a part-written WAV's sizes at everything actually on disk.

    The streaming writer only refreshes its header every few seconds, so a file
    left behind by a crash under-reports its own length. The samples are there;
    this makes players and decoders see them.
    """
    try:
        total = os.path.getsize(path)
    except OSError:
        return None
    data_bytes = total - HEADER_BYTES
    if data_bytes <= 0:
        return None
    try:
        with open(path, "r+b") as handle:
            handle.seek(4)
            handle.write(struct.pack("<I", 36 + data_bytes))
            handle.seek(40)
            handle.write(struct.pack("<I", data_bytes))
    except OSError:
        return None
    return path


class StreamingWavWriter:
    """Appends mono float32 blocks to a WAV file as they are captured.

    Safe to call from a capture thread; `write` is the only hot path and does
    no allocation beyond the PCM conversion.
    """

    def __init__(self, path, sample_rate, refresh_seconds=HEADER_REFRESH_SECONDS):
        self.path = path
        self.sample_rate = sample_rate
        self._refresh_seconds = refresh_seconds
        self._handle = open(path, "wb")
        self._handle.write(mono_header(sample_rate))
        self._data_bytes = 0
        self._bytes_at_last_refresh = 0

    @property
    def frames_written(self):
        return self._data_bytes // SAMPLE_WIDTH_BYTES

    @property
    def seconds_written(self):
        return self.frames_written / float(self.sample_rate or 1)

    @property
    def is_open(self):
        return self._handle is not None

    def write(self, track):
        """Append one float32 mono block."""
        if self._handle is None or track is None or not len(track):
            return
        payload = to_pcm16(track).tobytes()
        self._handle.write(payload)
        self._data_bytes += len(payload)
        self._refresh_header_if_due()

    def close(self):
        """Finalize the sizes and close. Returns the path, or None if silent."""
        if self._handle is None:
            return self.path if self._data_bytes else None
        try:
            self._rewrite_sizes()
        finally:
            self._handle.close()
            self._handle = None
        return self.path if self._data_bytes else None

    def _refresh_header_if_due(self):
        interval_bytes = int(self._refresh_seconds * self.sample_rate * SAMPLE_WIDTH_BYTES)
        if self._data_bytes - self._bytes_at_last_refresh < interval_bytes:
            return
        self._bytes_at_last_refresh = self._data_bytes
        position = self._handle.tell()
        try:
            self._rewrite_sizes()
            self._handle.flush()
            os.fsync(self._handle.fileno())
        except OSError:
            pass
        finally:
            self._handle.seek(position)

    def _rewrite_sizes(self):
        """Point the RIFF and data lengths at what has actually been written."""
        self._handle.seek(4)
        self._handle.write(struct.pack("<I", 36 + self._data_bytes))
        self._handle.seek(40)
        self._handle.write(struct.pack("<I", self._data_bytes))
        self._handle.seek(0, os.SEEK_END)
