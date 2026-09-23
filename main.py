"""Entry point for the EN/ES speech-to-text app.

Run the app:       python main.py   (or SpeechToText.exe)
Verify a build:    SpeechToText.exe --selftest
                   Loads the real Whisper model and transcribes a test tone,
                   then runs one sentence through the offline translator,
                   without opening a window; exits 0 on success, 1 on
                   failure. CI runs this on every release so a build whose
                   models cannot load can never ship.

                   The translator's model is a one-time 68 MB download. With
                   no network and no model, that leg is reported as skipped
                   rather than failed, so the health check still tells the
                   truth about an installed app. CI sets STT_SELFTEST_STRICT=1,
                   where a skip is a failure: a release must prove the whole
                   path.
"""

import os
import sys


def _report(message: str):
    """Print if a console exists, and always append to selftest.log
    (windowed PyInstaller builds have no usable stdout)."""
    try:
        print(message, flush=True)
    except Exception:
        pass
    try:
        with open("selftest.log", "a", encoding="utf-8") as fh:
            fh.write(message + "\n")
    except OSError:
        pass


def _selftest_offline_mt() -> str:
    """One sentence through the offline translator; what to print for it.

    Raises on anything except a download that could not happen for want of
    a network, which counts as a skip unless STT_SELFTEST_STRICT is set.
    """
    import requests

    from src.local_mt import LocalTranslator

    try:
        translated = LocalTranslator().translate("Hola mundo.", "es", "en")
    except (requests.ConnectionError, requests.Timeout):
        if os.environ.get("STT_SELFTEST_STRICT"):
            raise
        return "skipped (model not downloaded yet and no network to fetch it)"
    if not translated:
        raise RuntimeError("offline translator returned nothing")
    return repr(translated)


def selftest() -> int:
    """Headless build verification: model must load and transcribe."""
    import numpy as np

    from src.transcriber import Transcriber

    try:
        # No window opens here, but the UI toolkit's bundled theme data is
        # exactly what goes missing in a frozen build, and the transcriber
        # check below would never touch it.
        import customtkinter as ctk

        ctk.set_default_color_theme("dark-blue")

        transcriber = Transcriber()
        device = transcriber.load()
        # One second of silence: exercises the full decode path.
        text, lang, prob, duration = transcriber.transcribe(
            np.zeros(16000, dtype=np.float32))

        # The offline translator is the other native code path a frozen
        # build can break: CTranslate2 loading a second model type, plus the
        # sentencepiece extension. One real sentence through the es-en model
        # proves both, at the cost of that model's one-time download.
        mt_note = _selftest_offline_mt()
        _report(f"SELFTEST OK: model={transcriber.model_name} "
                f"device={device} (text={text!r}, lang={lang}) "
                f"offline-mt={mt_note} "
                f"ui=customtkinter {ctk.__version__}")
        return 0
    except Exception as exc:  # noqa: BLE001 - report anything that broke
        _report(f"SELFTEST FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
    # A frozen build re-launches this same executable to create multiprocessing
    # helpers - on macOS, the resource tracker. PyInstaller's runtime hook
    # recognises those launches and runs the helper instead of the app, but it
    # can only do so from inside freeze_support(). Without this call each helper
    # starts the whole app again and spawns another helper, so the .app
    # fork-bombs instead of exiting. Measured: 71 processes from one launch.
    #
    # This has to come first, before the --selftest check: a helper's argv holds
    # the interpreter flags and -c command, none of the arguments below.
    import multiprocessing
    multiprocessing.freeze_support()

    if "--selftest" in sys.argv:
        sys.exit(selftest())

    if sys.platform == "win32":
        # Give the app its own taskbar identity so Windows shows our icon
        # (instead of grouping the window under the generic Python icon).
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "mondragon.speechtotext.v2")

    from src.app import SpeechToTextApp
    SpeechToTextApp().mainloop()
