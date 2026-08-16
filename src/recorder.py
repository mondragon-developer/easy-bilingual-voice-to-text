"""Microphone capture on a background audio stream.

Records mono float32 audio at 16 kHz (Whisper's native rate) directly into
memory, so no temporary WAV file is ever written and the user starts and
stops at will.

Audio is held in RAM, which costs 64 KB per second - about 3.8 MB a minute.
That is nothing for dictation and a problem for a forgotten open microphone,
so capture stops on its own at ``MAX_RECORDING_SECONDS``. See ``limit_reached``.
"""

import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000  # Whisper models expect 16 kHz mono audio

#: Longest single recording, in seconds. In-memory audio costs
#: ``SAMPLE_RATE * 4`` bytes per second, and ``stop()`` briefly doubles that
#: while numpy concatenates the blocks, so 30 minutes peaks around 230 MB
#: before Whisper has allocated anything of its own. Past that a forgotten
#: microphone can exhaust a small machine, so capture stops instead.
MAX_RECORDING_SECONDS = 30 * 60
MAX_RECORDING_SAMPLES = SAMPLE_RATE * MAX_RECORDING_SECONDS


class AudioRecorder:
    """Captures microphone audio without blocking the UI thread.

    Attributes:
        level (float): Most recent RMS input level (roughly 0..1), updated on
            every audio block while recording. Drives the UI level meter.
        limit_reached (bool): True once the recording hit ``max_samples`` and
            further audio was dropped. The UI polls this and stops for the
            user, so what they get back is the capped audio rather than a
            silent truncation.
    """

    def __init__(self, max_samples: int = MAX_RECORDING_SAMPLES):
        """
        Args:
            max_samples: Longest recording to keep, in samples. Audio arriving
                after this is discarded and ``limit_reached`` is set.
        """
        self._frames = []
        self._stream = None
        self._lock = threading.Lock()
        self._samples = 0
        self._max_samples = max_samples
        self.level = 0.0
        self.limit_reached = False

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
        self._samples = 0
        self.limit_reached = False
        self._stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            callback=self._callback,
        )
        self._stream.start()

    def _callback(self, indata, frames, time_info, status):
        """PortAudio callback (runs on the audio thread) storing each block.

        Blocks arriving after the sample cap are dropped rather than stored,
        so memory stays bounded even if the UI is slow to notice the limit.

        Args:
            indata (numpy.ndarray): Incoming audio block, shape (frames, 1).
            frames (int): Number of frames in this block.
            time_info: PortAudio timing info (unused).
            status (sounddevice.CallbackFlags): Over/underflow flags (unused).
        """
        data = indata.copy()
        with self._lock:
            if self._samples >= self._max_samples:
                self.limit_reached = True
                return
            room = self._max_samples - self._samples
            if data.shape[0] > room:
                data = data[:room]
                self.limit_reached = True
            self._frames.append(data)
            self._samples += data.shape[0]
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
            self._samples = 0
        if not frames:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(frames, axis=0).flatten()
