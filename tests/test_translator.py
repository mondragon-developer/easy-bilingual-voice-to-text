"""Unit tests for src.translator: chunking, each engine, and the fallback chain."""

from unittest.mock import MagicMock, patch

import pytest
import requests
from deep_translator.exceptions import TooManyRequests

from src.translator import (ENGINE_GOOGLE, ENGINE_MYMEMORY, ENGINE_OFFLINE,
                            MODES, NETWORK_TIMEOUT, Translation,
                            TranslationError, _MAX_CHARS, _request_timeout,
                            _split_chunks, describe_failure, translate,
                            translate_google, translate_mymemory)


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

    def test_google_applies_the_timeout(self):
        seen = {}
        fake = MagicMock()
        fake.translate.side_effect = lambda chunk: seen.update(
            captured=requests.get.__name__) or "hola"
        with patch("src.translator.GoogleTranslator", return_value=fake):
            translate_google("hello", "en", "es")
        assert seen["captured"] == "_get_with_timeout"

    def test_mymemory_applies_the_timeout(self):
        seen = {}
        fake = MagicMock()
        fake.translate.side_effect = lambda chunk: seen.update(
            captured=requests.get.__name__) or "hola"
        with patch("src.translator.MyMemoryTranslator", return_value=fake):
            translate_mymemory("hello", "en", "es")
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


class TestGoogle:
    def test_single_chunk_translation(self):
        with patch("src.translator.GoogleTranslator") as gt:
            gt.return_value.translate.return_value = "Hello world."
            result = translate_google("Hola mundo.", "es", "en")
        assert result == "Hello world."
        gt.assert_called_once_with(source="es", target="en")

    def test_multi_chunk_results_are_joined(self):
        fake = MagicMock()
        fake.translate.side_effect = ["Part one.", "Part two."]
        with patch("src.translator.GoogleTranslator", return_value=fake), \
             patch("src.translator._split_chunks",
                   return_value=["Parte uno.", "Parte dos."]):
            result = translate_google("Parte uno. Parte dos.", "es", "en")
        assert result == "Part one. Part two."
        assert fake.translate.call_count == 2

    def test_none_chunk_results_are_skipped(self):
        fake = MagicMock()
        fake.translate.side_effect = ["Hello.", None]
        with patch("src.translator.GoogleTranslator", return_value=fake), \
             patch("src.translator._split_chunks",
                   return_value=["Hola.", "..."]):
            assert translate_google("Hola. ...", "es", "en") == "Hello."


class TestMyMemory:
    def test_uses_locales_not_bare_codes(self):
        with patch("src.translator.MyMemoryTranslator") as mm:
            mm.return_value.translate.return_value = "Hello."
            translate_mymemory("Hola.", "es", "en")
        mm.assert_called_once_with(source="es-ES", target="en-US")

    def test_chunks_stay_under_the_500_char_cap(self):
        fake = MagicMock()
        fake.translate.return_value = "x"
        text = ("Una frase bastante larga para la prueba. " * 40).strip()
        with patch("src.translator.MyMemoryTranslator", return_value=fake):
            translate_mymemory(text, "es", "en")
        for call in fake.translate.call_args_list:
            assert len(call.args[0]) <= 500

    def test_an_exhausted_quota_is_an_error_not_a_translation(self):
        """MyMemory answers 200 OK with a warning sentence as the 'translation'.
        Letting that through would paste the warning into the Spanish pane."""
        fake = MagicMock()
        fake.translate.return_value = (
            "MYMEMORY WARNING: YOU USED ALL AVAILABLE FREE TRANSLATIONS FOR TODAY.")
        with patch("src.translator.MyMemoryTranslator", return_value=fake):
            with pytest.raises(TooManyRequests):
                translate_mymemory("Hola.", "es", "en")


class TestDescribeFailure:
    def test_rate_limit_is_named_as_such(self):
        assert "rate-limited" in describe_failure(TooManyRequests())

    def test_connection_errors_say_no_connection(self):
        assert describe_failure(requests.ConnectionError()) == "no connection"
        assert describe_failure(requests.Timeout()) == "no connection"

    def test_http_errors_carry_the_status(self):
        response = MagicMock(status_code=404)
        assert "404" in describe_failure(requests.HTTPError(response=response))

    def test_verification_failures_keep_their_message(self):
        assert describe_failure(ValueError("failed verification")) == \
            "failed verification"

    def test_anything_else_gives_the_type(self):
        assert describe_failure(RuntimeError("x")) == "RuntimeError"


class TestTranslateChain:
    """``translate`` picks engines by mode and moves down the chain on
    failure, reporting which one finally produced the text."""

    @pytest.fixture
    def engines(self):
        with patch("src.translator.translate_google") as google, \
             patch("src.translator.translate_mymemory") as mymemory:
            local = MagicMock()
            yield google, mymemory, local

    def test_modes_are_the_three_the_ui_shows(self):
        assert MODES == ("off", "offline", "online")

    def test_empty_input_short_circuits(self, engines):
        google, mymemory, local = engines
        assert translate("   ", "es", "en", "online", local=local) == \
            Translation("", ENGINE_OFFLINE)
        google.assert_not_called()
        local.translate.assert_not_called()

    def test_off_is_not_a_mode_to_translate_in(self, engines):
        with pytest.raises(ValueError):
            translate("Hola.", "es", "en", "off", local=engines[2])

    def test_offline_uses_only_the_local_model(self, engines):
        google, mymemory, local = engines
        local.translate.return_value = "Hello."
        result = translate("Hola.", "es", "en", "offline", local=local)
        assert result == Translation("Hello.", ENGINE_OFFLINE)
        google.assert_not_called()
        mymemory.assert_not_called()

    def test_offline_never_falls_back_to_the_network(self, engines):
        """Offline is a promise, not a preference."""
        google, mymemory, local = engines
        local.translate.side_effect = requests.ConnectionError()
        with pytest.raises(TranslationError) as info:
            translate("Hola.", "es", "en", "offline", local=local)
        google.assert_not_called()
        mymemory.assert_not_called()
        assert "offline: no connection" in str(info.value)

    def test_online_prefers_google(self, engines):
        google, mymemory, local = engines
        google.return_value = "Hello."
        result = translate("Hola.", "es", "en", "online", local=local)
        assert result == Translation("Hello.", ENGINE_GOOGLE)
        google.assert_called_once_with("Hola.", "es", "en")
        mymemory.assert_not_called()
        local.translate.assert_not_called()

    def test_a_rate_limited_google_falls_back_to_mymemory(self, engines):
        google, mymemory, local = engines
        google.side_effect = TooManyRequests()
        mymemory.return_value = "Hello."
        result = translate("Hola.", "es", "en", "online", local=local)
        assert result == Translation("Hello.", ENGINE_MYMEMORY)
        local.translate.assert_not_called()

    def test_both_services_down_falls_back_to_the_local_model(self, engines):
        google, mymemory, local = engines
        google.side_effect = TooManyRequests()
        mymemory.side_effect = TooManyRequests()
        local.translate.return_value = "Hello."
        result = translate("Hola.", "es", "en", "online", local=local)
        assert result == Translation("Hello.", ENGINE_OFFLINE)

    def test_an_empty_reply_counts_as_a_failure(self, engines):
        google, mymemory, local = engines
        google.return_value = ""
        mymemory.return_value = "Hello."
        result = translate("Hola.", "es", "en", "online", local=local)
        assert result.engine == ENGINE_MYMEMORY

    def test_every_engine_failing_names_each_reason(self, engines):
        google, mymemory, local = engines
        google.side_effect = TooManyRequests()
        mymemory.side_effect = requests.ConnectionError()
        local.translate.side_effect = ValueError("failed verification")
        with pytest.raises(TranslationError) as info:
            translate("Hola.", "es", "en", "online", local=local)
        message = str(info.value)
        assert "Google: rate-limited" in message
        assert "MyMemory: no connection" in message
        assert "offline: failed verification" in message

    def test_progress_reaches_the_local_download(self, engines):
        google, mymemory, local = engines
        local.translate.return_value = "Hello."
        progress = MagicMock()
        translate("Hola.", "es", "en", "offline", local=local,
                  progress=progress)
        local.translate.assert_called_once_with("Hola.", "es", "en",
                                                progress=progress)

    def test_the_local_translator_is_created_on_demand(self, engines):
        """Nothing imports CTranslate2 until a translation asks for it."""
        google, mymemory, _ = engines
        with patch("src.local_mt.LocalTranslator") as cls:
            cls.return_value.translate.return_value = "Hello."
            result = translate("Hola.", "es", "en", "offline")
        assert result == Translation("Hello.", ENGINE_OFFLINE)
        cls.assert_called_once_with()
