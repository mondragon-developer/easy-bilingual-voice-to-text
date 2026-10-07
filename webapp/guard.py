"""Who may talk to the server: anyone on this PC, and remote users with a
password.

Two invariants, in that order of importance:

1. Local use never asks for a sign-in. A browser on the PC itself opens the
   page and records, no prompt.
2. Remote use is impossible with the credentials unset. An exposed port, a
   tunnel started by mistake, a forgotten config: none of them opens the
   microphone endpoint to the world. Remote requests get 403 until a user
   name and password exist, and 401 until they are presented.

A request is remote when its TCP peer is not loopback, or when it carries
the ``CF-Connecting-IP`` header. The header matters because a Cloudflare
Tunnel connector runs on this same PC and reaches the server from loopback,
so the address alone cannot tell tunnel traffic from a local browser.

HTTP Basic is the mechanism because the browser does the whole job: it
prompts once, remembers, and sends the credentials with every fetch the page
makes, including from the installed home-screen app.
"""

import base64
import hmac
from pathlib import Path

from fastapi import Request
from fastapi.responses import PlainTextResponse

REALM = "Speech to Text"
_LOOPBACK = {"127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost"}


def load_env(path) -> dict:
    """Read ``KEY=value`` lines from a ``.env`` file, if it exists.

    Blank lines and ``#`` comments are skipped; surrounding quotes on a
    value are removed. No interpolation, no export keyword: the file holds
    two settings and nothing fancier is wanted.
    """
    values = {}
    path = Path(path)
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def is_remote(client_host, headers) -> bool:
    """Whether a request came from somewhere other than this PC."""
    if headers.get("cf-connecting-ip"):
        return True
    return client_host not in _LOOPBACK


def credentials_match(authorization, user, password) -> bool:
    """Whether an ``Authorization`` header carries exactly ``user:password``.

    Both halves are compared in constant time, and a header that is not
    well-formed Basic auth is simply a mismatch.
    """
    if not authorization or not user or not password:
        return False
    scheme, _, encoded = authorization.partition(" ")
    if scheme.lower() != "basic" or not encoded:
        return False
    try:
        decoded = base64.b64decode(encoded.strip(), validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return False
    given_user, _, given_password = decoded.partition(":")
    user_ok = hmac.compare_digest(given_user.encode(), user.encode())
    password_ok = hmac.compare_digest(given_password.encode(), password.encode())
    return user_ok and password_ok


def install(app, user, password):
    """Put the guard in front of every route of ``app``.

    Args:
        app: The FastAPI application.
        user: Remote user name, or empty to refuse all remote use.
        password: Remote password, or empty to refuse all remote use.
    """
    enabled = bool(user and password)

    @app.middleware("http")
    async def _guard(request: Request, call_next):
        host = request.client.host if request.client else None
        if not is_remote(host, request.headers):
            return await call_next(request)
        if not enabled:
            return PlainTextResponse(
                "Remote access is off on this server.", status_code=403)
        if credentials_match(request.headers.get("authorization"),
                             user, password):
            return await call_next(request)
        return PlainTextResponse(
            "Sign in to use this server.", status_code=401,
            headers={"WWW-Authenticate": f'Basic realm="{REALM}"'})

    return enabled
