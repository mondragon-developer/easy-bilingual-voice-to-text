"""Unit tests for src.transcriber (text assembly + language mapping)."""

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.transcriber import Transcriber, _add_nvidia_dll_dirs


def _fake_pipeline(segment_texts, language, probability=0.97, duration=5.0):
    """Build a mock pipeline whose transcribe() yields the given segments."""
    segments = (SimpleNamespace(text=t) for t in segment_texts)
    info = SimpleNamespace(language=language, language_probability=probability,
                           duration=duration)
    pipeline = MagicMock()
    pipeline.transcribe.return_value = (segments, info)
    return pipeline


class TestTranscribe:
    def _run(self, segment_texts, language):
        tr = Transcriber()
        tr.pipeline = _fake_pipeline(segment_texts, language)
        return tr.transcribe(np.zeros(16000, dtype=np.float32))

    def test_segments_join_into_clean_text(self):
        text, _, _, _ = self._run(["  Hello there. ", "  How are you?"], "en")
        assert text == "Hello there. How are you?"

    def test_internal_whitespace_is_collapsed(self):
        text, _, _, _ = self._run(["One \n two", "three"], "en")
        assert text == "One two three"

    def test_spanish_is_detected(self):
        _, lang, prob, _ = self._run(["Hola."], "es")
        assert lang == "es"
        assert prob == pytest.approx(0.97)

    def test_english_is_detected(self):
        _, lang, _, _ = self._run(["Hello."], "en")
        assert lang == "en"

    def test_other_languages_map_to_english(self):
        # The UI only has EN/ES panes; anything else lands in the EN pane.
        _, lang, _, _ = self._run(["Bonjour."], "fr")
        assert lang == "en"

    def test_duration_is_returned(self):
        _, _, _, duration = self._run(["Hi."], "en")
        assert duration == pytest.approx(5.0)

    def test_empty_audio_returns_empty_text(self):
        text, _, _, _ = self._run([], "en")
        assert text == ""


class TestModelAllowlist:
    def test_known_models_are_allowed(self):
        from src.transcriber import ALLOWED_MODELS, CPU_MODEL_NAME, MODEL_NAME
        assert MODEL_NAME in ALLOWED_MODELS
        assert CPU_MODEL_NAME in ALLOWED_MODELS

    def test_arbitrary_repo_ids_are_rejected(self):
        from src.transcriber import ALLOWED_MODELS
        # STT_MODEL must not be able to point at any random HF repo.
        assert "evil-org/backdoored-model" not in ALLOWED_MODELS

    @pytest.mark.parametrize("model", ["distil-large-v2", "distil-large-v3",
                                       "distil-large-v3.5"])
    def test_silently_english_only_models_are_rejected(self, model):
        """These are English-only but nothing in the name says so.

        On a bilingual app they are worse than a rejected value: Spanish audio
        comes back as English-ish mush instead of raising, so the user sees a
        bad transcript with no clue why. The ``.en`` names stay allowed because
        someone typing ``small.en`` has said what they want.
        """
        from src.transcriber import ALLOWED_MODELS
        assert model not in ALLOWED_MODELS

    def test_every_allowed_multilingual_name_lacks_the_en_suffix(self):
        """Sanity check that the allowlist splits cleanly into two groups."""
        from src.transcriber import ALLOWED_MODELS
        multilingual = {m for m in ALLOWED_MODELS if not m.endswith(".en")}
        assert multilingual == {"tiny", "base", "small", "medium",
                                "large-v2", "large-v3", "large-v3-turbo"}


class TestNvidiaDllDirs:
    def test_missing_nvidia_package_is_harmless(self):
        with patch.dict(sys.modules, {"nvidia": None}):
            _add_nvidia_dll_dirs()  # must not raise

    def test_non_windows_is_a_noop(self):
        with patch("src.transcriber.sys") as fake_sys:
            fake_sys.platform = "linux"
            _add_nvidia_dll_dirs()  # must not raise or touch the registry

    def test_frozen_build_is_a_noop(self):
        # PyInstaller builds carry their CUDA DLLs next to the app already.
        with patch("src.transcriber.sys") as fake_sys:
            fake_sys.platform = "win32"
            fake_sys.frozen = True
            _add_nvidia_dll_dirs()  # must return before importing nvidia

    def test_phantom_namespace_package_is_harmless(self):
        # Regression (v2.0.1 bug): PyInstaller registered an 'nvidia'
        # package whose __path__ pointed to a directory that doesn't exist,
        # so os.listdir raised WinError 3 and the model never loaded.
        phantom = types.ModuleType("nvidia")
        phantom.__path__ = [r"C:\does\not\exist\nvidia"]
        with patch.dict(sys.modules, {"nvidia": phantom}):
            _add_nvidia_dll_dirs()  # must not raise
