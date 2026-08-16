"""Speech-to-text via faster-whisper with automatic EN/ES language detection.

Loads the model onto the GPU (CUDA / float16) when available and falls back
to CPU (int8) automatically. Whisper's output is already punctuated and
correctly spelled, which is what gives the app its precision.
"""

import os
import re
import sys
import warnings

from .languages import normalise

if sys.platform == "darwin":
    # NumPy on macOS links against Apple's Accelerate BLAS, which leaves the
    # CPU's floating-point exception flags set after a matmul even when the
    # result is fine. NumPy reads those flags and reports "divide by zero /
    # overflow / invalid value encountered in matmul" for every mel-spectrogram
    # the feature extractor computes. The transcript is unaffected; the warning
    # is spurious, so keep it off the console instead of alarming the user.
    warnings.filterwarnings("ignore", category=RuntimeWarning,
                            module=r"faster_whisper\.feature_extractor")

#: Model used when a CUDA GPU is available (best accuracy).
MODEL_NAME = "large-v3"
#: Model used on CPU-only machines (good accuracy, stays fast without a GPU).
CPU_MODEL_NAME = "small"
#: Values accepted from the STT_MODEL environment variable. Restricting to
#: known Whisper names prevents the env var from pointing the downloader at
#: an arbitrary HuggingFace repo.
ALLOWED_MODELS = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v2", "large-v3", "large-v3-turbo",
    "distil-large-v3",
})


def _add_nvidia_dll_dirs():
    """Expose pip-installed cuBLAS/cuDNN DLLs to CTranslate2 on Windows.

    The nvidia-cublas-cu12 / nvidia-cudnn-cu12 wheels drop their DLLs inside
    site-packages/nvidia/<lib>/bin, which is not on the loader path by default.

    Only needed when running from source: PyInstaller builds place the CUDA
    DLLs directly next to the app's libraries, where Windows finds them on
    its own. (In frozen builds ``import nvidia`` may even succeed as an empty
    phantom package whose path does not exist, so we must not touch it.)
    """
    if sys.platform != "win32" or getattr(sys, "frozen", False):
        return
    try:
        import nvidia
        for pkg_root in nvidia.__path__:
            if not os.path.isdir(pkg_root):
                continue
            for sub in os.listdir(pkg_root):
                for leaf in ("bin", "lib"):
                    dll_dir = os.path.join(pkg_root, sub, leaf)
                    if os.path.isdir(dll_dir):
                        os.add_dll_directory(dll_dir)
                        os.environ["PATH"] = (dll_dir + os.pathsep
                                              + os.environ.get("PATH", ""))
    except Exception:
        # Never let DLL-path setup break model loading; worst case CUDA
        # init fails later and the app falls back to CPU.
        return


class Transcriber:
    """Thin wrapper around a lazily loaded faster-whisper model."""

    def __init__(self):
        self.model = None
        self.pipeline = None
        self.model_name = None
        self.device_label = None
        self.gpu_error = None  # why the GPU load failed, if it did

    def load(self) -> str:
        """Load the Whisper model, preferring the GPU.

        Tries ``large-v3`` on CUDA first; if no usable GPU is present, falls
        back to the lighter ``small`` model on CPU so the app stays responsive
        on any machine. macOS goes straight to CPU, since CUDA cannot exist
        there and merely asking for it would download the large model first.
        Set the ``STT_MODEL`` environment variable to force a specific model
        on either device.

        Returns:
            str: Human-readable device label, e.g. ``"GPU (CUDA, float16)"``.
        """
        _add_nvidia_dll_dirs()
        import numpy as np
        from faster_whisper import BatchedInferencePipeline, WhisperModel

        override = os.environ.get("STT_MODEL")
        if override and override not in ALLOWED_MODELS:
            override = None  # unknown value: ignore and use the defaults
        # macOS never has CUDA, and WhisperModel downloads the weights before
        # it initialises the device - so attempting the GPU path there would
        # fetch all 3 GB of large-v3 only to discard it when the CUDA init
        # fails. Skipping the attempt keeps a Mac's first launch to the CPU
        # model alone. This is expected on a Mac, not a failure, so leave
        # gpu_error unset: the UI reserves that for a GPU that should have
        # worked and did not.
        if sys.platform != "darwin":
            try:
                self.model_name = override or MODEL_NAME
                self.model = WhisperModel(self.model_name, device="cuda",
                                          compute_type="float16")
                self.device_label = "GPU (CUDA, float16)"
            except Exception as exc:
                self.gpu_error = str(exc)

        if self.model is None:
            self.model_name = override or CPU_MODEL_NAME
            self.model = WhisperModel(self.model_name, device="cpu",
                                      compute_type="int8")
            self.device_label = "CPU (int8)"

        # Batched pipeline decodes VAD-split chunks in parallel - much faster
        # than sequential decoding, especially for longer dictations.
        self.pipeline = BatchedInferencePipeline(model=self.model)

        # Warm up: the first pass through the model triggers one-time cuDNN
        # kernel selection. Paying that cost here (on 1s of silence) keeps the
        # user's first real transcription fast.
        warmup = np.zeros(16000, dtype=np.float32)
        segments, _ = self.model.transcribe(warmup, language="en", beam_size=1,
                                            vad_filter=False)
        for _ in segments:
            pass
        return self.device_label

    def transcribe(self, audio):
        """Transcribe recorded audio to text.

        Args:
            audio (numpy.ndarray): 1-D float32 samples at 16 kHz.

        Returns:
            tuple: ``(text, lang, probability, duration)`` where

                - text (str): cleaned transcript (punctuated, spell-correct);
                - lang (str): ``"en"`` or ``"es"`` - auto-detected; anything
                  that is not Spanish maps to English so the two UI panes
                  always have a home for the text;
                - probability (float): confidence of the language detection;
                - duration (float): seconds of speech that were transcribed.
        """
        segments, info = self.pipeline.transcribe(
            audio,
            beam_size=5,        # wider beam = more accurate decoding
            batch_size=16,      # decode up to 16 VAD chunks concurrently
        )
        # Iterating the generator is what actually runs the transcription.
        text = " ".join(seg.text.strip() for seg in segments)
        text = re.sub(r"\s+", " ", text).strip()
        lang = normalise(info.language)
        return text, lang, info.language_probability, info.duration
