"""``python -m webapp``: serve the web front end on localhost."""

import os

import uvicorn

from .server import create_app

#: Localhost only. Tailscale (``tailscale serve``) is what exposes it to the
#: phone, over HTTPS, to this account's devices and no one else. Binding
#: wider than this would put the microphone endpoint on the LAN unprotected.
HOST = "127.0.0.1"
PORT = int(os.environ.get("STT_WEB_PORT", "8765"))

#: Optional second lock, for anyone who later exposes the server beyond
#: their own devices: with it set, every API call must carry the token.
TOKEN = os.environ.get("STT_WEB_TOKEN") or None

if __name__ == "__main__":
    uvicorn.run(create_app(token=TOKEN), host=HOST, port=PORT,
                log_level="info")
