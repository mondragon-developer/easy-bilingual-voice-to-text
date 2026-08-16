"""UI tests for src.app with the heavy dependencies mocked out.

These create a real (hidden-ish) CustomTkinter window, so they need a
desktop session - they run on a normal Windows/macOS/Linux machine but
would need a virtual display (e.g. Xvfb) on a headless CI runner.
"""

import re
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from src.app import LANG_NAMES, MiniWidget, SpeechToTextApp
from src.hotkeys import NullHotkeyManager


@pytest.fixture(scope="module")
def _shared_app():
    """One SpeechToTextApp for the whole module.

    Tk misbehaves when many interpreters are created and destroyed in a
    single process, so all tests share one window (state is reset by the
    ``app`` fixture below).

    The transcriber and the hotkey manager are handed in rather than patched:
    the app takes its collaborators as constructor arguments, so a test can
    substitute them directly.
    """
    fake = MagicMock()
    fake.load.return_value = "GPU (test)"
    fake.gpu_error = None
    fake.model_name = "large-v3"
    application = SpeechToTextApp(transcriber=fake,
                                  hotkeys=NullHotkeyManager())
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
    a.log.reset()
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


class TestEntries:
    """Each recording is its own headed entry; headers never get copied."""

    def test_each_recording_starts_a_numbered_entry(self, app):
        app._show_result("One.", "en", 0.9)
        app._show_result("Two.", "en", 0.9)
        raw = app.boxes["en"].get("1.0", "end-1c")
        assert raw.startswith("#1 · ")
        assert "\n\n#2 · " in raw
        assert app._pane_text("en") == "One.\n\nTwo."

    def test_date_is_shown_only_on_the_first_entry(self, app):
        app._show_result("One.", "en", 0.9)
        app._show_result("Two.", "en", 0.9)
        first, second = [line for line in
                         app.boxes["en"].get("1.0", "end-1c").splitlines()
                         if line.startswith("#")]
        assert re.match(r"#1 · [A-Z][a-z]{2} \d{1,2}, \d{1,2}:\d{2} [AP]M$", first)
        assert re.match(r"#2 · \d{1,2}:\d{2} [AP]M$", second)

    def test_both_panes_share_one_number_and_time(self, app):
        app._show_result("Hello.", "en", 0.9)
        app._append_to_pane("es", "Hola.")
        heads = [box.get("1.0", "1.end") for box in app.boxes.values()]
        assert heads[0] == heads[1]

    def test_pane_with_no_text_gets_no_header(self, app):
        app._show_result("Hello.", "en", 0.9)  # translation never arrives
        assert app.boxes["es"].get("1.0", "end-1c") == ""

    def test_numbering_restarts_once_both_panes_are_empty(self, app):
        app._show_result("One.", "en", 0.9)
        app._show_result("Two.", "en", 0.9)
        app.boxes["en"].delete("1.0", "end")
        app._show_result("Fresh start.", "en", 0.9)
        assert app.boxes["en"].get("1.0", "end-1c").startswith("#1 · ")

    def test_numbering_continues_while_one_pane_holds_text(self, app):
        app._show_result("Hello.", "en", 0.9)
        app._append_to_pane("es", "Hola.")
        app.boxes["en"].delete("1.0", "end")  # only the English side cleared
        app._show_result("Again.", "en", 0.9)
        assert app.boxes["en"].get("1.0", "end-1c").startswith("#2 · ")

    def test_copy_button_leaves_headers_behind(self, app):
        app._show_result("One.", "en", 0.9)
        app._show_result("Two.", "en", 0.9)
        app.copy_pane("en")
        assert app.clipboard_get() == "One.\n\nTwo."

    def test_selection_copy_leaves_headers_behind(self, app):
        app._show_result("One.", "en", 0.9)
        app._show_result("Two.", "en", 0.9)
        inner = app.boxes["en"]._textbox
        app._select_all(inner)
        app._copy_selection(inner)
        assert app.clipboard_get() == "One.\n\nTwo."

    def test_selection_copy_of_a_partial_span(self, app):
        app._show_result("One.", "en", 0.9)
        app._show_result("Two.", "en", 0.9)
        inner = app.boxes["en"]._textbox
        inner.tag_add("sel", "2.0", "4.end")  # first text line through header 2
        app._copy_selection(inner)
        assert app.clipboard_get() == "One.\n\n"

    def test_cut_copies_stripped_text_and_removes_the_selection(self, app):
        app._show_result("One.", "en", 0.9)
        inner = app.boxes["en"]._textbox
        app._select_all(inner)
        app._copy_selection(inner, cut=True)
        assert app.clipboard_get() == "One."
        assert app.boxes["en"].get("1.0", "end-1c") == ""

    def test_hand_edits_beside_a_header_stay_copyable(self, app):
        """Tk gives new text the tags shared by both neighbours - so text
        typed against a header must not be absorbed into it and vanish
        from the clipboard."""
        app._show_result("One.", "en", 0.9)
        inner = app.boxes["en"]._textbox
        inner.insert("2.0", "Edited: ")      # hard against the header's newline
        inner.insert("end-1c", " tail")
        assert app._pane_text("en") == "Edited: One. tail"

    def test_saved_file_keeps_the_headers(self, app, tmp_path):
        app._show_result("One.", "en", 0.9)
        out = tmp_path / "out.txt"
        with patch("src.app.filedialog.asksaveasfilename", return_value=str(out)):
            app.save_transcript()
        content = out.read_text(encoding="utf-8")
        assert "#1 · " in content and "One." in content


class TestShowResult:
    def test_updates_badge_titles_and_pane(self, app):
        app._show_result("Hola mundo.", "es", 0.98)
        app.update()
        assert "Español" in app.lang_badge.cget("text")
        assert "98%" in app.lang_badge.cget("text")
        assert "spoken" in app.pane_titles["es"].cget("text")
        assert "translation" in app.pane_titles["en"].cget("text")
        assert app._pane_text("es") == "Hola mundo."

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
        app.translate = MagicMock(return_value="Hola.")
        app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False)
        for _ in range(20):
            app.update()
        assert app._pane_text("en") == "Hello."
        assert app._pane_text("es") == "Hola."
        assert "Done" in app.status_lbl.cget("text")

    def test_translate_off_makes_no_network_call(self, app):
        app.transcriber.transcribe.return_value = ("Hello.", "en", 0.99, 1.2)
        fake_translate = MagicMock()
        app.translate = fake_translate
        app._process_audio(np.zeros(16000, dtype=np.float32),
                           autocopy=False, do_translate=False)
        for _ in range(20):
            app.update()
        fake_translate.assert_not_called()
        assert app._pane_text("en") == "Hello."
        assert app.boxes["es"].get("1.0", "end-1c") == ""
        assert "Translation off" in app.status_lbl.cget("text")

    def test_translation_failure_keeps_spoken_text(self, app):
        app.transcriber.transcribe.return_value = ("Hello.", "en", 0.99, 1.2)
        app.translate = MagicMock(side_effect=ConnectionError("offline"))
        app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False)
        for _ in range(20):
            app.update()
        assert app._pane_text("en") == "Hello."
        assert app.boxes["es"].get("1.0", "end-1c") == ""
        assert "translation failed" in app.status_lbl.cget("text")


class TestAlwaysCopyEnglish:
    """With the option on, the clipboard gets English whatever was spoken.

    The awkward part is timing: the spoken text is shown before the
    translation exists, so the copy has to wait for it - and must still leave
    something useful on the clipboard when the translation never arrives.
    """

    def _run(self, app, spoken, lang, translation="Hello.",
             translate_ok=True, do_translate=True, prefer_english=True,
             autocopy=True):
        app.transcriber.transcribe.return_value = (spoken, lang, 0.99, 1.2)
        app.translate = (MagicMock(return_value=translation) if translate_ok
                         else MagicMock(side_effect=ConnectionError("offline")))
        app.clipboard_clear()
        app.clipboard_append("SENTINEL")
        app._process_audio(np.zeros(16000, dtype=np.float32),
                           autocopy=autocopy, do_translate=do_translate,
                           prefer_english=prefer_english)
        for _ in range(20):
            app.update()
        return app.clipboard_get()

    def test_spanish_dictation_copies_the_english_translation(self, app):
        assert self._run(app, "Hola mundo.", "es",
                         translation="Hello world.") == "Hello world."

    def test_english_dictation_still_copies_the_spoken_text(self, app):
        """Spoken English already *is* the English - nothing to wait for."""
        assert self._run(app, "Hello world.", "en",
                         translation="Hola mundo.") == "Hello world."

    def test_option_off_copies_the_spoken_text(self, app):
        assert self._run(app, "Hola mundo.", "es", translation="Hello world.",
                         prefer_english=False) == "Hola mundo."

    def test_translation_off_falls_back_to_the_spoken_text(self, app):
        """No translation means no English version exists to copy."""
        assert self._run(app, "Hola mundo.", "es",
                         do_translate=False) == "Hola mundo."

    def test_failed_translation_falls_back_to_the_spoken_text(self, app):
        """The clipboard must not be left holding the previous contents."""
        assert self._run(app, "Hola mundo.", "es",
                         translate_ok=False) == "Hola mundo."

    def test_failed_translation_says_what_it_copied_instead(self, app):
        self._run(app, "Hola mundo.", "es", translate_ok=False)
        assert "spoken text copied instead" in app.status_lbl.cget("text")

    def test_autocopy_off_copies_nothing_at_all(self, app):
        """The master switch still wins over this one."""
        assert self._run(app, "Hola mundo.", "es", translation="Hello world.",
                         autocopy=False) == "SENTINEL"

    def test_status_names_english_when_that_is_what_was_copied(self, app):
        self._run(app, "Hola mundo.", "es", translation="Hello world.")
        assert "English copied to clipboard" in app.status_lbl.cget("text")

    def test_both_panes_still_get_their_text(self, app):
        self._run(app, "Hola mundo.", "es", translation="Hello world.")
        assert app._pane_text("es") == "Hola mundo."
        assert app._pane_text("en") == "Hello world."


class TestEnglishClipCheckbox:
    def test_disabled_while_translation_is_off(self, app):
        app.translate_var.set(False)
        app._sync_english_clip_state()
        assert app.english_clip_box.cget("state") == "disabled"

    def test_enabled_again_when_translation_comes_back(self, app):
        app.translate_var.set(False)
        app._sync_english_clip_state()
        app.translate_var.set(True)
        app._sync_english_clip_state()
        assert app.english_clip_box.cget("state") == "normal"

    def test_off_by_default(self, app):
        assert app.english_clip_var.get() is False


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
