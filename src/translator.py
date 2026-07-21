"""EN <-> ES translation via Google (deep-translator, free, no API key).

Only the translation pane needs internet; transcription itself is offline.
Long texts are split at sentence boundaries to stay under Google's
per-request character limit.
"""

import re

from deep_translator import GoogleTranslator

_MAX_CHARS = 4500  # Google web endpoint rejects requests near 5000 chars


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
        Exception: Propagates deep-translator/network errors (e.g. offline);
            the caller decides how to surface them.
    """
    text = text.strip()
    if not text:
        return ""
    translator = GoogleTranslator(source="auto", target=target)
    parts = [translator.translate(chunk) or "" for chunk in _split_chunks(text)]
    return " ".join(part.strip() for part in parts if part).strip()
