"""Shared filesystem locations — everything lives next to main.py."""

import os
import shutil

APP_DIR = os.path.dirname(os.path.abspath(__file__))
RECORDINGS_DIR = os.path.join(APP_DIR, "recordings")


def ensure_recordings_dir():
    os.makedirs(RECORDINGS_DIR, exist_ok=True)


def free_recording_space_bytes():
    """Room left on the drive that holds the recordings, or None if unknown."""
    ensure_recordings_dir()
    try:
        return shutil.disk_usage(RECORDINGS_DIR).free
    except OSError:
        return None
