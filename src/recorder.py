"""Microphone capture on a background audio stream.

Records mono float32 audio at 16 kHz (Whisper's native rate) directly into
memory, so no temporary WAV file is ever written and there is no fixed
recording duration -- the user starts and stops at will.
"""

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Whisper models expect 16 kHz mono audio


class AudioRecorder:
    """Captures microphone audio without blocking the UI thread.

    Attributes:
        level (float): Most recent RMS input level (roughly 0..1), updated on
            every audio block while recording. Drives the UI level meter.
    """

    def __init__(self):
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self.level = 0.0

    @property
    def is_recording(self) -> bool:
        """bool: True while the microphone stream is open and capturing."""
        return self._stream is not None

    def start(self):
        """Open the default input device and begin capturing.

        No-op if a recording is already in progress.

        Raises:
            sounddevice.PortAudioError: If no input device can be opened.
        """
        if self._stream is not None:
            return
        self._frames = []
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        """PortAudio callback (runs on the audio thread) storing each block.

        Args:
            indata (numpy.ndarray): Incoming audio block, shape (frames, 1).
            frames (int): Number of frames in this block.
            time_info: PortAudio timing info (unused).
            status (sounddevice.CallbackFlags): Over/underflow flags (unused).
        """
        data = indata.copy()
        with self._lock:
            self._frames.append(data)
        self.level = float(np.sqrt(np.mean(np.square(data))))

    def stop(self) -> np.ndarray:
        """Stop capturing and return the recording.

        Returns:
            numpy.ndarray: 1-D float32 array of all captured samples at
            16 kHz. Empty array if nothing was recorded or no recording
            was in progress.
        """
        if self._stream is None:
            return np.zeros(0, dtype=np.float32)
        self._stream.stop()
        self._stream.close()
        self._stream = None
        self.level = 0.0
        with self._lock:
            frames, self._frames = self._frames, []
        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames, axis=0).flatten()
