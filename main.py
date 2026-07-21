"""Entry point for the EN/ES speech-to-text app.

Run the app:       python main.py   (or SpeechToText.exe)
Verify a build:    SpeechToText.exe --selftest
                   Loads the real Whisper model and transcribes a test tone
                   without opening a window; exits 0 on success, 1 on
                   failure. CI runs this on every release so a build whose
                   model cannot load can never ship.
"""

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


def selftest() -> int:
    """Headless build verification: model must load and transcribe."""
    import numpy as np

    from src.transcriber import Transcriber

    try:
        transcriber = Transcriber()
        device = transcriber.load()
        # One second of silence: exercises the full decode path.
        text, lang, prob, duration = transcriber.transcribe(
            np.zeros(16000, dtype=np.float32))
        _report(f"SELFTEST OK: model={transcriber.model_name} "
                f"device={device} (text={text!r}, lang={lang})")
        return 0
    except Exception as exc:  # noqa: BLE001 - report anything that broke
        _report(f"SELFTEST FAIL: {type(exc).__name__}: {exc}")
        return 1


if __name__ == "__main__":
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
