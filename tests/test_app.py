"""UI tests for src.app with the heavy dependencies mocked out.

These create a real (hidden-ish) CustomTkinter window, so they need a
desktop session - they run on a normal Windows/macOS/Linux machine but
would need a virtual display (e.g. Xvfb) on a headless CI runner.
"""

import json
import re
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from unittest.mock import MagicMock, patch

import customtkinter as ctk
import numpy as np
import pytest

from src.app import (LANG_NAMES, MINI_BG, MODE_LABELS, MiniWidget,
                     SpeechToTextApp)
from src.hotkeys import NullHotkeyManager
from src.settings import Settings
from src.translator import Translation, TranslationError


@pytest.fixture(scope="module")
def _shared_app(tmp_path_factory):
    """One SpeechToTextApp for the whole module.

    Tk misbehaves when many interpreters are created and destroyed in a
    single process, so all tests share one window (state is reset by the
    ``app`` fixture below).

    The transcriber and the hotkey manager are handed in rather than patched:
    the app takes its collaborators as constructor arguments, so a test can
    substitute them directly. Settings get a scratch file too: without it the
    window reads the developer's real settings.json and any test that expects
    a default fails on a machine where that default was changed.
    """
    fake = MagicMock()
    fake.load.return_value = "GPU (test)"
    fake.gpu_error = None
    fake.model_name = "large-v3"
    settings = Settings(tmp_path_factory.mktemp("settings") / "settings.json")
    application = SpeechToTextApp(transcriber=fake,
                                  hotkeys=NullHotkeyManager(),
                                  settings=settings)
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
        app.translate = MagicMock(return_value=Translation("Hola.", "offline"))
        app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False)
        for _ in range(20):
            app.update()
        assert app._pane_text("en") == "Hello."
        assert app._pane_text("es") == "Hola."
        assert "Done" in app.status_lbl.cget("text")

    def test_the_translator_is_told_the_mode_and_both_languages(self, app):
        app.transcriber.transcribe.return_value = ("Hola.", "es", 0.99, 1.2)
        app.translate = MagicMock(return_value=Translation("Hello.", "Google"))
        app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False,
                           mode="online")
        for _ in range(20):
            app.update()
        kwargs = app.translate.call_args.kwargs
        assert app.translate.call_args.args == ("Hola.",)
        assert (kwargs["source"], kwargs["target"], kwargs["mode"]) == \
            ("es", "en", "online")
        assert callable(kwargs["progress"])

    def test_the_status_names_the_engine_that_translated(self, app):
        app.transcriber.transcribe.return_value = ("Hola.", "es", 0.99, 1.2)
        app.translate = MagicMock(return_value=Translation("Hello.", "MyMemory"))
        app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False,
                           mode="online")
        for _ in range(20):
            app.update()
        assert "translated MyMemory" in app.status_lbl.cget("text")

    def test_translate_off_makes_no_network_call(self, app):
        app.transcriber.transcribe.return_value = ("Hello.", "en", 0.99, 1.2)
        fake_translate = MagicMock()
        app.translate = fake_translate
        app._process_audio(np.zeros(16000, dtype=np.float32),
                           autocopy=False, mode="off")
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

    def test_translation_failure_says_why_per_engine(self, app):
        """"Are you online?" was the old message for every failure, including
        a Google rate limit on a perfectly good connection."""
        app.transcriber.transcribe.return_value = ("Hello.", "en", 0.99, 1.2)
        app.translate = MagicMock(side_effect=TranslationError(
            "Google: rate-limited (too many requests from this network today); "
            "MyMemory: no connection"))
        app._process_audio(np.zeros(16000, dtype=np.float32), autocopy=False,
                           mode="online")
        for _ in range(20):
            app.update()
        status = app.status_lbl.cget("text")
        assert "Google: rate-limited" in status
        assert "are you online" not in status

    def test_download_progress_reaches_the_status_bar(self, app):
        report = app._download_progress("es", "en")
        report(34_000_000, 68_000_000)
        for _ in range(5):
            app.update()
        status = app.status_lbl.cget("text")
        assert "Downloading the offline translator" in status
        assert "50%" in status and "68 MB" in status

    def test_download_progress_only_posts_whole_percent_changes(self, app):
        report = app._download_progress("es", "en")
        with patch.object(app, "_ui") as ui:
            report(1, 1000)
            report(2, 1000)
            report(10, 1000)
            report(11, 1000)
        assert ui.call_count == 2


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
        app.translate = (MagicMock(return_value=Translation(translation, "offline"))
                         if translate_ok
                         else MagicMock(side_effect=ConnectionError("offline")))
        app.clipboard_clear()
        app.clipboard_append("SENTINEL")
        app._process_audio(np.zeros(16000, dtype=np.float32),
                           autocopy=autocopy,
                           mode="offline" if do_translate else "off",
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


class TestSettingsPersistence:
    """The choices must survive a restart.

    A second ``SpeechToTextApp`` in this process is a second Tk interpreter,
    and on Windows the second one created after another was destroyed fails
    intermittently with "Can't find a usable init.tcl". So the tests that
    only need *a* window drive the shared one with a scratch settings file,
    and the two whose point is a fresh launch run that launch in a child
    process, where Tk starts clean every time.
    """

    @pytest.fixture
    def store(self, app, tmp_path):
        """The shared window, writing to a fresh file for this test only."""
        original = app.settings
        app.settings = Settings(tmp_path / "s.json")
        try:
            yield app.settings
        finally:
            app.settings = original
            app.autocopy_var.set(True)
            app.english_clip_var.set(False)
            app.translate_mode_var.set(MODE_LABELS["offline"])
            app._sync_english_clip_state()

    def test_a_toggle_is_written_immediately(self, app, store):
        """Saved on change, not only at exit, so a force quit loses nothing."""
        app.english_clip_var.set(True)
        app._save_settings()
        assert store.load()["always_copy_english"] is True

    def test_the_mode_is_written_when_switched(self, app, store):
        app.translate_mode_var.set(MODE_LABELS["online"])
        app._on_translate_mode_changed()
        assert store.load()["translate_mode"] == "online"

    def test_unwritable_settings_do_not_break_anything(self, app, store):
        """A read-only home must not stop the app working."""
        with patch.object(store, "save", return_value=False):
            app._save_settings()          # must not raise
            app.english_clip_var.set(True)
        assert app.english_clip_var.get() is True

    def test_choices_come_back_on_the_next_launch(self, tmp_path):
        store = Settings(tmp_path / "s.json")
        store.save({"autocopy": False, "translate_mode": "online",
                    "always_copy_english": True})
        seen = _launch_in_child(store.path)
        assert seen == {"autocopy": False, "english": True, "mode": "online"}

    def test_closing_saves_and_a_corrupt_file_still_starts(self, tmp_path):
        """One launch for two facts: a corrupt file on disk is not fatal on
        the way in, and the close handler is a backstop save on the way out."""
        path = tmp_path / "s.json"
        path.write_text("{{{ not json", encoding="utf-8")
        seen = _launch_in_child(path, close_with_mode="off")
        assert seen["autocopy"] is True            # the default
        assert Settings(path).load()["translate_mode"] == "off"


_CHILD_LAUNCH = """
import json, sys
from unittest.mock import MagicMock
from src.app import MODE_LABELS, SpeechToTextApp
from src.hotkeys import NullHotkeyManager
from src.settings import Settings
fake = MagicMock()
fake.load.return_value = "CPU (test)"
fake.gpu_error = None
fake.model_name = "small"
app = SpeechToTextApp(transcriber=fake, hotkeys=NullHotkeyManager(),
                      settings=Settings(sys.argv[1]))
for _ in range(50):
    app.update()
    if app.model_ready:
        break
print(json.dumps({"autocopy": app.autocopy_var.get(),
                  "english": app.english_clip_var.get(),
                  "mode": app.translate_mode()}))
if len(sys.argv) > 2:
    app.translate_mode_var.set(MODE_LABELS[sys.argv[2]])
    app._on_close()
else:
    app.destroy()
"""


def _launch_in_child(settings_path, close_with_mode=None):
    """Start the app in a fresh interpreter and report what it read back.

    Returns the dict the child prints: the three choices as the new window
    saw them. With ``close_with_mode`` the child sets that mode and exits
    through the close handler instead of plain ``destroy``.
    """
    args = [sys.executable, "-c", _CHILD_LAUNCH, str(settings_path)]
    if close_with_mode:
        args.append(close_with_mode)
    done = subprocess.run(args, capture_output=True, text=True, timeout=120,
                          cwd=str(Path(__file__).resolve().parent.parent))
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout.strip().splitlines()[-1])


class TestTranslateModeControl:
    def test_offers_exactly_the_three_modes(self, app):
        assert app.translate_mode_btn.cget("values") == \
            ["Off", "Offline", "Online"]

    def test_defaults_to_offline(self, app):
        assert app.translate_mode() == "offline"

    def test_reads_back_as_a_settings_value(self, app):
        for mode, label in MODE_LABELS.items():
            app.translate_mode_var.set(label)
            assert app.translate_mode() == mode
        app.translate_mode_var.set(MODE_LABELS["offline"])


class TestEnglishClipCheckbox:
    def test_disabled_while_translation_is_off(self, app):
        app.translate_mode_var.set(MODE_LABELS["off"])
        app._sync_english_clip_state()
        assert app.english_clip_box.cget("state") == "disabled"

    def test_enabled_again_when_translation_comes_back(self, app):
        app.translate_mode_var.set(MODE_LABELS["off"])
        app._sync_english_clip_state()
        app.translate_mode_var.set(MODE_LABELS["offline"])
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

    def test_buttons_are_words_not_glyphs(self, app):
        """The minimise and restore symbols have no font on macOS and drew
        as empty boxes. Button labels are plain words, except the record
        button's state marks, which every platform renders."""
        assert app.mini_btn.cget("text") == "Mini"
        app.toggle_mini_mode()
        app.update()
        labels = [button.cget("text") for button in _buttons(app.mini)]
        assert "Restore" in labels
        for label in labels:
            assert label.isascii() or label in ("●", "■", "…", "✓")
        app.toggle_mini_mode()

    def test_windows_transparency_uses_the_colour_key(self):
        """Windows sees the pill through a colour nothing else paints."""
        pill = MagicMock()
        with patch("src.app.sys.platform", "win32"):
            MiniWidget._make_window_transparent(pill)
        pill.configure.assert_called_once_with(fg_color="#000001")
        pill.wm_attributes.assert_called_once_with("-transparentcolor", "#000001")
        pill.attributes.assert_not_called()

    def test_macos_transparency_uses_the_real_thing(self):
        """macOS has no colour key; a solid near-black window was what drew
        the pill inside a rectangle. The pill must ask for per-window
        transparency there instead."""
        pill = MagicMock()
        with patch("src.app.sys.platform", "darwin"):
            MiniWidget._make_window_transparent(pill)
        pill.attributes.assert_called_once_with("-transparent", True)
        pill.configure.assert_called_once_with(fg_color="systemTransparent")
        pill.wm_attributes.assert_not_called()

    def test_a_platform_without_transparency_gets_a_plain_pill(self):
        pill = MagicMock()
        pill.wm_attributes.side_effect = tk.TclError("bad attribute")
        with patch("src.app.sys.platform", "linux"):
            MiniWidget._make_window_transparent(pill)
        pill.configure.assert_called_with(fg_color=MINI_BG)


def _buttons(widget):
    """Every CTkButton below ``widget``, depth first."""
    found = []
    for child in widget.winfo_children():
        if isinstance(child, ctk.CTkButton):
            found.append(child)
        found.extend(_buttons(child))
    return found


class TestGuards:
    def test_recording_blocked_while_processing(self, app):
        app._processing = True
        app.toggle_recording()
        assert not app.recorder.is_recording

    def test_language_names_cover_both_panes(self):
        assert set(LANG_NAMES) == {"en", "es"}
