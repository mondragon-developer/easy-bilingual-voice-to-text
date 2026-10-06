"""Tests for the web front end's server, with the model and decoder faked.

The real decoder and the real model are covered elsewhere (the selftest and
the transcriber tests); here the question is whether the HTTP layer says the
right things: loading, ready, bad input, the token, and a dictation's shape.
"""

import time
from unittest.mock import MagicMock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from src.translator import Translation
from webapp.server import MAX_UPLOAD_BYTES, create_app

SPEECH = np.ones(16000, dtype=np.float32)


def _transcriber(load_result="CPU (test)", error=None):
    fake = MagicMock()
    fake.model_name = "small"
    if error is not None:
        fake.load.side_effect = error
    else:
        fake.load.return_value = load_result
    fake.transcribe.return_value = ("You you was there.", "en", 0.97, 1.2)
    return fake


@pytest.fixture
def client():
    """A started app whose model has finished 'loading'."""
    app = create_app(transcriber=_transcriber(), decode=lambda raw: SPEECH)
    with TestClient(app) as client:
        _wait_ready(client)
        yield client


def _wait_ready(client, headers=None):
    for _ in range(100):
        if client.get("/api/status", headers=headers or {}).json()["ready"]:
            return
        time.sleep(0.02)
    raise AssertionError("model never became ready")


def _dictate(client, **fields):
    data = {"translate_mode": "off", "tidy_mode": "basic", **fields}
    return client.post("/api/dictate", data=data,
                       files={"clip": ("clip", b"\x00" * 100, "audio/webm")})


class TestStatus:
    def test_reports_ready_with_model_and_device(self, client):
        info = client.get("/api/status").json()
        assert info["ready"] is True
        assert info["device"] == "CPU (test)"
        assert info["model"] == "small"
        assert info["tidy_modes"] == ["off", "basic", "full"]

    def test_a_model_that_fails_to_load_is_reported_not_hidden(self):
        app = create_app(transcriber=_transcriber(error=RuntimeError("no DLL")))
        with TestClient(app) as client:
            for _ in range(100):
                info = client.get("/api/status").json()
                if info["error"]:
                    break
                time.sleep(0.02)
        assert info["ready"] is False
        assert "no DLL" in info["error"]

    def test_the_page_is_served(self, client):
        res = client.get("/")
        assert res.status_code == 200
        assert "<title>Speech to Text</title>" in res.text


class TestDictate:
    def test_returns_both_languages_and_the_engine(self):
        app = create_app(transcriber=_transcriber(), decode=lambda raw: SPEECH)
        with TestClient(app) as client:
            _wait_ready(client)
            res = _dictate(client, translate_mode="off")
        body = res.json()
        assert res.status_code == 200
        assert body["text"] == "You were there."
        assert body["lang"] == "en" and body["lang_name"] == "English"
        assert body["translation"] == ""

    def test_tidy_off_gives_the_words_as_spoken(self, client):
        assert _dictate(client, tidy_mode="off").json()["text"] == \
            "You you was there."

    def test_a_short_clip_is_a_note(self):
        app = create_app(transcriber=_transcriber(),
                         decode=lambda raw: np.zeros(100, dtype=np.float32))
        with TestClient(app) as client:
            _wait_ready(client)
            body = _dictate(client).json()
        assert body["text"] == "" and "too short" in body["note"]

    def test_a_clip_that_does_not_decode_is_a_400(self):
        def bad(raw):
            raise ValueError("not audio")
        app = create_app(transcriber=_transcriber(), decode=bad)
        with TestClient(app) as client:
            _wait_ready(client)
            res = _dictate(client)
        assert res.status_code == 400
        assert "not audio" in res.json()["detail"]

    def test_unknown_modes_are_refused(self, client):
        assert _dictate(client, tidy_mode="loud").status_code == 422
        assert _dictate(client, translate_mode="klingon").status_code == 422

    def test_a_dictation_before_the_model_is_ready_is_a_503(self):
        slow = _transcriber()
        slow.load.side_effect = lambda: time.sleep(0.5) or "CPU"
        app = create_app(transcriber=slow, decode=lambda raw: SPEECH)
        with TestClient(app) as client:
            assert _dictate(client).status_code == 503

    def test_an_oversized_clip_is_refused(self, client):
        res = client.post("/api/dictate", data={"translate_mode": "off"},
                          files={"clip": ("clip", b"\x00" * (MAX_UPLOAD_BYTES + 1),
                                          "audio/webm")})
        assert res.status_code == 413


class TestToken:
    def test_with_a_token_set_every_call_needs_it(self):
        app = create_app(transcriber=_transcriber(), token="s3cret",
                         decode=lambda raw: SPEECH)
        with TestClient(app) as client:
            assert client.get("/api/status").status_code == 401
            assert client.get("/api/status",
                              headers={"X-Token": "wrong"}).status_code == 401
            _wait_ready(client, headers={"X-Token": "s3cret"})
            res = client.post("/api/dictate", data={"translate_mode": "off"},
                              files={"clip": ("clip", b"\x00", "audio/webm")},
                              headers={"X-Token": "s3cret"})
            assert res.status_code == 200
            assert client.get("/").status_code == 200  # the page itself is public

    def test_without_a_token_nothing_is_asked(self, client):
        assert client.get("/api/status").status_code == 200
