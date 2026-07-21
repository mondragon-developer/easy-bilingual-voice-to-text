"""Entry point for the EN/ES speech-to-text app. Run:  python main.py"""

import sys

if sys.platform == "win32":
    # Give the app its own taskbar identity so Windows shows our icon
    # (instead of grouping the window under the generic Python icon).
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        "mondragon.speechtotext.v2")

from src.app import SpeechToTextApp

if __name__ == "__main__":
    SpeechToTextApp().mainloop()
