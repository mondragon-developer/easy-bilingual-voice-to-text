"""Unit tests for src.local_mt: the model installer and the offline engine.

The real models are 68 MB each and CTranslate2 is slow to start, so the
installer is tested against an in-memory zip served by a fake HTTP session,
and the engine against a fake CTranslate2 / SentencePiece pair. What the
tests care about is the safety of the install and the shape of the calls,
not the quality of a translation.
"""

import hashlib
import io
import zipfile
from unittest.mock import MagicMock, patch

import pytest

from src.local_mt import (MODELS, LocalTranslator, ModelSpec, _Engine,
                          _split_sentences, install, is_installed, models_dir)


def _zip_bytes(names=("model.bin", "source.spm", "target.spm"), prefix=""):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in names:
            z.writestr(prefix + name, b"data:" + name.encode())
    return buf.getvalue()


def _spec(payload):
    return ModelSpec("es", "en", hashlib.sha256(payload).hexdigest(), 1)


class _FakeResponse:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status
        self.headers = {"Content-Length": str(len(payload))}

    def raise_for_status(self):
        if self.status_code >= 400:
            import requests
            raise requests.HTTPError(response=self)

    def iter_content(self, chunk_size):
        for i in range(0, len(self._payload), chunk_size):
            yield self._payload[i:i + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _session(payload, status=200):
    session = MagicMock()
    session.get.return_value = _FakeResponse(payload, status)
    return session


class TestSpecs:
    def test_both_directions_are_known(self):
        assert set(MODELS) == {("es", "en"), ("en", "es")}

    def test_hashes_are_real_sha256_hex(self):
        for spec in MODELS.values():
            assert len(spec.sha256) == 64
            int(spec.sha256, 16)

    def test_urls_point_at_this_repository_release(self):
        for spec in MODELS.values():
            assert spec.url.startswith("https://github.com/mondragon-developer/")
            assert "/releases/download/models/" in spec.url
            assert spec.url.endswith(f"{spec.name}-ct2-int8.zip")

    def test_models_live_beside_the_settings_file(self):
        with patch("src.local_mt.default_path") as default_path:
            default_path.return_value = MagicMock(parent=MagicMock())
            default_path.return_value.parent.__truediv__ = lambda self, x: f"P/{x}"
            assert models_dir() == "P/models"


class TestInstall:
    def test_downloads_verifies_and_unpacks(self, tmp_path):
        payload = _zip_bytes()
        spec = _spec(payload)
        folder = install(spec, tmp_path, session=_session(payload))
        assert folder == tmp_path / spec.name
        assert (folder / "model.bin").read_bytes() == b"data:model.bin"
        assert is_installed(spec, tmp_path)

    def test_the_url_fetched_is_the_specs(self, tmp_path):
        payload = _zip_bytes()
        spec = _spec(payload)
        session = _session(payload)
        install(spec, tmp_path, session=session)
        assert session.get.call_args.args[0] == spec.url
        assert session.get.call_args.kwargs["timeout"] > 0

    def test_a_wrong_hash_installs_nothing(self, tmp_path):
        """A swapped file on the server must not reach the app."""
        payload = _zip_bytes()
        spec = ModelSpec("es", "en", "0" * 64, 1)
        with pytest.raises(ValueError, match="verification"):
            install(spec, tmp_path, session=_session(payload))
        assert not is_installed(spec, tmp_path)
        assert list(tmp_path.iterdir()) == []   # no zip, no scratch folder

    def test_an_http_error_installs_nothing(self, tmp_path):
        import requests
        payload = _zip_bytes()
        spec = _spec(payload)
        with pytest.raises(requests.HTTPError):
            install(spec, tmp_path, session=_session(payload, status=404))
        assert list(tmp_path.iterdir()) == []

    def test_an_already_installed_model_is_not_fetched_again(self, tmp_path):
        payload = _zip_bytes()
        spec = _spec(payload)
        install(spec, tmp_path, session=_session(payload))
        session = _session(payload)
        install(spec, tmp_path, session=session)
        session.get.assert_not_called()

    def test_progress_is_reported_with_totals(self, tmp_path):
        payload = _zip_bytes()
        spec = _spec(payload)
        seen = []
        install(spec, tmp_path, session=_session(payload),
                progress=lambda done, total: seen.append((done, total)))
        assert seen[-1] == (len(payload), len(payload))

    def test_a_single_wrapping_folder_is_tolerated(self, tmp_path):
        payload = _zip_bytes(prefix="opus-mt-es-en/")
        spec = _spec(payload)
        install(spec, tmp_path, session=_session(payload))
        assert is_installed(spec, tmp_path)

    def test_an_archive_without_a_model_is_rejected(self, tmp_path):
        payload = _zip_bytes(names=("README.md",))
        spec = _spec(payload)
        with pytest.raises(ValueError, match="does not contain"):
            install(spec, tmp_path, session=_session(payload))
        assert list(tmp_path.iterdir()) == []

    def test_zip_slip_members_never_escape_the_models_folder(self, tmp_path):
        """A member named ../escape must not be written above the folder."""
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for name in ("model.bin", "source.spm", "target.spm"):
                z.writestr(name, b"x")
            z.writestr("../../escape.txt", b"evil")
        payload = buf.getvalue()
        spec = _spec(payload)
        root = tmp_path / "models"
        root.mkdir()
        install(spec, root, session=_session(payload))
        assert not (tmp_path / "escape.txt").exists()
        assert not (tmp_path.parent / "escape.txt").exists()
        assert is_installed(spec, root)

    def test_a_partial_previous_install_is_replaced(self, tmp_path):
        payload = _zip_bytes()
        spec = _spec(payload)
        stale = tmp_path / spec.name
        stale.mkdir()
        (stale / "model.bin").write_bytes(b"half")   # no .spm files
        assert not is_installed(spec, tmp_path)
        install(spec, tmp_path, session=_session(payload))
        assert (stale / "model.bin").read_bytes() == b"data:model.bin"


class TestSplitSentences:
    def test_empty(self):
        assert _split_sentences("  ") == []

    def test_sentence_boundaries(self):
        assert _split_sentences("Hola. ¿Qué tal? Bien!") == \
            ["Hola.", "¿Qué tal?", "Bien!"]


class TestLocalTranslator:
    @pytest.fixture
    def ensure(self, tmp_path):
        ensure = MagicMock(return_value=tmp_path / "opus-mt-es-en")
        return ensure

    def test_empty_input_never_touches_a_model(self, ensure):
        assert LocalTranslator(ensure=ensure).translate("  ", "es", "en") == ""
        ensure.assert_not_called()

    def test_the_model_is_fetched_once_per_direction(self, ensure, tmp_path):
        with patch("src.local_mt._Engine") as engine:
            engine.return_value.translate.return_value = ["Hello."]
            local = LocalTranslator(root=tmp_path, ensure=ensure)
            local.translate("Hola.", "es", "en")
            local.translate("Adiós.", "es", "en")
        ensure.assert_called_once()
        spec, root, _ = ensure.call_args.args
        assert spec is MODELS[("es", "en")]
        assert root == tmp_path

    def test_sentences_are_translated_as_a_batch_and_joined(self, ensure):
        with patch("src.local_mt._Engine") as engine:
            engine.return_value.translate.return_value = ["Hello.", "Bye."]
            local = LocalTranslator(ensure=ensure)
            assert local.translate("Hola. Adiós.", "es", "en") == "Hello. Bye."
        engine.return_value.translate.assert_called_once_with(
            ["Hola.", "Adiós."])

    def test_progress_is_forwarded_to_the_download(self, ensure):
        progress = MagicMock()
        with patch("src.local_mt._Engine") as engine:
            engine.return_value.translate.return_value = ["Hello."]
            LocalTranslator(ensure=ensure).translate("Hola.", "es", "en",
                                                     progress=progress)
        assert ensure.call_args.args[2] is progress

    def test_unknown_direction_is_a_key_error(self, ensure):
        with pytest.raises(KeyError):
            LocalTranslator(ensure=ensure).translate("Bonjour.", "fr", "en")

    def test_is_ready_reflects_the_files_on_disk(self, tmp_path):
        local = LocalTranslator(root=tmp_path)
        assert local.is_ready("es", "en") is False
        folder = tmp_path / "opus-mt-es-en"
        folder.mkdir()
        for name in ("model.bin", "source.spm", "target.spm"):
            (folder / name).write_bytes(b"x")
        assert local.is_ready("es", "en") is True


class TestEngine:
    """The CTranslate2 call shape, with the libraries faked."""

    def test_appends_the_end_of_sentence_marker(self, tmp_path):
        ct2 = MagicMock()
        spm = MagicMock()
        source = MagicMock()
        target = MagicMock()
        spm.SentencePieceProcessor.side_effect = [source, target]
        source.encode.return_value = ["▁Hola", "."]
        hyp = MagicMock(hypotheses=[["▁Hello", "."]])
        ct2.Translator.return_value.translate_batch.return_value = [hyp]
        target.decode.return_value = "Hello."
        with patch.dict("sys.modules", {"ctranslate2": ct2,
                                        "sentencepiece": spm}):
            engine = _Engine(tmp_path)
            assert engine.translate(["Hola."]) == ["Hello."]
        batch = ct2.Translator.return_value.translate_batch.call_args.args[0]
        assert batch == [["▁Hola", ".", "</s>"]]
        ct2.Translator.assert_called_once_with(str(tmp_path), device="cpu",
                                               compute_type="int8")
