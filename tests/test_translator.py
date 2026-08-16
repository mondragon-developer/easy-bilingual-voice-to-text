"""Unit tests for src.translator (chunking + translation orchestration)."""

from unittest.mock import MagicMock, patch

import requests

from src.translator import (NETWORK_TIMEOUT, _MAX_CHARS, _request_timeout,
                            _split_chunks, translate)


class TestRequestTimeout:
    """deep-translator calls requests.get() with no timeout, and requests then
    waits forever. A captive portal would hang the worker thread for good."""

    def test_a_timeout_is_injected_into_the_call(self):
        seen = {}
        with patch.object(requests, "get",
                          side_effect=lambda *a, **k: seen.update(k)):
            with _request_timeout(7):
                requests.get("http://example.invalid/")
        assert seen["timeout"] == 7

    def test_an_explicit_timeout_is_not_overridden(self):
        seen = {}
        with patch.object(requests, "get",
                          side_effect=lambda *a, **k: seen.update(k)):
            with _request_timeout(7):
                requests.get("http://example.invalid/", timeout=1)
        assert seen["timeout"] == 1

    def test_requests_get_is_restored_afterwards(self):
        original = requests.get
        with _request_timeout(7):
            assert requests.get is not original
        assert requests.get is original

    def test_it_is_restored_even_when_the_call_raises(self):
        original = requests.get
        try:
            with _request_timeout(7):
                raise ConnectionError("offline")
        except ConnectionError:
            pass
        assert requests.get is original

    def test_translate_applies_the_timeout(self):
        seen = {}
        fake = MagicMock()
        fake.translate.side_effect = lambda chunk: seen.update(
            captured=requests.get.__name__) or "hola"
        with patch("src.translator.GoogleTranslator", return_value=fake):
            translate("hello", target="es")
        assert seen["captured"] == "_get_with_timeout"

    def test_the_timeout_is_a_sane_length(self):
        assert 5 <= NETWORK_TIMEOUT <= 60


class TestSplitChunks:
    def test_empty_text_gives_no_chunks(self):
        assert _split_chunks("") == []

    def test_short_text_is_single_chunk(self):
        assert _split_chunks("Hola mundo.") == ["Hola mundo."]

    def test_splits_at_sentence_boundaries(self):
        text = "First sentence. Second sentence! Third sentence?"
        chunks = _split_chunks(text, limit=20)
        assert chunks == ["First sentence.", "Second sentence!", "Third sentence?"]

    def test_groups_sentences_under_limit(self):
        text = "One. Two. Three."
        assert _split_chunks(text, limit=12) == ["One. Two.", "Three."]

    def test_every_chunk_respects_limit(self):
        text = ("This is a fairly long sentence used for testing. " * 40).strip()
        for chunk in _split_chunks(text, limit=200):
            assert len(chunk) <= 200

    def test_oversized_single_sentence_is_hard_split(self):
        text = "a" * 95  # no sentence boundary at all
        chunks = _split_chunks(text, limit=30)
        assert "".join(chunks) == text
        assert all(len(c) <= 30 for c in chunks)

    def test_default_limit_under_google_cap(self):
        assert _MAX_CHARS < 5000


class TestTranslate:
    def test_empty_input_short_circuits(self):
        with patch("src.translator.GoogleTranslator") as gt:
            assert translate("   ", target="es") == ""
            gt.assert_not_called()

    def test_single_chunk_translation(self):
        with patch("src.translator.GoogleTranslator") as gt:
            gt.return_value.translate.return_value = "Hello world."
            result = translate("Hola mundo.", target="en")
        assert result == "Hello world."
        gt.assert_called_once_with(source="auto", target="en")

    def test_multi_chunk_results_are_joined(self):
        fake = MagicMock()
        fake.translate.side_effect = ["Part one.", "Part two."]
        with patch("src.translator.GoogleTranslator", return_value=fake), \
             patch("src.translator._split_chunks",
                   return_value=["Parte uno.", "Parte dos."]):
            result = translate("Parte uno. Parte dos.", target="en")
        assert result == "Part one. Part two."
        assert fake.translate.call_count == 2

    def test_none_chunk_results_are_skipped(self):
        fake = MagicMock()
        fake.translate.side_effect = ["Hello.", None]
        with patch("src.translator.GoogleTranslator", return_value=fake), \
             patch("src.translator._split_chunks",
                   return_value=["Hola.", "..."]):
            assert translate("Hola. ...", target="en") == "Hello."
