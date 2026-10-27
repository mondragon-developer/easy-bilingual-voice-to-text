"""Tests for the web front end's server, with the model and decoder faked.

The real decoder and the real model are covered elsewhere (the selftest and
the transcriber tests); here the question is whether the HTTP layer says the
right things: loading, ready, bad input, the token, and a dictation's shape.
"""

import base64
import threading
import time
from unittest.mock import MagicMock

import numpy as np
import pytest

# The web front end has its own requirements file; without it (CI installs
# only the desktop app's) these tests are skipped rather than failed.
pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from src.transcriber import ModelNotLoaded
from src.translator import Translation
from webapp.server import MAX_CLIP_CHARS, MAX_UPLOAD_BYTES, create_app

SPEECH = np.ones(16000, dtype=np.float32)
LOCAL = ("127.0.0.1", 50000)
REMOTE = ("203.0.113.9", 50000)


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
    """A started app whose model has finished 'loading', used from the PC
    itself (the test client's default peer address is not loopback, and
    would count as remote)."""
    app = create_app(transcriber=_transcriber(), decode=lambda raw: SPEECH)
    with TestClient(app, client=LOCAL) as client:
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
        with TestClient(app, client=LOCAL) as client:
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
        with TestClient(app, client=LOCAL) as client:
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
        with TestClient(app, client=LOCAL) as client:
            _wait_ready(client)
            body = _dictate(client).json()
        assert body["text"] == "" and "too short" in body["note"]

    def test_a_clip_that_does_not_decode_is_a_400(self):
        def bad(raw):
            raise ValueError("not audio")
        app = create_app(transcriber=_transcriber(), decode=bad)
        with TestClient(app, client=LOCAL) as client:
            _wait_ready(client)
            res = _dictate(client)
        assert res.status_code == 400
        assert "not audio" in res.json()["detail"]

    def test_unknown_modes_are_refused(self, client):
        assert _dictate(client, tidy_mode="loud").status_code == 422
        assert _dictate(client, translate_mode="klingon").status_code == 422

    def test_a_dictation_before_the_model_is_ready_is_a_503(self):
        slow = _transcriber()
        slow.load.side_effect = lambda mode: time.sleep(0.5) or "CPU"
        app = create_app(transcriber=slow, decode=lambda raw: SPEECH)
        with TestClient(app, client=LOCAL) as client:
            assert _dictate(client).status_code == 503

    def test_an_oversized_clip_is_refused(self, client):
        res = client.post("/api/dictate", data={"translate_mode": "off"},
                          files={"clip": ("clip", b"\x00" * (MAX_UPLOAD_BYTES + 1),
                                          "audio/webm")})
        assert res.status_code == 413


def _basic(user, password):
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class TestRemoteGuard:
    """Local use never signs in; remote use cannot happen without
    credentials, and needs them once they exist."""

    def _app(self, **remote):
        return create_app(transcriber=_transcriber(), decode=lambda raw: SPEECH,
                          **remote)

    def test_local_use_never_signs_in_even_with_credentials_set(self):
        app = self._app(remote_user="jmond", remote_password="pw")
        with TestClient(app, client=LOCAL) as client:
            assert client.get("/").status_code == 200
            assert client.get("/api/status").status_code == 200

    def test_remote_is_refused_outright_while_credentials_are_unset(self):
        with TestClient(self._app(), client=REMOTE) as client:
            res = client.get("/api/status")
        assert res.status_code == 403
        assert "WWW-Authenticate" not in res.headers

    def test_remote_is_asked_to_sign_in(self):
        app = self._app(remote_user="jmond", remote_password="pw")
        with TestClient(app, client=REMOTE) as client:
            res = client.get("/")
            assert res.status_code == 401
            assert res.headers["WWW-Authenticate"].startswith("Basic ")
            assert client.get("/api/status",
                              headers=_basic("jmond", "wrong")).status_code == 401
            assert client.get("/api/status",
                              headers=_basic("other", "pw")).status_code == 401
            assert client.get("/api/status",
                              headers={"Authorization": "Bearer x"}).status_code == 401

    def test_remote_with_the_right_credentials_gets_through(self):
        app = self._app(remote_user="jmond", remote_password="pw")
        with TestClient(app, client=REMOTE) as client:
            auth = _basic("jmond", "pw")
            _wait_ready(client, headers=auth)
            res = client.post("/api/dictate", data={"translate_mode": "off"},
                              files={"clip": ("clip", b"\x00", "audio/webm")},
                              headers=auth)
        assert res.status_code == 200

    def test_tunnel_traffic_from_loopback_counts_as_remote(self):
        # cloudflared runs on this PC and connects from 127.0.0.1; the
        # CF-Connecting-IP header is what says the request came from outside.
        app = self._app(remote_user="jmond", remote_password="pw")
        with TestClient(app, client=LOCAL) as client:
            res = client.get("/api/status", headers={"CF-Connecting-IP": "1.2.3.4"})
            assert res.status_code == 401
            res = client.get("/api/status", headers={"CF-Connecting-IP": "1.2.3.4",
                                                     **_basic("jmond", "pw")})
            assert res.status_code == 200

    def test_half_set_credentials_count_as_unset(self):
        with TestClient(self._app(remote_user="jmond"), client=REMOTE) as client:
            assert client.get("/api/status").status_code == 403

    def test_extra_accounts_sign_in_too(self):
        app = self._app(remote_user="jmond", remote_password="pw",
                        remote_users="guest:welcome, friend:hello")
        with TestClient(app, client=REMOTE) as client:
            for user, password in (("jmond", "pw"), ("guest", "welcome"),
                                   ("friend", "hello")):
                assert client.get("/api/status",
                                  headers=_basic(user, password)).status_code == 200
            assert client.get("/api/status",
                              headers=_basic("guest", "pw")).status_code == 401
            assert client.get("/api/status",
                              headers=_basic("nobody", "welcome")).status_code == 401

    def test_extra_accounts_alone_are_enough(self):
        app = self._app(remote_users="guest:welcome")
        with TestClient(app, client=REMOTE) as client:
            assert client.get("/api/status").status_code == 401
            assert client.get("/api/status",
                              headers=_basic("guest", "welcome")).status_code == 200

    def test_a_half_written_extra_account_is_ignored(self):
        with TestClient(self._app(remote_users="guest:, :pw, junk"),
                        client=REMOTE) as client:
            assert client.get("/api/status").status_code == 403

    def test_the_status_says_whether_remote_access_is_on(self):
        assert self._app().state.remote_enabled is False
        assert self._app(remote_user="a", remote_password="b").state.remote_enabled is True


class TestSpeechModelSwitch:
    """The desktop window's Best / Light / CPU only switch reaches the
    server, so freeing the GPU frees it of both copies of Whisper. The page
    has the switch too, for the PC and the owner's account only."""

    def _app(self, transcriber=None, **kwargs):
        return create_app(transcriber=transcriber or _transcriber(),
                          decode=lambda raw: SPEECH, **kwargs)

    @staticmethod
    def _switch(client, mode, **kwargs):
        return client.post("/api/speech-model", json={"mode": mode}, **kwargs)

    def test_the_start_up_model_is_the_one_asked_for(self):
        fake = _transcriber()
        with TestClient(self._app(fake, speech_model="light"),
                        client=LOCAL) as client:
            _wait_ready(client)
            assert client.get("/api/status").json()["speech_model"] == "light"
        fake.load.assert_called_once_with("light")

    def test_an_unknown_start_up_model_means_best(self):
        fake = _transcriber()
        with TestClient(self._app(fake, speech_model="huge"),
                        client=LOCAL) as client:
            _wait_ready(client)
        fake.load.assert_called_once_with("best")

    def test_a_local_switch_reloads(self):
        fake = _transcriber()
        with TestClient(self._app(fake), client=LOCAL) as client:
            _wait_ready(client)
            res = self._switch(client, "cpu")
            assert res.status_code == 202
            _wait_ready(client)
            info = client.get("/api/status").json()
        assert info["speech_model"] == "cpu"
        assert [c.args for c in fake.load.call_args_list] == \
            [("best",), ("cpu",)]

    def test_the_grammar_pipeline_survives_a_switch(self):
        app = self._app()
        with TestClient(app, client=LOCAL) as client:
            _wait_ready(client)
            first = _dictate(client, tidy_mode="off")
            self._switch(client, "light")
            _wait_ready(client)
            second = _dictate(client, tidy_mode="off")
        assert first.status_code == second.status_code == 200

    def test_the_same_model_again_is_not_a_reload(self):
        fake = _transcriber()
        with TestClient(self._app(fake), client=LOCAL) as client:
            _wait_ready(client)
            self._switch(client, "best")
        fake.load.assert_called_once_with("best")

    def test_quick_switches_end_on_the_last_one(self):
        """A switch landing mid-load must not be overtaken by the load it
        interrupted."""
        gate = threading.Event()
        loaded = []
        fake = _transcriber()

        def load(mode):
            if mode == "best":
                gate.wait(5)
            loaded.append(mode)
            return mode
        fake.load.side_effect = load
        with TestClient(self._app(fake), client=LOCAL) as client:
            self._switch(client, "light")
            self._switch(client, "cpu")
            gate.set()
            _wait_ready(client)
            info = client.get("/api/status").json()
        assert info["speech_model"] == "cpu"
        assert info["device"] == "cpu"
        assert loaded[-1] == "cpu"

    def test_unknown_models_are_refused(self, client):
        assert self._switch(client, "huge").status_code == 422

    def test_a_form_post_is_refused(self, client):
        """A JSON body is what keeps a web page from switching the model
        cross-origin; a form needs no preflight."""
        res = client.post("/api/speech-model", data={"mode": "cpu"})
        assert res.status_code == 422

    def test_the_owner_can_switch_from_a_phone(self):
        fake = _transcriber()
        app = self._app(fake, remote_user="jmond", remote_password="pw",
                        remote_users="guest:welcome")
        auth = _basic("jmond", "pw")
        with TestClient(app, client=REMOTE) as client:
            _wait_ready(client, headers=auth)
            assert client.get("/api/status", headers=auth).json()["can_switch"] is True
            assert self._switch(client, "light", headers=auth).status_code == 202
            _wait_ready(client, headers=auth)
        assert fake.load.call_args.args == ("light",)

    def test_a_guest_cannot_switch(self):
        fake = _transcriber()
        app = self._app(fake, remote_user="jmond", remote_password="pw",
                        remote_users="guest:welcome")
        auth = _basic("guest", "welcome")
        with TestClient(app, client=REMOTE) as client:
            _wait_ready(client, headers=auth)
            assert client.get("/api/status", headers=auth).json()["can_switch"] is False
            assert self._switch(client, "cpu", headers=auth).status_code == 403
        fake.load.assert_called_once_with("best")

    def test_a_guest_through_the_tunnel_cannot_switch_either(self):
        app = self._app(remote_user="jmond", remote_password="pw",
                        remote_users="guest:welcome")
        with TestClient(app, client=LOCAL) as client:
            res = self._switch(client, "cpu", headers={
                "CF-Connecting-IP": "1.2.3.4", **_basic("guest", "welcome")})
        assert res.status_code == 403

    def test_with_no_main_account_nobody_remote_can_switch(self):
        app = self._app(remote_users="jmond:pw")
        with TestClient(app, client=REMOTE) as client:
            res = self._switch(client, "cpu", headers=_basic("jmond", "pw"))
        assert res.status_code == 403

    def test_the_pc_itself_can_always_switch(self, client):
        assert client.get("/api/status").json()["can_switch"] is True

    def test_a_dictation_caught_by_a_switch_is_a_503(self):
        fake = _transcriber()
        fake.transcribe.side_effect = ModelNotLoaded("switching")
        with TestClient(self._app(fake), client=LOCAL) as client:
            _wait_ready(client)
            res = _dictate(client)
        assert res.status_code == 503
        assert "switching" in res.json()["detail"]


class TestClipboard:
    """On the PC the server sets the clipboard, because the browser may
    not once the focus has moved to the window being pasted into."""

    def _app(self, copied, works=True, **kwargs):
        def fake(text):
            copied.append(text)
            return works
        return create_app(transcriber=_transcriber(), decode=lambda raw: SPEECH,
                          copy_to_clipboard=fake, **kwargs)

    def test_a_page_on_the_pc_gets_the_pc_clipboard(self):
        copied = []
        with TestClient(self._app(copied), client=LOCAL) as client:
            assert client.get("/api/status").json()["pc_clipboard"] is True
            res = client.post("/api/clipboard", json={"text": "Hola, ¿qué tal?"})
        assert res.status_code == 200
        assert copied == ["Hola, ¿qué tal?"]

    def test_a_signed_in_phone_does_not(self):
        copied = []
        app = self._app(copied, remote_user="jmond", remote_password="pw")
        auth = _basic("jmond", "pw")
        with TestClient(app, client=REMOTE) as client:
            assert client.get("/api/status", headers=auth).json()["pc_clipboard"] is False
            res = client.post("/api/clipboard", json={"text": "x"}, headers=auth)
        assert res.status_code == 403
        assert copied == []

    def test_tunnel_traffic_does_not_either(self):
        copied = []
        app = self._app(copied, remote_user="jmond", remote_password="pw")
        with TestClient(app, client=LOCAL) as client:
            res = client.post("/api/clipboard", json={"text": "x"}, headers={
                "CF-Connecting-IP": "1.2.3.4", **_basic("jmond", "pw")})
        assert res.status_code == 403
        assert copied == []

    def test_a_form_post_is_refused(self):
        """Another web page could send a form without a preflight."""
        copied = []
        with TestClient(self._app(copied), client=LOCAL) as client:
            res = client.post("/api/clipboard", data={"text": "x"})
        assert res.status_code == 422
        assert copied == []

    def test_a_clipboard_that_cannot_be_opened_is_a_503(self):
        with TestClient(self._app([], works=False), client=LOCAL) as client:
            res = client.post("/api/clipboard", json={"text": "x"})
        assert res.status_code == 503

    def test_oversized_text_is_refused(self):
        copied = []
        with TestClient(self._app(copied), client=LOCAL) as client:
            res = client.post("/api/clipboard",
                              json={"text": "x" * (MAX_CLIP_CHARS + 1)})
        assert res.status_code == 413
        assert copied == []
