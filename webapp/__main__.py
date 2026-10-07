"""``python -m webapp``: serve the web front end on localhost."""

import os
from pathlib import Path

import uvicorn

from .guard import load_env
from .server import create_app

#: Localhost only. What exposes it to a phone is a tunnel or Tailscale,
#: both of which reach it from this machine; and the guard in ``guard``
#: makes any remote request sign in. Binding wider than this would put the
#: microphone endpoint on the LAN with only the password in the way.
HOST = "127.0.0.1"
PORT = int(os.environ.get("STT_WEB_PORT", "8765"))

#: Remote credentials come from the environment, or from a ``.env`` in the
#: project folder (gitignored) so a log-on launcher need not know them.
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


def _setting(name, env):
    return os.environ.get(name) or env.get(name, "")


if __name__ == "__main__":
    env = load_env(ENV_FILE)
    app = create_app(remote_user=_setting("STT_REMOTE_USER", env),
                     remote_password=_setting("STT_REMOTE_PASSWORD", env),
                     remote_users=_setting("STT_REMOTE_USERS", env))
    print("Remote access:",
          "enabled (sign-in required)" if app.state.remote_enabled
          else "off (STT_REMOTE_USER / STT_REMOTE_PASSWORD not set)",
          flush=True)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
