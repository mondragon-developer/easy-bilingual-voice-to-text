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
#:
#: The ``.en`` names are English-only by design and are listed anyway: someone
#: who types ``small.en`` has said what they want. What must stay out are
#: English-only models whose names do not say so. ``distil-large-v3`` was here
#: and was removed: HuggingFace reports ``language: ['en']`` for it, so on this
#: bilingual app it does not fail on Spanish audio, it silently returns
#: English-ish mush. Same for ``distil-large-v2`` and ``distil-large-v3.5``.
#: If a multilingual distil model ships later, check its card before adding it.
ALLOWED_MODELS = frozenset({
    "tiny", "tiny.en", "base", "base.en", "small", "small.en",
    "medium", "medium.en", "large-v2", "large-v3", "large-v3-turbo",
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


def _open_model(WhisperModel, name, device, compute_type):
    """Build a WhisperModel from the local cache, downloading only on a miss.

    faster-whisper's default is to ask the Hugging Face hub for the model's
    current revision on every construction, even when the weights are
    already cached. That is one network round trip per launch that the app
    never needed and that the privacy notes promise it does not make. The
    cache is tried first with the network switched off; only a genuine cache
    miss (a first run, or a wiped cache) goes online.

    A model that is cached but fails to initialise on the device raises
    something other than ``FileNotFoundError`` and is not retried here: the
    caller's device fallback handles it.
    """
    try:
        return WhisperModel(name, device=device, compute_type=compute_type,
                            local_files_only=True)
    except FileNotFoundError:
        return WhisperModel(name, device=device, compute_type=compute_type)


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
                self.model = _open_model(WhisperModel, self.model_name,
                                         "cuda", "float16")
                # The warm-up has to sit inside this try. Constructing the
                # CUDA model only needs the driver; cuBLAS is loaded at the
                # first matmul. On a PC with an NVIDIA driver but no CUDA
                # DLLs (the CPU zip), the construction succeeds, the app
                # reports GPU, and the first recording dies with "Library
                # cublas64_12.dll is not found". Running one pass here turns
                # that into the CPU fallback it should have been.
                self._warm_up(np)
                self.device_label = "GPU (CUDA, float16)"
            except Exception as exc:
                self.gpu_error = str(exc)
                self.model = None

        if self.model is None:
            self.model_name = override or CPU_MODEL_NAME
            self.model = _open_model(WhisperModel, self.model_name,
                                     "cpu", "int8")
            self.device_label = "CPU (int8)"
            self._warm_up(np)

        # Batched pipeline decodes VAD-split chunks in parallel - much faster
        # than sequential decoding, especially for longer dictations.
        self.pipeline = BatchedInferencePipeline(model=self.model)
        return self.device_label

    def _warm_up(self, np):
        """Run one pass over a second of silence.

        The first pass triggers one-time cuDNN kernel selection, so paying it
        here keeps the user's first real transcription fast. It is also the
        earliest point at which a GPU that cannot actually compute reveals
        itself, which is why ``load`` calls it before trusting the device.
        """
        warmup = np.zeros(16000, dtype=np.float32)
        segments, _ = self.model.transcribe(warmup, language="en", beam_size=1,
                                            vad_filter=False)
        for _ in segments:
            pass

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
