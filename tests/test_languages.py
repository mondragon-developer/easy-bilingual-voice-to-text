"""Unit tests for src.languages, the one place that knows the app is bilingual."""

import pytest

from src.languages import (DEFAULT_LANG, LANG_NAMES, PANE_ORDER, counterpart,
                           normalise)


class TestNormalise:
    def test_a_language_with_a_pane_is_kept(self):
        assert normalise("es") == "es"
        assert normalise("en") == "en"

    @pytest.mark.parametrize("detected", ["fr", "de", "pt", "zh", "xx", ""])
    def test_anything_else_falls_back_to_the_default(self, detected):
        """Whisper knows ~99 languages; only two have somewhere to go, and
        text must never be dropped because of that."""
        assert normalise(detected) == DEFAULT_LANG

    def test_the_default_has_a_pane(self):
        assert DEFAULT_LANG in LANG_NAMES


class TestCounterpart:
    def test_pairs_the_two_panes(self):
        assert counterpart("en") == "es"
        assert counterpart("es") == "en"

    def test_is_its_own_inverse(self):
        for lang in PANE_ORDER:
            assert counterpart(counterpart(lang)) == lang

    def test_a_language_without_a_pane_is_an_error(self):
        with pytest.raises(KeyError):
            counterpart("fr")


class TestConsistency:
    def test_pane_order_and_names_describe_the_same_languages(self):
        assert set(PANE_ORDER) == set(LANG_NAMES)

    def test_there_are_exactly_two_panes(self):
        """counterpart() has no meaning beyond a pair; if this ever changes,
        the pairing model has to change with it."""
        assert len(PANE_ORDER) == 2
