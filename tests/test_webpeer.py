"""Tests for src.webpeer, against a throwaway HTTP server on loopback."""

import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from src import webpeer


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@pytest.fixture
def server():
    """A server that records what it is sent and answers with ``status``."""
    seen = []

    class Handler(BaseHTTPRequestHandler):
        status = 202

        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            seen.append((self.path, self.headers["Content-Type"],
                         json.loads(body)))
            self.send_response(Handler.status)
            self.end_headers()

        def log_message(self, *args):
            pass

    httpd = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    try:
        yield httpd.server_address[1], seen, Handler
    finally:
        httpd.shutdown()
        httpd.server_close()


def test_sends_the_mode_as_json(server):
    port, seen, _ = server
    assert webpeer.tell_speech_model("light", port=port) is True
    assert seen == [("/api/speech-model", "application/json",
                     {"mode": "light"})]


def test_no_server_is_simply_false():
    assert webpeer.tell_speech_model("cpu", port=_free_port(),
                                     timeout=1) is False


def test_a_refusal_is_false_not_an_exception(server):
    port, _, handler = server
    handler.status = 403
    assert webpeer.tell_speech_model("cpu", port=port) is False


def test_a_configured_proxy_is_not_used(server, monkeypatch):
    """The request is for this machine; a proxy would at best fail it and
    at worst see it."""
    monkeypatch.setenv("HTTP_PROXY", f"http://127.0.0.1:{_free_port()}")
    monkeypatch.setenv("NO_PROXY", "")
    port, seen, _ = server
    assert webpeer.tell_speech_model("best", port=port) is True
    assert seen


def test_a_bad_port_setting_falls_back(monkeypatch):
    monkeypatch.setenv("STT_WEB_PORT", "not-a-port")
    assert webpeer._port_from_env() == 8765
