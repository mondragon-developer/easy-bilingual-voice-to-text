"""UI tests for src.app with the heavy dependencies mocked out.

These create a real (hidden-ish) CustomTkinter window, so they need a
desktop session — they run on a normal Windows/macOS/Linux machine but
would need a virtual display (e.g. Xvfb) on a headless CI runner.
"""

from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.app import LANG_NAMES, MiniWidget, SpeechToTextApp


@pytest.fixture(scope="module")
def _shared_app():
    """One SpeechToTextApp for the whole module.

    Tk misbehaves when many interpreters are created and destroyed in a
    single process, so all tests share one window (state is reset by the
    ``app`` fixture below). Model loading and global hotkeys are stubbed.
    """
    with patch("src.app.Transcriber") as fake_cls, \
         patch.object(SpeechToTextApp, "_register_global_hotkeys",
                      lambda self: setattr(self, "hotkeys_ok", False)):
        fake = fake_cls.return_value
        fake.load.return_value = "GPU (test)"
        fake.gpu_error = None
        fake.model_name = "large-v3"
        application = SpeechToTextApp()
        # Let the model-load thread finish and its after() callbacks run.
        for _ in range(50):
            application.update()
            if application.model_ready:
                break
        yield application
        try:
            application.update()  # drain pending after() callbacks
            application.destroy()
        except Exception:
            pass  # window already torn down


@pytest.fixture
def app(_shared_app):
    """The shared app, reset to a clean state for each test."""
    a = _shared_app
    a.update()
    a._processing = False
    for box in a.boxes.values():
        box.delete("1.0", "end")
    if a.mini is not None and a.mini.winfo_exists():
        a.toggle_mini_mode()  # make sure we start restored, no pill
    a.deiconify()
    a.update()
    return a


class TestPanes:
    def test_append_to_empty_pane(self, app):
        app._append_to_pane("en", "Hello world.")
        assert app.boxes["en"].get("1.0", "end-1c") == "Hello world."

    def test_append_adds_separating_space(self, app):
        app._append_to_pane("es", "Hola.")
        app._append_to_pane("es", "¿Qué tal?")
        assert app.boxes["es"].get("1.0", "end-1c") == "Hola. ¿Qué tal?"

    def test_panes_are_editable(self, app):
        app.boxes["en"].insert("end", "typed by hand")
        assert "typed by hand" in app.boxes["en"].get("1.0", "end-1c")


class TestShowResult:
    def test_updates_badge_titles_and_pane(self, app):
        app._show_result("Hola mundo.", "es", 0.98)
        app.update()
        assert "Español" in app.lang_badge.cget("text")
        assert "98%" in app.lang_badge.cget("text")
        assert "spoken" in app.pane_titles["es"].cget("text")
        assert "translation" in app.pane_titles["en"].cget("text")
        assert app.boxes["es"].get("1.0", "end-1c") == "Hola mundo."

    def test_autocopy_places_text_on_clipboard(self, app):
        app._show_result("Copy me.", "en", 0.9, autocopy=True)
        app.update()
        assert app.clipboard_get() == "Copy me."


class TestProcessAudio:
    def test_too_short_audio_reports_and_reenables(self, app):
        app._processing = True
        app._process_audio(np.zeros(100, dtype=np.float32), autocopy=False)
        app.update()
        assert "too short" in app.status_lbl.cget("text")
        assert app._processing is False

    def test_full_flow_fills_both_panes(self, app):
        app.transcriber.transcribe.return_value = ("Hello.", "en", 0.99, 1.2)
        with patch("src.app.translate", return_value="Hola."):
            app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False)
        for _ in range(20):
            app.update()
        assert app.boxes["en"].get("1.0", "end-1c") == "Hello."
        assert app.boxes["es"].get("1.0", "end-1c") == "Hola."
        assert "Done" in app.status_lbl.cget("text")

    def test_translate_off_makes_no_network_call(self, app):
        app.transcriber.transcribe.return_value = ("Hello.", "en", 0.99, 1.2)
        with patch("src.app.translate") as fake_translate:
            app._process_audio(np.zeros(16000, dtype=np.float32),
                               autocopy=False, do_translate=False)
            for _ in range(20):
                app.update()
        fake_translate.assert_not_called()
        assert app.boxes["en"].get("1.0", "end-1c") == "Hello."
        assert app.boxes["es"].get("1.0", "end-1c") == ""
        assert "Translation off" in app.status_lbl.cget("text")

    def test_translation_failure_keeps_spoken_text(self, app):
        app.transcriber.transcribe.return_value = ("Hello.", "en", 0.99, 1.2)
        with patch("src.app.translate", side_effect=ConnectionError("offline")):
            app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False)
        for _ in range(20):
            app.update()
        assert app.boxes["en"].get("1.0", "end-1c") == "Hello."
        assert app.boxes["es"].get("1.0", "end-1c") == ""
        assert "translation failed" in app.status_lbl.cget("text")


class TestActions:
    def test_copy_pane(self, app):
        app.boxes["en"].insert("end", "clipboard test")
        app.copy_pane("en")
        assert app.clipboard_get() == "clipboard test"

    def test_copy_empty_pane_is_noop(self, app):
        app.clipboard_clear()
        app.clipboard_append("sentinel")
        app.copy_pane("en")
        assert app.clipboard_get() == "sentinel"

    def test_save_transcript_writes_both_sections(self, app, tmp_path):
        app.boxes["en"].insert("end", "English text")
        app.boxes["es"].insert("end", "Texto español")
        out = tmp_path / "out.txt"
        with patch("src.app.filedialog.asksaveasfilename",
                   return_value=str(out)):
            app.save_transcript()
        content = out.read_text(encoding="utf-8")
        assert "=== English ===" in content and "English text" in content
        assert "=== Español ===" in content and "Texto español" in content


class TestMiniMode:
    def test_toggle_creates_and_destroys_pill(self, app):
        app.toggle_mini_mode()
        app.update()
        assert isinstance(app.mini, MiniWidget)
        assert app.state() == "withdrawn"
        app.toggle_mini_mode()
        app.update()
        assert app.mini is None
        assert app.state() == "normal"

    def test_pill_mirrors_app_state(self, app):
        app.toggle_mini_mode()
        app.update()
        app._set_app_state("recording")
        assert app.mini.rec_btn.cget("text") == "■"
        app._set_app_state("idle")
        assert app.mini.rec_btn.cget("text") == "●"
        app.toggle_mini_mode()


class TestGuards:
    def test_recording_blocked_while_processing(self, app):
        app._processing = True
        app.toggle_recording()
        assert not app.recorder.is_recording

    def test_language_names_cover_both_panes(self):
        assert set(LANG_NAMES) == {"en", "es"}
