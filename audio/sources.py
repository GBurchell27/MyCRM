"""Background audio sources that each stream one mono track to a sink.

Blocks are handed straight to a sink (normally a `StreamingWavWriter`) rather
than piling up in a list, so an hour-long meeting costs no more memory than a
one-minute one and survives the process dying.

A source that fails mid-meeting — a headset that drops off Bluetooth, a device
swapped in Windows — does not end the recording. `restart()` reopens the device
and keeps appending to the same sink, and the gap is reported rather than
silently shortening the track.
"""

import threading
import time
from abc import ABC, abstractmethod


class AudioSource(ABC):
    """Captures mono audio on a background thread until stopped."""

    def __init__(self, sample_rate=16000, blocksize=1024):
        self.sample_rate = sample_rate
        self.blocksize = blocksize
        self._running = False
        self._thread = None
        self._sink = None
        self._lock = threading.Lock()
        self._error = None
        self._restarts = 0

    @property
    @abstractmethod
    def label(self):
        ...

    @property
    def error(self):
        return self._error

    @property
    def restarts(self):
        """How many times the device had to be reopened during this capture."""
        return self._restarts

    @property
    def is_capturing(self):
        return bool(self._thread and self._thread.is_alive())

    @property
    def has_failed(self):
        """True once the capture thread has died while it was meant to run."""
        return bool(self._running and not self.is_capturing)

    @abstractmethod
    def _capture(self):
        """Write mono float32 blocks to the sink while `self._running`."""

    def start(self, sink=None):
        if self._running:
            return
        self._running = True
        self._error = None
        self._restarts = 0
        self._sink = sink
        self._spawn()

    def restart(self):
        """Reopen the device after a failure, keeping the same sink.

        Returns the error that ended the previous attempt, or None if the
        source was healthy and nothing needed doing.
        """
        if not self._running or self.is_capturing:
            return None
        previous_error = self._error
        self._error = None
        self._restarts += 1
        self._spawn()
        return previous_error

    def stop(self, timeout=10):
        """Stop capturing. Returns the number of frames written to the sink."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=timeout)
            self._thread = None
        return self._sink.frames_written if self._sink else 0

    def _spawn(self):
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def _run(self):
        try:
            self._capture()
        except Exception as exc:
            self._error = str(exc) or exc.__class__.__name__

    def _append(self, block):
        import numpy as np

        mono = np.asarray(block, dtype="float32")
        if mono.ndim > 1:
            mono = mono.mean(axis=1)
        with self._lock:
            if self._sink is not None:
                self._sink.write(mono.reshape(-1))


class MicrophoneSource(AudioSource):
    """Default input device, captured through sounddevice."""

    @staticmethod
    def is_available():
        try:
            import sounddevice  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def label(self):
        return "microphone"

    def _capture(self):
        import sounddevice as sd

        def callback(indata, _frames, _time_info, _status):
            if not self._running:
                raise sd.CallbackStop()
            self._append(indata.copy())

        with sd.InputStream(
            samplerate=self.sample_rate,
            channels=1,
            dtype="float32",
            blocksize=self.blocksize,
            callback=callback,
        ):
            while self._running:
                time.sleep(0.05)


class SystemAudioSource(AudioSource):
    """Whatever the speakers are playing, via the WASAPI loopback device."""

    @staticmethod
    def is_available():
        try:
            import soundcard  # noqa: F401
            return True
        except ImportError:
            return False

    @property
    def label(self):
        return "system audio"

    def _loopback_microphone(self):
        import soundcard as sc

        speaker = sc.default_speaker()
        return sc.get_microphone(str(speaker.name), include_loopback=True)

    def _capture(self):
        loopback = self._loopback_microphone()
        with loopback.recorder(
            samplerate=self.sample_rate,
            channels=1,
            blocksize=self.blocksize,
        ) as recorder:
            while self._running:
                self._append(recorder.record(numframes=self.blocksize))
