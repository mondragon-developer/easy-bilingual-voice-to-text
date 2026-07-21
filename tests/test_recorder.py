"""Unit tests for src.recorder using a fake sounddevice stream."""

from unittest.mock import patch

import numpy as np

from src.recorder import SAMPLE_RATE, AudioRecorder


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
