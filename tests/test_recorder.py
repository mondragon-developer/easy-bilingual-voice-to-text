"""Unit tests for src.recorder using a fake sounddevice stream."""

from unittest.mock import patch

import numpy as np

from src.recorder import (MAX_RECORDING_SAMPLES, MAX_RECORDING_SECONDS,
                          SAMPLE_RATE, AudioRecorder)


class FakeStream:
    """Stands in for sounddevice.InputStream; lets tests feed audio blocks."""

    def __init__(self, samplerate, channels, dtype, callback):
        self.callback = callback
        self.started = False
        self.closed = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        self.closed = True


@patch("src.recorder.sd.InputStream", FakeStream)
class TestAudioRecorder:
    def test_initial_state(self):
        rec = AudioRecorder()
        assert not rec.is_recording
        assert rec.level == 0.0

    def test_start_opens_stream(self):
        rec = AudioRecorder()
        rec.start()
        assert rec.is_recording
        assert rec._stream.started

    def test_start_twice_is_noop(self):
        rec = AudioRecorder()
        rec.start()
        first = rec._stream
        rec.start()
        assert rec._stream is first

    def test_stop_without_start_returns_empty(self):
        rec = AudioRecorder()
        audio = rec.stop()
        assert audio.size == 0
        assert audio.dtype == np.float32

    def test_captured_blocks_are_concatenated(self):
        rec = AudioRecorder()
        rec.start()
        block1 = np.ones((100, 1), dtype=np.float32) * 0.5
        block2 = np.ones((50, 1), dtype=np.float32) * -0.5
        rec._stream.callback(block1, 100, None, None)
        rec._stream.callback(block2, 50, None, None)
        audio = rec.stop()
        assert audio.shape == (150,)
        assert np.allclose(audio[:100], 0.5)
        assert np.allclose(audio[100:], -0.5)

    def test_level_tracks_input_rms(self):
        rec = AudioRecorder()
        rec.start()
        rec._stream.callback(np.ones((64, 1), dtype=np.float32) * 0.25, 64, None, None)
        assert rec.level == np.float32(0.25)

    def test_stop_resets_state(self):
        rec = AudioRecorder()
        rec.start()
        stream = rec._stream
        rec._stream.callback(np.zeros((10, 1), dtype=np.float32), 10, None, None)
        rec.stop()
        assert not rec.is_recording
        assert rec.level == 0.0
        assert stream.closed
        assert rec.stop().size == 0  # second stop: nothing left

    def test_sample_rate_is_whisper_native(self):
        assert SAMPLE_RATE == 16000


@patch("src.recorder.sd.InputStream", FakeStream)
class TestRecordingLimit:
    """Audio lives in RAM, so an open microphone must not grow forever."""

    def _block(self, n):
        return np.ones((n, 1), dtype=np.float32) * 0.1

    def test_limit_not_flagged_during_normal_use(self):
        rec = AudioRecorder(max_samples=1000)
        rec.start()
        rec._stream.callback(self._block(500), 500, None, None)
        assert not rec.limit_reached

    def test_audio_past_the_cap_is_dropped(self):
        rec = AudioRecorder(max_samples=1000)
        rec.start()
        rec._stream.callback(self._block(800), 800, None, None)
        rec._stream.callback(self._block(800), 800, None, None)
        audio = rec.stop()
        assert audio.size == 1000, "must keep exactly the cap, not 1600"
        assert rec.limit_reached

    def test_blocks_arriving_after_the_cap_are_ignored_entirely(self):
        rec = AudioRecorder(max_samples=100)
        rec.start()
        rec._stream.callback(self._block(100), 100, None, None)
        rec._stream.callback(self._block(500), 500, None, None)
        rec._stream.callback(self._block(500), 500, None, None)
        assert rec.stop().size == 100

    def test_a_partial_block_is_truncated_not_discarded(self):
        rec = AudioRecorder(max_samples=120)
        rec.start()
        rec._stream.callback(self._block(100), 100, None, None)
        rec._stream.callback(self._block(100), 100, None, None)
        assert rec.stop().size == 120

    def test_the_flag_clears_on_the_next_recording(self):
        rec = AudioRecorder(max_samples=100)
        rec.start()
        rec._stream.callback(self._block(200), 200, None, None)
        rec.stop()
        assert rec.limit_reached
        rec.start()
        assert not rec.limit_reached

    def test_a_second_recording_starts_from_an_empty_budget(self):
        rec = AudioRecorder(max_samples=100)
        rec.start()
        rec._stream.callback(self._block(100), 100, None, None)
        rec.stop()
        rec.start()
        rec._stream.callback(self._block(60), 60, None, None)
        assert rec.stop().size == 60

    def test_default_cap_matches_the_documented_minutes(self):
        assert MAX_RECORDING_SAMPLES == SAMPLE_RATE * MAX_RECORDING_SECONDS
        assert MAX_RECORDING_SECONDS == 30 * 60
