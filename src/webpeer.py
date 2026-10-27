"""Passing the speech-model choice on to the phone front end's server.

The web server is a process of its own with its own copy of Whisper, so
switching the desktop window to a lighter model frees nothing while the
server keeps large-v3 on the GPU. The window tells the server too.

The call never leaves this machine: it goes to the loopback address the
server listens on, bypassing any configured proxy, and a server that is not
running is the normal case, not an error.
"""

import json
import os
import urllib.request

WEB_HOST = "127.0.0.1"


def _port_from_env() -> int:
    try:
        return int(os.environ.get("STT_WEB_PORT", "8765"))
    except ValueError:
        return 8765


WEB_PORT = _port_from_env()


def tell_speech_model(mode, port=None, timeout=3.0) -> bool:
    """Ask a running web server to switch to ``mode``.

    Args:
        mode: A key of ``transcriber.MODES``.
        port: The server's port; ``WEB_PORT`` when omitted.
        timeout: Seconds to wait for the server to answer.

    Returns:
        bool: True if a server took the request. False covers no server,
        a refusal and a timeout alike; the caller has nothing to do about
        any of them.
    """
    url = f"http://{WEB_HOST}:{port or WEB_PORT}/api/speech-model"
    request = urllib.request.Request(
        url, data=json.dumps({"mode": mode}).encode("utf-8"),
        headers={"Content-Type": "application/json"}, method="POST")
    # An HTTP_PROXY in the environment would otherwise get this request.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout) as response:
            return 200 <= response.status < 300
    except (OSError, ValueError):
        return False
