"""Gain and sample-format rules shared by everything that writes audio.

The clipping ceiling lives here rather than in the mixdown so the one-shot and
streaming paths cannot drift apart on how loud a mixed meeting is allowed to be.
"""

CLIP_CEILING = 0.99


def to_pcm16(track):
    """Convert a float32 track in [-1, 1] to int16 PCM samples."""
    import numpy as np

    return np.clip(track * 32767.0, -32768, 32767).astype(np.int16)
