"""Verify the frozen UI, hook imports and pipeline without capturing audio."""

import tempfile
import time
from pathlib import Path


def run():
    app = None
    try:
        import numpy as np
        from pynput import keyboard
        from src.hotkeys import NullHotkeyManager
        from src.settings import Settings
        from src.translator import Translation
        from .app import PushToTalkApp
        from .paste import create_paster

        assert keyboard.Key.f9.value.vk != keyboard.Key.f13.value.vk

        class Recorder:
            is_recording = False
            limit_reached = False
            level = 0

            def start(self):
                self.is_recording = True

            def stop(self):
                self.is_recording = False
                return np.zeros(16000, dtype=np.float32)

        class Transcriber:
            model_name = "small"
            gpu_error = None

            def load(self, *args):
                return "CPU (packaging check)"

            def transcribe(self, audio):
                return "Hola mundo.", "es", 0.99, 1.0

        class Listener:
            def __init__(self, key, key_name):
                self.key = key

            def start(self):
                pass

            def health(self):
                return True, None

            def stop(self):
                self.key.set_enabled(False)

        def wait_for(condition):
            deadline = time.monotonic() + 10
            while time.monotonic() < deadline:
                app.update()
                if condition():
                    return
                time.sleep(0.01)
            raise RuntimeError("Timed out during frozen PTT check")

        with tempfile.TemporaryDirectory() as folder:
            # Import and construct the real platform adapter, then replace
            # delivery so this check never types into another application.
            paster = create_paster()
            pasted = []
            paster.capture = lambda: "selftest destination"
            paster.paste = pasted.append
            app = PushToTalkApp(
                recorder=Recorder(), transcriber=Transcriber(),
                translator=lambda *a, **kw: Translation("Hello world.", "offline"),
                hotkeys=NullHotkeyManager(), listener_factory=Listener,
                settings=Settings(Path(folder) / "settings.json"),
                paster=paster,
                web_peer=lambda mode: None)
            wait_for(lambda: app.model_ready)
            app.autocopy_var.set(True)
            app.english_clip_var.set(True)
            app.ptt_key.feed(True)
            wait_for(lambda: app.recorder.is_recording)
            for _ in range(10):
                app.ptt_key.feed(True)
            app.ptt_key.feed(False)
            wait_for(lambda: not app.recorder.is_recording and not app._processing)
            assert app.clipboard_get() == "Hello world."
            assert "Hola mundo." in app._pane_text("es")
            assert pasted == []  # Auto-paste starts off in a normal launch.
            app.paste_english.set(True)
            app.ptt_key.feed(True)
            wait_for(lambda: app.recorder.is_recording)
            app.ptt_key.feed(False)
            wait_for(lambda: not app.recorder.is_recording and not app._processing)
            assert pasted == ["selftest destination"]
            assert app.clipboard_get() == "Hello world."
            app._on_close()
            app = None
        message, code = "PTT SELFTEST OK: native imports, UI, hold/release, English clipboard, simulated paste", 0
    except Exception as exc:
        message, code = f"PTT SELFTEST FAIL: {type(exc).__name__}: {exc}", 1
    finally:
        if app is not None:
            app._on_close()
    Path("selftest-ptt.log").write_text(message + "\n", encoding="utf-8")
    if __import__("sys").stdout is not None:
        print(message, flush=True)
    return code
