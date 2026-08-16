"""The languages the app shows, and the pairing between them.

Every assumption that this app is bilingual lives here. It used to be spread
across six places in two modules - the pane loop, three copies of
``"es" if lang == "en" else "en"``, and the detector's own mapping - so adding
a language meant finding all of them.

Supporting a third language is still a design change, not a config change:
two panes cannot show three languages, and ``counterpart`` has no meaning
beyond a pair. Centralising it does not make that free. What it does is put
the whole decision in one file, where the shape of the work is visible.
"""

#: Display names for the languages with a pane, in pane order.
LANG_NAMES = {"en": "English", "es": "Español"}

#: Pane order, left to right.
PANE_ORDER = ("en", "es")

#: Used when the detector reports something we have no pane for.
DEFAULT_LANG = "en"


def normalise(detected: str) -> str:
    """Map a detected language code onto a language with a pane.

    Whisper recognises ~99 languages; only these have somewhere to go. Anything
    else lands in the default pane, so text is never dropped on the floor.

    Args:
        detected: Language code from the transcriber, e.g. ``"es"``, ``"fr"``.

    Returns:
        str: A key of ``LANG_NAMES``.
    """
    return detected if detected in LANG_NAMES else DEFAULT_LANG


def counterpart(lang: str) -> str:
    """The other pane's language.

    Args:
        lang: A key of ``LANG_NAMES``.

    Returns:
        str: The key of the pane that receives the translation.

    Raises:
        KeyError: If ``lang`` has no pane.
    """
    if lang not in LANG_NAMES:
        raise KeyError(lang)
    return next(other for other in PANE_ORDER if other != lang)
