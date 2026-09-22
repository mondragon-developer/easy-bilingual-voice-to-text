"""EN <-> ES translation: on this machine, or online with fallbacks.

Three modes, chosen in the bottom bar and stored in settings:

- ``off``: nothing is translated.
- ``offline``: OPUS-MT models run here through CTranslate2 (see
  ``local_mt``). The only network use is the one-time model download.
- ``online``: Google's free web endpoint, which reads best. It rate-limits
  by public IP, so on a shared network (a school, an office) it answers 429
  to everyone at once; when that happens the text goes to MyMemory, and if
  that fails too, to the offline model. The result says which engine made
  it, so the status bar can be honest about what happened.

Long texts are split at sentence boundaries to stay under each service's
per-request character limit.
"""

import re
from contextlib import contextmanager
from dataclasses import dataclass

import requests
from deep_translator import GoogleTranslator, MyMemoryTranslator
from deep_translator.exceptions import TooManyRequests

#: Settings values for the translation mode, in the order the UI shows them.
MODES = ("off", "offline", "online")

_MAX_CHARS = 4500  # Google web endpoint rejects requests near 5000 chars
_MYMEMORY_MAX_CHARS = 450  # MyMemory refuses anything over 500

#: MyMemory wants a locale, not a bare language code.
_MYMEMORY_LOCALES = {"en": "en-US", "es": "es-ES"}

#: Seconds to wait on a translation endpoint before giving up. Kept well
#: above a slow-but-working connection and well below the user's patience.
NETWORK_TIMEOUT = 20.0

#: Engine names as the status bar shows them.
ENGINE_GOOGLE = "Google"
ENGINE_MYMEMORY = "MyMemory"
ENGINE_OFFLINE = "offline"

#: The one ``LocalTranslator`` every translation shares, created on first
#: use. It caches a loaded CTranslate2 model per direction, so making a new
#: one per call would reload the model for every recording.
_shared_local = None


def _default_local():
    global _shared_local
    if _shared_local is None:
        from .local_mt import LocalTranslator
        _shared_local = LocalTranslator()
    return _shared_local


@dataclass(frozen=True)
class Translation:
    """A finished translation and the engine that produced it."""

    text: str
    engine: str


class TranslationError(Exception):
    """Every engine that was tried failed; ``str()`` says why, per engine."""


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

    Patching a module global is only safe because no two translations ever
    overlap: ``_processing`` gates the recorder, the engines in a chain run
    one after another, and the model downloads (Whisper's before recording
    is enabled, the offline translator's outside this block) pass their own
    timeouts.

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


def _join(parts):
    return " ".join(part.strip() for part in parts if part).strip()


def translate_google(text: str, source: str, target: str) -> str:
    """Google's free web endpoint. Best quality; rate-limited per public IP.

    Raises:
        Exception: Propagates deep-translator/network errors (offline, a 429
            from a shared network, or a timeout after ``NETWORK_TIMEOUT``).
    """
    translator = GoogleTranslator(source=source, target=target)
    with _request_timeout(NETWORK_TIMEOUT):
        parts = [translator.translate(chunk) or ""
                 for chunk in _split_chunks(text)]
    return _join(parts)


def translate_mymemory(text: str, source: str, target: str) -> str:
    """MyMemory, the fallback when Google refuses. Small daily quota per IP.

    MyMemory reports an exhausted quota as a *successful* response whose
    translation is a warning sentence in capitals. Passing that through
    would put the warning in the Spanish pane, so it is raised instead.
    """
    translator = MyMemoryTranslator(source=_MYMEMORY_LOCALES[source],
                                    target=_MYMEMORY_LOCALES[target])
    parts = []
    with _request_timeout(NETWORK_TIMEOUT):
        for chunk in _split_chunks(text, _MYMEMORY_MAX_CHARS):
            part = translator.translate(chunk) or ""
            if part.upper().startswith("MYMEMORY WARNING"):
                raise TooManyRequests()
            parts.append(part)
    return _join(parts)


def describe_failure(exc) -> str:
    """One short reason a user can act on, from whatever an engine raised."""
    if isinstance(exc, TooManyRequests):
        return "rate-limited (too many requests from this network today)"
    if isinstance(exc, (requests.ConnectionError, requests.Timeout)):
        return "no connection"
    if isinstance(exc, requests.HTTPError):
        status = getattr(getattr(exc, "response", None), "status_code", "?")
        return f"server answered HTTP {status}"
    if isinstance(exc, ValueError):
        return str(exc)
    return f"{type(exc).__name__}"


def translate(text: str, source: str, target: str, mode: str = "online",
              local=None, progress=None) -> Translation:
    """Translate ``text`` the way ``mode`` asks, falling back as needed.

    Args:
        text: Text in ``source``.
        source: Language spoken, ``"en"`` or ``"es"``.
        target: The other pane's language.
        mode: ``"offline"`` or ``"online"``; ``"off"`` is an error here,
            because the caller should not have asked.
        local: A ``LocalTranslator``. When omitted, one shared instance is
            created on first use and kept, so importing this module never
            loads CTranslate2 and a loaded model is never loaded twice.
        progress: Passed to the offline model download when one happens.

    Returns:
        Translation: The text and the engine that produced it.

    Raises:
        TranslationError: Every engine in the chain failed. The message lists
            each engine and why.
        ValueError: ``mode`` is not ``offline`` or ``online``.
    """
    text = text.strip()
    if not text:
        return Translation("", ENGINE_OFFLINE)
    if mode == "offline":
        chain = [(ENGINE_OFFLINE, None)]
    elif mode == "online":
        chain = [(ENGINE_GOOGLE, translate_google),
                 (ENGINE_MYMEMORY, translate_mymemory),
                 (ENGINE_OFFLINE, None)]
    else:
        raise ValueError(f"cannot translate in mode {mode!r}")

    failures = []
    for engine, func in chain:
        try:
            if func is None:
                if local is None:
                    local = _default_local()
                result = local.translate(text, source, target,
                                         progress=progress)
            else:
                result = func(text, source, target)
        except Exception as exc:  # noqa: BLE001 - next engine gets a go
            failures.append(f"{engine}: {describe_failure(exc)}")
            continue
        if result:
            return Translation(result, engine)
        failures.append(f"{engine}: empty reply")
    raise TranslationError("; ".join(failures))
