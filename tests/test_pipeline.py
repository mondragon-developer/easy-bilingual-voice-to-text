"""Unit tests for src.pipeline: the dictation sequence with every part faked."""

from unittest.mock import MagicMock

import numpy as np
import pytest
import requests

from src.pipeline import Pipeline
from src.translator import Translation

AUDIO = np.zeros(16000, dtype=np.float32)


@pytest.fixture
def parts():
    transcriber = MagicMock()
    transcriber.transcribe.return_value = ("Um, you you was there.", "en", 0.98, 1.5)
    translator = MagicMock(return_value=Translation("Estabas ahí.", "offline"))
    grammar = MagicMock()
    grammar.correct.side_effect = lambda text, progress=None: text.replace(
        "there", "there, indeed")
    return transcriber, translator, grammar


def _pipeline(parts):
    transcriber, translator, grammar = parts
    return Pipeline(transcriber, translator=translator, grammar=grammar)


class TestSequence:
    def test_rules_then_translation(self, parts):
        result = _pipeline(parts).run(AUDIO)
        assert result.text == "You were there."
        assert result.lang == "en"
        assert result.translation == "Estabas ahí."
        assert result.engine == "offline"
        assert result.notes == ()
        parts[1].assert_called_once()
        assert parts[1].call_args.args == ("You were there.",)
        assert parts[1].call_args.kwargs["mode"] == "offline"
        parts[2].correct.assert_not_called()

    def test_full_adds_the_grammar_model_before_translation(self, parts):
        result = _pipeline(parts).run(AUDIO, tidy_mode="full")
        parts[2].correct.assert_called_once()
        assert parts[2].correct.call_args.args == ("You were there.",)
        assert result.text == "You were there, indeed."
        assert parts[1].call_args.args == ("You were there, indeed.",)

    def test_off_leaves_the_words_as_spoken(self, parts):
        result = _pipeline(parts).run(AUDIO, tidy_mode="off", translate_mode="off")
        assert result.text == "Um, you you was there."
        assert result.translation == ""
        parts[1].assert_not_called()

    def test_spanish_skips_the_grammar_model(self, parts):
        parts[0].transcribe.return_value = ("Yo yo creo.", "es", 0.9, 1.0)
        parts[1].return_value = Translation("I think.", "Google")
        result = _pipeline(parts).run(AUDIO, tidy_mode="full", translate_mode="online")
        parts[2].correct.assert_not_called()
        assert result.text == "Yo creo."
        assert (parts[1].call_args.kwargs["source"],
                parts[1].call_args.kwargs["target"]) == ("es", "en")

    def test_no_speech_is_empty_text_and_no_translation(self, parts):
        parts[0].transcribe.return_value = ("", "en", 0.5, 0.0)
        result = _pipeline(parts).run(AUDIO)
        assert result.text == ""
        parts[1].assert_not_called()

    def test_only_fillers_counts_as_no_speech(self, parts):
        parts[0].transcribe.return_value = ("Hmm.", "en", 0.5, 0.4)
        assert _pipeline(parts).run(AUDIO).text == ""


class TestFailures:
    def test_a_grammar_model_that_cannot_run_is_a_note_not_an_error(self, parts):
        parts[2].correct.side_effect = requests.ConnectionError("offline")
        result = _pipeline(parts).run(AUDIO, tidy_mode="full")
        assert result.text == "You were there."
        assert result.translation == "Estabas ahí."
        assert result.notes == ("grammar check skipped: no connection",)

    def test_a_failed_translation_keeps_the_spoken_text(self, parts):
        parts[1].side_effect = RuntimeError("Google: no connection")
        result = _pipeline(parts).run(AUDIO)
        assert result.text == "You were there."
        assert result.translation == ""
        assert result.engine == ""
        assert result.notes == ("translation failed: Google: no connection",)


class TestProgress:
    def test_downloads_are_reported_with_the_model_named(self, parts):
        seen = []
        parts[2].correct.side_effect = lambda text, progress=None: (
            progress(10, 100), text)[1]
        parts[1].side_effect = lambda text, **kw: (
            kw["progress"](50, 100), Translation("x", "offline"))[1]
        _pipeline(parts).run(AUDIO, tidy_mode="full",
                             progress=lambda what, d, t: seen.append((what, d, t)))
        assert seen == [("the grammar model", 10, 100),
                        ("the offline translator, en to es", 50, 100)]

    def test_no_progress_callback_is_fine(self, parts):
        _pipeline(parts).run(AUDIO, tidy_mode="full")
        assert parts[2].correct.call_args.kwargs["progress"] is None
