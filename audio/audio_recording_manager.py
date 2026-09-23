"""Runs the meeting's audio sources together and writes the mixed WAV.

Each source streams to its own part-file on disk while the meeting runs, and
the parts are mixed down only at the end. Nothing is held in memory, so the
recording survives the app dying, and the two raw tracks stay separable right
up to the mixdown.
"""

import os

from audio.sources import MicrophoneSource, SystemAudioSource
from audio.wav_mixdown import mix_wav_files, track_is_silent
from audio.wav_writer import StreamingWavWriter

PART_SUFFIX = ".part.wav"
# A device that has genuinely gone (unplugged for good) would otherwise be
# reopened every few seconds for the rest of the meeting, filling the log and
# the status line with the same message. Try a handful of times, then say so
# once and leave the remaining sources to carry the recording.
MAX_RESTART_ATTEMPTS = 5


class AudioRecordingManager:
    """Captures microphone plus optional system playback into one WAV file."""

    def __init__(self, recordings_dir, sample_rate=16000):
        self.recordings_dir = recordings_dir
        self.sample_rate = sample_rate
        self._microphone = MicrophoneSource(sample_rate=sample_rate)
        self._system_audio = SystemAudioSource(sample_rate=sample_rate)
        self._capture_system_audio = False
        self._warnings = []
        self._writers = {}
        self._stamp = ""
        self._abandoned = set()

    @staticmethod
    def microphone_available():
        return MicrophoneSource.is_available()

    @staticmethod
    def system_audio_available():
        return SystemAudioSource.is_available()

    @property
    def warnings(self):
        return list(self._warnings)

    @property
    def part_paths(self):
        """The on-disk part-files for this capture, in mix order."""
        return [writer.path for writer in self._writers.values()]

    @property
    def seconds_captured(self):
        """How much microphone audio has reached the disk so far."""
        writer = self._writers.get(self._microphone)
        return writer.seconds_written if writer else 0.0

    @property
    def _active_sources(self):
        sources = [self._microphone]
        if self._capture_system_audio:
            sources.append(self._system_audio)
        return sources

    def start(self, stamp, capture_system_audio=True):
        self._warnings = []
        self._writers = {}
        self._abandoned = set()
        self._stamp = stamp
        self._capture_system_audio = bool(capture_system_audio) and self.system_audio_available()
        if capture_system_audio and not self._capture_system_audio:
            self._warnings.append(
                "[audio note] System audio was not captured; install the 'soundcard' "
                "package to record what your speakers play."
            )
        os.makedirs(self.recordings_dir, exist_ok=True)
        for source, tag in ((self._microphone, "mic"), (self._system_audio, "system")):
            if source not in self._active_sources:
                continue
            writer = StreamingWavWriter(self._part_path(tag), self.sample_rate)
            self._writers[source] = writer
            source.start(sink=writer)

    def check_health(self):
        """Reopen any source that has died. Returns messages about what happened.

        Called on a timer while recording so a device that drops out is noticed
        within seconds instead of at the end of the meeting.
        """
        messages = []
        for source in self._active_sources:
            if not source.has_failed or source in self._abandoned:
                continue
            messages.append(self._recover(source))
        self._warnings.extend(messages)
        return messages

    def _recover(self, source):
        if source.restarts >= MAX_RESTART_ATTEMPTS:
            self._abandoned.add(source)
            return (
                f"[audio error] The {source.label} kept failing and has been given "
                f"up on after {source.restarts} attempts ({source.error}). The rest "
                "of the recording is continuing."
            )
        reason = source.restart()
        return (
            f"[audio recovered] The {source.label} stopped "
            f"({reason or 'unknown reason'}) and was restarted — "
            "a moment of audio may be missing."
        )

    def stop(self, stamp=None):
        """Stop every source and write the mix. Returns the WAV path or None."""
        stamp = stamp or self._stamp
        for source in self._active_sources:
            source.stop()
        part_paths = self._close_writers()
        self._collect_warnings(part_paths)

        mixed_path = os.path.join(self.recordings_dir, f"meeting_{stamp}.wav")
        try:
            result = mix_wav_files(part_paths, mixed_path, self.sample_rate)
        except Exception as exc:
            self._warnings.append(
                f"[audio error] Could not mix the recorded tracks ({exc}); "
                "the separate tracks were kept instead."
            )
            return self._keep_largest_part(part_paths)
        self._remove_parts(part_paths)
        return result

    # ---------------------------------------------------------------- helpers

    def _part_path(self, tag):
        return os.path.join(self.recordings_dir, f"meeting_{self._stamp}.{tag}{PART_SUFFIX}")

    def _close_writers(self):
        paths = []
        for writer in self._writers.values():
            writer.close()
            paths.append(writer.path)
        self._writers = {}
        return paths

    def _collect_warnings(self, part_paths):
        for source in self._active_sources:
            if source.error:
                self._warnings.append(f"[audio error] {source.label}: {source.error}")
            if source.restarts:
                self._warnings.append(
                    f"[audio note] The {source.label} was reopened "
                    f"{source.restarts} time(s) during this recording."
                )
        if self._capture_system_audio and self._system_part_is_silent(part_paths):
            self._warnings.append(
                "[audio note] System audio track was silent — check that the meeting "
                "played through the default playback device."
            )

    def _system_part_is_silent(self, part_paths):
        system = [p for p in part_paths if p.endswith(f".system{PART_SUFFIX}")]
        return bool(system) and track_is_silent(system[0])

    def _keep_largest_part(self, part_paths):
        """Fall back to the biggest raw track so a failed mix still leaves audio."""
        existing = [p for p in part_paths if os.path.isfile(p) and os.path.getsize(p) > 44]
        if not existing:
            return None
        return max(existing, key=os.path.getsize)

    @staticmethod
    def _remove_parts(part_paths):
        for path in part_paths:
            try:
                os.remove(path)
            except OSError:
                pass
