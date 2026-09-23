"""The recording path's guarantees: nothing is held only in memory, nothing is
silently truncated, and a long meeting can always be transcribed.

These cover the failure modes that only show up in a meeting long enough to
hurt — an hour of audio trimmed to the video's length, a file too big for the
transcription API, a crash halfway through — none of which a short manual test
would ever reveal.
"""

import os
import sys
import tempfile
import unittest
import wave

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np  # noqa: E402

import media_muxer  # noqa: E402
import recording_journal  # noqa: E402
from audio.audio_recording_manager import (  # noqa: E402
    MAX_RESTART_ATTEMPTS,
    AudioRecordingManager,
)
from audio.chunked_transcriber import ChunkedTranscriber, PartialTranscriptError  # noqa: E402
from audio.speech_audio import (  # noqa: E402
    MAX_UPLOAD_BYTES,
    SpeechAudioError,
    _is_already_compact,
    _verified_original,
)
from audio.wav_mixdown import mix_wav_files, track_is_silent  # noqa: E402
from audio.wav_writer import StreamingWavWriter, repair_wav_header  # noqa: E402
from recording_journal import RecordingJournal, interrupted_recordings  # noqa: E402
from screen_capture import ScreenVideoRecorder  # noqa: E402

SAMPLE_RATE = 16000


def tone(seconds, amplitude=0.5, rate=SAMPLE_RATE):
    samples = np.arange(int(seconds * rate))
    return (amplitude * np.sin(samples / 20.0)).astype("float32")


def wav_seconds(path):
    with wave.open(path, "rb") as handle:
        return handle.getnframes() / float(handle.getframerate())


class TempDirTestCase(unittest.TestCase):
    def setUp(self):
        self._tempdir = tempfile.TemporaryDirectory()
        self.directory = self._tempdir.name

    def tearDown(self):
        self._tempdir.cleanup()

    def path(self, name):
        return os.path.join(self.directory, name)


class StreamingWavWriterTests(TempDirTestCase):
    """Audio must be on disk as it is captured, not at the end."""

    def test_audio_is_readable_before_the_writer_is_closed(self):
        writer = StreamingWavWriter(self.path("live.wav"), SAMPLE_RATE, refresh_seconds=0.1)
        for _ in range(4):
            writer.write(tone(1))

        # Nothing has closed the file — this is what a crash would leave behind.
        repair_wav_header(self.path("live.wav"))
        self.assertAlmostEqual(wav_seconds(self.path("live.wav")), 4.0, places=2)
        writer.close()

    def test_header_repair_recovers_samples_written_since_the_last_refresh(self):
        writer = StreamingWavWriter(self.path("crash.wav"), SAMPLE_RATE, refresh_seconds=60)
        for _ in range(3):
            writer.write(tone(1))
        writer._handle.flush()

        # Without a repair the header still claims the file is empty.
        self.assertEqual(os.path.getsize(self.path("crash.wav")), 44 + 3 * SAMPLE_RATE * 2)
        repair_wav_header(self.path("crash.wav"))
        self.assertAlmostEqual(wav_seconds(self.path("crash.wav")), 3.0, places=2)
        writer.close()

    def test_a_silent_capture_produces_no_file_path(self):
        writer = StreamingWavWriter(self.path("empty.wav"), SAMPLE_RATE)
        self.assertIsNone(writer.close())


class MixdownTests(TempDirTestCase):
    """Mixing must keep every sample of the longest track."""

    def _write(self, name, seconds, amplitude=0.5):
        writer = StreamingWavWriter(self.path(name), SAMPLE_RATE)
        writer.write(tone(seconds, amplitude))
        writer.close()
        return self.path(name)

    def test_the_mix_is_as_long_as_the_longest_track(self):
        mic = self._write("mic.wav", 5)
        system = self._write("sys.wav", 2)
        mixed = mix_wav_files([mic, system], self.path("mix.wav"), SAMPLE_RATE)
        self.assertAlmostEqual(wav_seconds(mixed), 5.0, places=2)

    def test_a_loud_sum_is_scaled_down_rather_than_clipped(self):
        first = self._write("a.wav", 1, amplitude=0.9)
        second = self._write("b.wav", 1, amplitude=0.9)
        mixed = mix_wav_files([first, second], self.path("mix.wav"), SAMPLE_RATE)
        with wave.open(mixed, "rb") as handle:
            data = np.frombuffer(handle.readframes(handle.getnframes()), dtype="<i2")
        self.assertLessEqual(float(np.abs(data).max()) / 32768.0, 0.99)

    def test_a_missing_track_does_not_stop_the_mix(self):
        mic = self._write("mic.wav", 2)
        mixed = mix_wav_files([mic, self.path("gone.wav")], self.path("mix.wav"), SAMPLE_RATE)
        self.assertAlmostEqual(wav_seconds(mixed), 2.0, places=2)

    def test_silence_is_detected_without_loading_the_whole_track(self):
        quiet = self._write("quiet.wav", 3, amplitude=0.0)
        loud = self._write("loud.wav", 3, amplitude=0.5)
        self.assertTrue(track_is_silent(quiet))
        self.assertFalse(track_is_silent(loud))


class MuxingPolicyTests(TempDirTestCase):
    """Regression guard: audio was being trimmed to the video's length.

    The screen capture always runs a little behind the clock, so the video is
    the shorter stream. Asking ffmpeg for `-shortest` therefore cut the end off
    every meeting, and the WAV was deleted immediately afterwards.
    """

    def setUp(self):
        super().setUp()
        self.commands = []
        self._real_run = media_muxer.subprocess.run
        media_muxer.subprocess.run = self._record_command

    def tearDown(self):
        media_muxer.subprocess.run = self._real_run
        super().tearDown()

    def _record_command(self, command, **_kwargs):
        self.commands.append(command)
        with open(command[-1], "wb") as handle:
            handle.write(b"muxed")

        class Result:
            returncode = 0

        return Result()

    def _files(self):
        for name in ("clip.mp4", "clip.wav"):
            with open(self.path(name), "wb") as handle:
                handle.write(bytes(2048))
        return self.path("clip.mp4"), self.path("clip.wav")

    @unittest.skipUnless(media_muxer.muxing_available(), "ffmpeg not installed")
    def test_the_muxer_never_trims_to_the_shorter_stream(self):
        video, audio = self._files()
        self.assertTrue(media_muxer.mux_audio_into_video(video, audio))
        self.assertNotIn("-shortest", self.commands[0])

    @unittest.skipUnless(media_muxer.muxing_available(), "ffmpeg not installed")
    def test_both_streams_are_mapped_so_neither_is_dropped(self):
        video, audio = self._files()
        media_muxer.mux_audio_into_video(video, audio)
        self.assertIn("0:v:0", self.commands[0])
        self.assertIn("1:a:0", self.commands[0])


class FramePacingTests(unittest.TestCase):
    """Video must track wall-clock time or the muxed audio loses its tail."""

    def setUp(self):
        self.recorder = ScreenVideoRecorder(fps=8)
        self.recorder._started_at = 0.0
        self.written = []

    class _Encoder:
        def __init__(self, sink):
            self.sink = sink

        def write(self, frame):
            self.sink.append(frame)

    def test_missed_slots_are_back_filled_so_the_frame_count_matches_the_clock(self):
        encoder = self._Encoder(self.written)
        # One frame arrives on time, the next a full second late.
        self.recorder._write_due_frames(encoder, "a", now=0.0, interval=0.125)
        self.recorder._write_due_frames(encoder, "b", now=1.0, interval=0.125)

        self.assertEqual(self.recorder.frames_written, 9)
        self.assertEqual(len(self.written), 9)
        self.assertEqual(self.recorder.back_filled_frames, 7)

    def test_back_filling_is_capped_so_a_long_stall_cannot_flood_the_encoder(self):
        encoder = self._Encoder(self.written)
        self.recorder._write_due_frames(encoder, "a", now=3600.0, interval=0.125)
        self.assertEqual(len(self.written), 8 * 5)


class PartialVideoTests(TempDirTestCase):
    """A screen capture that dies mid-meeting must not take its footage with it."""

    def setUp(self):
        super().setUp()
        self.recorder = ScreenVideoRecorder()
        self.recorder._path = self.path("meeting.mp4")

    def _write_video(self, size):
        with open(self.recorder._path, "wb") as handle:
            handle.write(bytes(size))

    def test_footage_captured_before_a_failure_is_still_returned(self):
        self._write_video(200000)
        self.recorder._error = "BitBlt failed"
        self.assertEqual(self.recorder.stop(), self.recorder._path)

    def test_a_file_holding_nothing_but_headers_is_not_offered(self):
        self._write_video(100)
        self.assertIsNone(self.recorder.stop())

    def test_a_file_still_being_written_is_never_handed_on(self):
        import threading

        self._write_video(200000)
        release = threading.Event()
        self.recorder._thread = threading.Thread(target=release.wait, daemon=True)
        self.recorder._thread.start()
        try:
            self.assertIsNone(self.recorder.stop(timeout=0.1))
            self.assertIn("did not finish writing", self.recorder.error)
        finally:
            release.set()


class DeviceRecoveryTests(TempDirTestCase):
    """A device dropping out mid-meeting must not end the recording."""

    class _DeadSource:
        """A source whose capture thread is always dead."""

        def __init__(self, label="microphone"):
            self.label = label
            self.error = "device disconnected"
            self.restarts = 0
            self.has_failed = True

        def restart(self):
            self.restarts += 1
            return self.error

    def _manager(self, source):
        manager = AudioRecordingManager(self.directory)
        manager._microphone = source
        manager._capture_system_audio = False
        return manager

    def test_a_failed_device_is_reopened_and_the_user_is_told(self):
        manager = self._manager(self._DeadSource())
        messages = manager.check_health()
        self.assertEqual(len(messages), 1)
        self.assertIn("restarted", messages[0])

    def test_a_device_that_never_comes_back_is_given_up_on_rather_than_retried_forever(self):
        source = self._DeadSource()
        manager = self._manager(source)
        for _ in range(MAX_RESTART_ATTEMPTS + 10):
            manager.check_health()
        self.assertEqual(source.restarts, MAX_RESTART_ATTEMPTS)
        self.assertIn("given up on", manager.warnings[-1])


class ChunkedTranscriberTests(unittest.TestCase):
    """A long transcription must survive a bad connection part-way through."""

    def setUp(self):
        self.calls = []

    def _transcriber(self, behaviour):
        def transcribe(path, prompt=None):
            self.calls.append((path, prompt))
            return behaviour(len(self.calls))

        return ChunkedTranscriber(transcribe, sleep=lambda _s: None)

    def test_a_transient_failure_is_retried_and_the_transcript_completes(self):
        def behaviour(call):
            if call == 2:
                raise RuntimeError("Could not reach the AI service.")
            return f"text{call}"

        result = self._transcriber(behaviour).transcribe_chunks(["a", "b", "c"])
        self.assertEqual(result, "text1\n\ntext3\n\ntext4")

    def test_a_permanent_failure_is_not_retried(self):
        def behaviour(_call):
            raise RuntimeError("The AI service rejected the API key.")

        with self.assertRaises(PartialTranscriptError):
            self._transcriber(behaviour).transcribe_chunks(["a", "b"])
        self.assertEqual(len(self.calls), 1)

    def test_finished_parts_are_kept_when_a_later_part_fails(self):
        def behaviour(call):
            if call >= 2:
                raise RuntimeError("The AI service rejected the API key.")
            return "the first twenty minutes"

        with self.assertRaises(PartialTranscriptError) as caught:
            self._transcriber(behaviour).transcribe_chunks(["a", "b", "c"])
        self.assertEqual(caught.exception.text, "the first twenty minutes")
        self.assertEqual(caught.exception.completed, 1)
        self.assertEqual(caught.exception.total, 3)

    def test_each_part_is_given_the_tail_of_the_previous_one_for_context(self):
        transcriber = self._transcriber(lambda call: f"sentence {call}")
        transcriber.transcribe_chunks(["a", "b"])
        self.assertIsNone(self.calls[0][1])
        self.assertEqual(self.calls[1][1], "sentence 1")

    def test_progress_is_reported_for_a_split_recording(self):
        seen = []
        transcriber = ChunkedTranscriber(
            lambda path, prompt=None: "x", on_progress=lambda d, t: seen.append((d, t))
        )
        transcriber.transcribe_chunks(["a", "b"])
        self.assertEqual(seen, [(0, 2), (1, 2), (2, 2)])


class SpeechAudioTests(TempDirTestCase):
    """Nothing may be sent to the API that the API will refuse."""

    def test_an_oversized_file_is_rejected_with_advice_not_a_failed_upload(self):
        big = self.path("huge.wav")
        with open(big, "wb") as handle:
            handle.write(b"\0" * (MAX_UPLOAD_BYTES + 1))
        with self.assertRaises(SpeechAudioError) as caught:
            _verified_original(big)
        self.assertIn("safe on disk", str(caught.exception))

    def test_a_small_compressed_file_is_uploaded_without_being_re_encoded(self):
        compact = self.path("clip.m4a")
        with open(compact, "wb") as handle:
            handle.write(b"\0" * 1024)
        self.assertTrue(_is_already_compact(compact))

    def test_a_wav_is_never_treated_as_upload_ready(self):
        raw = self.path("clip.wav")
        with open(raw, "wb") as handle:
            handle.write(b"\0" * 1024)
        self.assertFalse(_is_already_compact(raw))


class RecordingJournalTests(TempDirTestCase):
    """A crash must leave a trail pointing at the files it left behind."""

    def setUp(self):
        super().setUp()
        self._previous_dir = recording_journal.RECORDINGS_DIR
        recording_journal.RECORDINGS_DIR = self.directory

    def tearDown(self):
        recording_journal.RECORDINGS_DIR = self._previous_dir
        super().tearDown()

    def _media(self, name, size=4096):
        with open(self.path(name), "wb") as handle:
            handle.write(b"\0" * size)
        return self.path(name)

    def _abandon(self, journal):
        """Rewrite the journal as another process's, i.e. one that died."""
        import json

        with open(journal.path, encoding="utf-8") as handle:
            payload = json.load(handle)
        payload["pid"] = os.getpid() + 1
        with open(journal.path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle)

    def test_a_finished_recording_leaves_nothing_to_recover(self):
        journal = RecordingJournal("20260825_120000", recordings_dir=self.directory)
        journal.open([self._media("meeting.wav")], note_title="Weekly")
        journal.close()
        self.assertEqual(interrupted_recordings(self.directory), [])

    def test_an_interrupted_recording_is_offered_back_with_its_files(self):
        journal = RecordingJournal("20260825_120000", recordings_dir=self.directory)
        journal.open([self._media("meeting.mic.part.wav")], note_title="Weekly")
        self._abandon(journal)

        found = interrupted_recordings(self.directory)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].note_title, "Weekly")
        self.assertEqual(len(found[0].files), 1)

    def test_a_recording_running_right_now_is_not_mistaken_for_wreckage(self):
        journal = RecordingJournal("20260825_120000", recordings_dir=self.directory)
        journal.open([self._media("meeting.mic.part.wav")])
        self.assertEqual(interrupted_recordings(self.directory), [])

    def test_a_journal_whose_files_are_gone_is_not_offered(self):
        journal = RecordingJournal("20260825_120000", recordings_dir=self.directory)
        journal.open([self.path("never_written.wav")])
        self._abandon(journal)
        self.assertEqual(interrupted_recordings(self.directory), [])


if __name__ == "__main__":
    unittest.main()
