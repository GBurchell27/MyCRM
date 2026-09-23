"""Mixes the captured part-tracks on disk into the meeting's final WAV.

Reads and writes in blocks rather than loading whole tracks, so a three-hour
meeting costs the same memory as a three-minute one. Two passes are made: the
first finds the summed peak, the second writes with the single gain that keeps
it under the clipping ceiling — the same "only quiet it if it would clip" rule
the in-memory mixer used.
"""

import os
import wave

from audio.track_mixer import CLIP_CEILING
from audio.wav_writer import mono_header, SAMPLE_WIDTH_BYTES

BLOCK_FRAMES = 1 << 16
INT16_SCALE = 32768.0


class WavTrack:
    """One readable part-track, opened lazily and read in blocks."""

    def __init__(self, path):
        self.path = path
        self._wave = None

    def __enter__(self):
        self._wave = wave.open(self.path, "rb")
        return self

    def __exit__(self, *_exc):
        if self._wave is not None:
            self._wave.close()
            self._wave = None

    @property
    def frames(self):
        return self._wave.getnframes() if self._wave else 0

    @property
    def sample_rate(self):
        return self._wave.getframerate() if self._wave else 0

    def rewind(self):
        self._wave.rewind()

    def read_block(self, frames):
        """Return the next block as float32 in [-1, 1], or an empty array."""
        import numpy as np

        raw = self._wave.readframes(frames)
        if not raw:
            return np.zeros(0, dtype="float32")
        return np.frombuffer(raw, dtype="<i2").astype("float32") / INT16_SCALE


def track_is_silent(path, threshold=1e-4):
    """True when the file is missing, empty, or never rises above `threshold`."""
    import numpy as np

    if not path or not os.path.isfile(path):
        return True
    try:
        with WavTrack(path) as track:
            while True:
                block = track.read_block(BLOCK_FRAMES)
                if not len(block):
                    return True
                if float(np.abs(block).max()) > threshold:
                    return False
    except (wave.Error, OSError):
        return True


def mix_wav_files(part_paths, out_path, sample_rate):
    """Sum the part tracks into `out_path`. Returns the path, or None if silent.

    Parts of differing length are zero-padded to the longest, matching how the
    sources are expected to drift apart by a block or two at start and stop.
    """
    usable = [p for p in part_paths if p and os.path.isfile(p) and os.path.getsize(p) > 44]
    if not usable:
        return None

    total_frames = _longest(usable)
    if not total_frames:
        return None
    gain = _clip_safe_gain(usable, total_frames)

    with open(out_path, "wb") as handle:
        handle.write(mono_header(sample_rate))
        written = _stream_sum(usable, total_frames, handle, gain)
        _finish_header(handle, written * SAMPLE_WIDTH_BYTES)
    return out_path if written else None


def _longest(paths):
    longest = 0
    for path in paths:
        with WavTrack(path) as track:
            longest = max(longest, track.frames)
    return longest


def _clip_safe_gain(paths, total_frames):
    """The single gain that keeps the summed peak under the ceiling."""
    peak = 0.0
    for block in _summed_blocks(paths, total_frames):
        import numpy as np

        peak = max(peak, float(np.abs(block).max()))
    if peak <= CLIP_CEILING:
        return 1.0
    return CLIP_CEILING / peak


def _stream_sum(paths, total_frames, handle, gain):
    import numpy as np

    written = 0
    for block in _summed_blocks(paths, total_frames):
        scaled = np.clip(block * gain * 32767.0, -32768, 32767).astype(np.int16)
        handle.write(scaled.tobytes())
        written += len(scaled)
    return written


def _summed_blocks(paths, total_frames):
    """Yield successive zero-padded sums of every track, block by block."""
    import numpy as np

    tracks = [WavTrack(path).__enter__() for path in paths]
    try:
        for track in tracks:
            track.rewind()
        remaining = total_frames
        while remaining > 0:
            count = min(BLOCK_FRAMES, remaining)
            mixed = np.zeros(count, dtype="float32")
            for track in tracks:
                block = track.read_block(count)
                if len(block):
                    mixed[: len(block)] += block
            yield mixed
            remaining -= count
    finally:
        for track in tracks:
            track.__exit__(None, None, None)


def _finish_header(handle, data_bytes):
    import struct

    handle.seek(4)
    handle.write(struct.pack("<I", 36 + data_bytes))
    handle.seek(40)
    handle.write(struct.pack("<I", data_bytes))
