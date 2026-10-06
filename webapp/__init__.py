"""The web front end: the same dictation, from a phone.

Everything heavy stays on this computer. The browser is a microphone and a
screen: it records a clip, posts it here, and shows what comes back. The
server is a thin layer over ``src.pipeline`` and shares every model with
the desktop app; it never touches ``src.app``, so the desktop app is
unchanged whether or not this package exists.

Run with ``python -m webapp``. It listens on localhost only, on purpose:
reaching it from a phone goes through Tailscale (see the README), which
adds device authentication and the HTTPS that browsers demand before they
will open a microphone.
"""
