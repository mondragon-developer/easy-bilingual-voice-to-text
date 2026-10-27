"""Speech-to-text via faster-whisper with automatic EN/ES language detection.

Loads the model onto the GPU (CUDA / float16) when available and falls back
to CPU (int8) automatically. Whisper's output is already punctuated and
correctly spelled, which is what gives the app its precision.
"""

import gc
import os
import re
import sys
import threading
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
#: The speech-model choices the UI offers, as (model, device, compute type,
#: batch size). "light" is there to give the GPU back to something else
#: without giving up Spanish: turbo is multilingual, int8 weights take about
#: a quarter of large-v3's float16, and a smaller batch keeps the decode
#: buffers down too. "cpu" frees the GPU entirely.
MODES = {
    "best": (MODEL_NAME, "cuda", "float16", 16),
    "light": ("large-v3-turbo", "cuda", "int8_float16", 4),
    "cpu": (CPU_MODEL_NAME, "cpu", "int8", 16),
}
DEFAULT_MODE = "best"

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


def _cuda_devices() -> int:
    """How many CUDA devices CTranslate2 can see; 1 when it cannot say.

    Asked before any GPU model is built because WhisperModel downloads the
    weights first and only then finds out there is no GPU: on a PC without
    an NVIDIA card, choosing Light would fetch 1.5 GB to throw away. "Cannot
    say" keeps the old behaviour of trying, so a broken query never costs a
    working GPU.
    """
    try:
        import ctranslate2
        return ctranslate2.get_cuda_device_count()
    except Exception:
        return 1


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


class ModelNotLoaded(RuntimeError):
    """A transcription asked for while no model is loaded: mid-swap, or
    after a swap that failed outright."""


class Transcriber:
    """Thin wrapper around a lazily loaded faster-whisper model.

    ``load``, ``unload`` and ``transcribe`` share one lock, so a model swap
    asked for mid-dictation waits for that dictation to finish instead of
    freeing the model out from under it.
    """

    def __init__(self):
        self.model = None
        self.pipeline = None
        self.model_name = None
        self.device_label = None
        self.mode = None        # the MODES key that actually loaded
        self.batch_size = MODES[DEFAULT_MODE][3]
        self.gpu_error = None  # why the GPU load failed, if it did
        self._lock = threading.RLock()

    def load(self, mode=DEFAULT_MODE) -> str:
        """Load the Whisper model for ``mode``, replacing any loaded one.

        ``"best"`` and ``"light"`` try the GPU and fall back to the
        ``small`` model on CPU when no usable GPU is present, so the app
        stays responsive on any machine; ``"cpu"`` goes there directly.
        macOS always goes straight to CPU, since CUDA cannot exist there and
        merely asking for it would download the large model first. Set the
        ``STT_MODEL`` environment variable to force a specific model on
        either device.

        The old model is released before the new one loads, so a swap never
        holds two models in GPU memory at once.

        Args:
            mode: A key of ``MODES``. An unknown value means the default.

        Returns:
            str: Human-readable device label, e.g. ``"GPU (CUDA, float16)"``.
        """
        if mode not in MODES:
            mode = DEFAULT_MODE
        with self._lock:
            self.unload()
            self._load(mode)
        return self.device_label

    def _load(self, mode):
        _add_nvidia_dll_dirs()
        import numpy as np
        from faster_whisper import BatchedInferencePipeline, WhisperModel

        override = os.environ.get("STT_MODEL")
        if override and override not in ALLOWED_MODELS:
            override = None  # unknown value: ignore and use the defaults
        name, device, compute_type, batch_size = MODES[mode]
        self.gpu_error = None
        # macOS never has CUDA, and WhisperModel downloads the weights before
        # it initialises the device - so attempting the GPU path there would
        # fetch all 3 GB of large-v3 only to discard it when the CUDA init
        # fails. Skipping the attempt keeps a Mac's first launch to the CPU
        # model alone. This is expected on a Mac, not a failure, so leave
        # gpu_error unset: the UI reserves that for a GPU that should have
        # worked and did not.
        try_gpu = device == "cuda" and sys.platform != "darwin"
        if try_gpu and _cuda_devices() == 0:
            # Still reported, as a failed CUDA load always was: on a PC that
            # does have an NVIDIA card, a missing driver looks exactly like
            # this, and the status bar is where its owner finds out.
            self.gpu_error = "no CUDA-capable GPU was found"
        elif try_gpu:
            try:
                self.model_name = override or name
                self.model = _open_model(WhisperModel, self.model_name,
                                         device, compute_type)
                # The warm-up has to sit inside this try. Constructing the
                # CUDA model only needs the driver; cuBLAS is loaded at the
                # first matmul. On a PC with an NVIDIA driver but no CUDA
                # DLLs (the CPU zip), the construction succeeds, the app
                # reports GPU, and the first recording dies with "Library
                # cublas64_12.dll is not found". Running one pass here turns
                # that into the CPU fallback it should have been.
                self._warm_up(np)
                self.device_label = f"GPU (CUDA, {compute_type})"
                self.mode = mode
                self.batch_size = batch_size
            except Exception as exc:
                self.gpu_error = str(exc)
                self.model = None

        if self.model is None:
            cpu_name, _, cpu_compute, cpu_batch = MODES["cpu"]
            self.model_name = override or cpu_name
            self.model = _open_model(WhisperModel, self.model_name,
                                     "cpu", cpu_compute)
            self.device_label = f"CPU ({cpu_compute})"
            self._warm_up(np)
            self.mode = "cpu"
            self.batch_size = cpu_batch

        # Batched pipeline decodes VAD-split chunks in parallel - much faster
        # than sequential decoding, especially for longer dictations.
        self.pipeline = BatchedInferencePipeline(model=self.model)

    def unload(self):
        """Release the model and the GPU memory it holds. Safe to repeat.

        CTranslate2 frees device memory when its model object goes away, but
        anything still referencing it (a traceback, the pipeline) would keep
        it alive, so the weights are unloaded explicitly first.
        """
        with self._lock:
            engine = getattr(self.model, "model", None)
            if engine is not None and hasattr(engine, "unload_model"):
                try:
                    engine.unload_model()
                except Exception:
                    pass  # dropping the references below still frees it
            self.pipeline = None
            self.model = None
            self.mode = None
            gc.collect()

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
        with self._lock:
            if self.pipeline is None:
                raise ModelNotLoaded("the speech model is not loaded "
                                     "(switching models?)")
            segments, info = self.pipeline.transcribe(
                audio,
                beam_size=5,        # wider beam = more accurate decoding
                batch_size=self.batch_size,  # VAD chunks decoded at once
            )
            # Iterating the generator is what actually runs the
            # transcription, so it has to stay under the lock too.
            text = " ".join(seg.text.strip() for seg in segments)
        text = re.sub(r"\s+", " ", text).strip()
        lang = normalise(info.language)
        return text, lang, info.language_probability, info.duration
