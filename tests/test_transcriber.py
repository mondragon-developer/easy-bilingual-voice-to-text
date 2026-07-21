"""Unit tests for src.transcriber (text assembly + language mapping)."""

import sys
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


class TestNvidiaDllDirs:
    def test_missing_nvidia_package_is_harmless(self):
        with patch.dict(sys.modules, {"nvidia": None}):
            _add_nvidia_dll_dirs()  # must not raise

    def test_non_windows_is_a_noop(self):
        with patch("src.transcriber.sys") as fake_sys:
            fake_sys.platform = "linux"
            _add_nvidia_dll_dirs()  # must not raise or touch the registry
