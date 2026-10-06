"""Audio in, both languages out, with no window involved.

The desktop app runs this same sequence inside ``app._process_audio``,
interleaved with status-bar updates. This is the sequence on its own:
transcribe, tidy, correct the grammar, translate. It exists so a second
front end (the web app) can dictate without copying that logic, and so the
sequence itself can be tested without a Tk window.

Every collaborator is injected and has a working default, in the same way
``SpeechToTextApp`` takes its parts, so a test can hand in fakes and the
real thing needs no arguments.
"""

import threading
from dataclasses import dataclass, field

from .cleanup import tidy
from .grammar import LocalGrammar
from .languages import DEFAULT_LANG, counterpart
from .translator import describe_failure, translate


@dataclass(frozen=True)
class Dictation:
    """What one recording produced.

    Attributes:
        text: The spoken text, tidied as the settings asked.
        lang: Its language, ``"en"`` or ``"es"``.
        probability: Confidence of the language detection, 0 to 1.
        duration: Seconds of audio.
        translation: The other language, or ``""`` when translation is off
            or failed.
        engine: Which translator answered (``"offline"``, ``"Google"``,
            ``"MyMemory"``), or ``""`` when there is no translation.
        notes: Anything that was skipped and why, one entry each, for the
            status line: a grammar model that could not be fetched, a
            translation that failed.
    """

    text: str
    lang: str
    probability: float
    duration: float
    translation: str = ""
    engine: str = ""
    notes: tuple = field(default_factory=tuple)


class Pipeline:
    """Runs one recording through transcription, tidying and translation."""

    def __init__(self, transcriber, translator=translate, grammar=None):
        """
        Args:
            transcriber: A loaded ``Transcriber`` (or anything with its
                ``transcribe`` method). Loading is the caller's business:
                it is slow, and when it happens is a front-end decision.
            translator: Callable ``(text, source, target, mode, progress)
                -> Translation``; see ``translator.translate``.
            grammar: Object with the ``LocalGrammar`` interface.
        """
        self._transcriber = transcriber
        self._translate = translator
        self._grammar = grammar if grammar is not None else LocalGrammar()
        # One recording at a time: the transcriber is a single model on a
        # single device, and the translator patches a module global.
        self._lock = threading.Lock()

    def run(self, audio, translate_mode="offline", tidy_mode="basic",
            progress=None) -> Dictation:
        """Dictate one recording.

        Args:
            audio: 1-D float32 samples at 16 kHz.
            translate_mode: ``"off"``, ``"offline"`` or ``"online"``.
            tidy_mode: ``"off"``, ``"basic"`` or ``"full"``.
            progress: Optional ``callable(what, done, total)`` for the
                one-time model downloads; ``what`` names the model.

        Returns:
            Dictation: Empty ``text`` means no speech was detected.
        """
        with self._lock:
            return self._run(audio, translate_mode, tidy_mode, progress)

    def _run(self, audio, translate_mode, tidy_mode, progress):
        text, lang, prob, duration = self._transcriber.transcribe(audio)
        if tidy_mode != "off":
            text = tidy(text, lang)
        if not text:
            return Dictation("", lang, prob, duration)

        notes = []
        if tidy_mode == "full" and lang == DEFAULT_LANG:
            try:
                text = self._grammar.correct(
                    text, progress=_named(progress, "the grammar model"))
            except Exception as exc:  # noqa: BLE001 - reported, not fatal
                notes.append(f"grammar check skipped: {describe_failure(exc)}")

        if translate_mode == "off":
            return Dictation(text, lang, prob, duration, notes=tuple(notes))

        other = counterpart(lang)
        try:
            result = self._translate(
                text, source=lang, target=other, mode=translate_mode,
                progress=_named(progress,
                                f"the offline translator, {lang} to {other}"))
        except Exception as exc:  # noqa: BLE001 - reported, not fatal
            notes.append(f"translation failed: {exc}")
            return Dictation(text, lang, prob, duration, notes=tuple(notes))
        return Dictation(text, lang, prob, duration, result.text,
                         result.engine, tuple(notes))


def _named(progress, what):
    """Bind the model's name into a two-argument download callback."""
    if progress is None:
        return None
    return lambda done, total: progress(what, done, total)
