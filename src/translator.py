"""EN <-> ES translation via Google (deep-translator, free, no API key).

Only the translation pane needs internet; transcription itself is offline.
Long texts are split at sentence boundaries to stay under Google's
per-request character limit.
"""

import re
from contextlib import contextmanager

import requests
from deep_translator import GoogleTranslator

_MAX_CHARS = 4500  # Google web endpoint rejects requests near 5000 chars

#: Seconds to wait on the translation endpoint before giving up. Kept well
#: above a slow-but-working connection and well below the user's patience.
NETWORK_TIMEOUT = 20.0


@contextmanager
def _request_timeout(seconds):
    """Force a timeout onto deep-translator's HTTP call.

    deep-translator calls ``requests.get()`` without a ``timeout`` and offers
    no way to pass one, and requests waits forever by default. Left alone, a
    captive portal - hotel or airport wifi, where the TCP connection is
    accepted but no reply ever arrives - blocks the worker thread for good.
    The app would keep believing a transcription was in flight and never let
    you record again.

    Note the obvious alternative does **not** work: ``socket.setdefaulttimeout``
    is ignored here, because urllib3 passes its own timeout sentinel down to
    the socket. Measured against a blackholed address with a 3 s socket
    default, the call still took 75 s. Wrapping the function is what actually
    bounds it.

    Patching a module global is only safe because this is the app's single
    network call and no two translations overlap: ``_processing`` gates the
    recorder, and the one-time model download finishes before recording is
    ever enabled.

    Args:
        seconds: Timeout applied to any request made inside the block.
    """
    original = requests.get

    def _get_with_timeout(*args, **kwargs):
        kwargs.setdefault("timeout", seconds)
        return original(*args, **kwargs)

    requests.get = _get_with_timeout
    try:
        yield
    finally:
        requests.get = original


def _split_chunks(text: str, limit: int = _MAX_CHARS):
    """Split text into chunks below a character limit.

    Prefers breaking at sentence boundaries (., !, ?, …); a single sentence
    longer than the limit is hard-split at the limit.

    Args:
        text: The text to split.
        limit: Maximum characters per chunk.

    Returns:
        list[str]: Ordered, non-empty chunks (empty list for empty input).
    """
    sentences = re.split(r"(?<=[.!?…])\s+", text)
    chunks, current = [], ""
    for sentence in sentences:
        # Hard-split any single sentence that is itself over the limit.
        while len(sentence) > limit:
            head, sentence = sentence[:limit], sentence[limit:]
            if current:
                chunks.append(current)
                current = ""
            chunks.append(head)
        if current and len(current) + len(sentence) + 1 > limit:
            chunks.append(current)
            current = sentence
        else:
            current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current)
    return chunks


def translate(text: str, target: str) -> str:
    """Translate text into the target language.

    Args:
        text: Text to translate; the source language is auto-detected.
        target: Target language code, e.g. ``"en"`` or ``"es"``.

    Returns:
        str: The translated text ("" for empty input).

    Raises:
        Exception: Propagates deep-translator/network errors (e.g. offline, or
            a timeout after ``NETWORK_TIMEOUT`` seconds); the caller decides
            how to surface them.
    """
    text = text.strip()
    if not text:
        return ""
    translator = GoogleTranslator(source="auto", target=target)
    with _request_timeout(NETWORK_TIMEOUT):
        parts = [translator.translate(chunk) or ""
                 for chunk in _split_chunks(text)]
    return " ".join(part.strip() for part in parts if part).strip()
