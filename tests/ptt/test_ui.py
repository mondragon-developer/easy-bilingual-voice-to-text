"""Real GUI + original processing pipeline, with no real mic/model/hook."""

import time
from unittest.mock import Mock

import pytest


@pytest.fixture(scope="module")
def app(request, tmp_path_factory):
    if not request.config.getoption("--run-ptt-ui"):
        pytest.skip("Use --run-ptt-ui in a desktop/display session")
    import numpy as np
    from ptt.app import PushToTalkApp
    from src.hotkeys import NullHotkeyManager
    from src.settings import Settings
    from src.translator import Translation

    class Recorder:
        is_recording = False
        limit_reached = False
        level = 0

        def start(self):
            self.is_recording = True

        def stop(self):
            self.is_recording = False
            return np.zeros(16000, dtype=np.float32)

    class Listener:
        def __init__(self, key, key_name):
            self.key = key
            self.stopped = False
            self.error = None

        def start(self):
            pass

        def health(self):
            return self.error is None, self.error

        def stop(self):
            self.stopped = True
            self.key.set_enabled(False)

    transcriber = Mock()
    transcriber.load.return_value = "CPU (test)"
    transcriber.model_name = "small"
    transcriber.gpu_error = None
    transcriber.transcribe.return_value = ("Hola mundo.", "es", 0.99, 1.0)
    app = PushToTalkApp(
        recorder=Recorder(), transcriber=transcriber,
        translator=lambda *a, **kw: Translation("Hello world.", "offline"),
        hotkeys=NullHotkeyManager(), listener_factory=Listener,
        settings=Settings(tmp_path_factory.mktemp("ptt-settings") / "settings.json"),
        paster=Mock(capture=Mock(return_value="editor")),
        web_peer=Mock())
    # Keep the test's clipboard private rather than replacing the user's.
    clipboard = [""]
    app.clipboard_clear = lambda: clipboard.__setitem__(0, "")
    app.clipboard_append = lambda text: clipboard.__setitem__(0, clipboard[0] + text)
    app.clipboard_get = lambda: clipboard[0]
    wait_for(app, lambda: app.model_ready)
    yield app
    app._on_close()
    assert app.ptt_listener.stopped


def wait_for(app, condition):
    deadline = time.monotonic() + 3
    while time.monotonic() < deadline:
        app.update()
        if condition():
            return
        time.sleep(0.01)
    pytest.fail("Timed out waiting for the UI")


def finish(app):
    wait_for(app, lambda: not app._processing)


def test_hold_uses_original_translation_and_english_clipboard(app):
    app.autocopy_var.set(True)
    app.english_clip_var.set(True)
    app.ptt_key.feed(True)
    wait_for(app, lambda: app.recorder.is_recording)
    for _ in range(10):
        app.ptt_key.feed(True)
    app.ptt_key.feed(False)
    wait_for(app, lambda: not app.recorder.is_recording)
    finish(app)
    assert app.clipboard_get() == "Hello world."
    assert "Hola mundo." in app._pane_text("es")
    assert "Hello world." in app._pane_text("en")


def test_manual_recording_survives_ptt_release(app):
    app.toggle_recording()
    app.ptt_key.feed(True)
    app.ptt_recording.tick()
    app.ptt_key.feed(False)
    app.ptt_recording.tick()
    assert app.recorder.is_recording
    app.toggle_recording()
    finish(app)


def test_mixed_controls_relinquish_ownership(app):
    app.ptt_key.feed(True)
    app.ptt_recording.tick()
    app.toggle_recording()
    finish(app)
    app.toggle_recording()
    app.ptt_key.feed(False)
    app.ptt_recording.tick()
    assert app.recorder.is_recording
    app.toggle_recording()
    finish(app)


def test_disabling_stops_hold_and_restores_key(app):
    app.ptt_key.feed(True)
    app.ptt_recording.tick()
    app.ptt_enabled.set(False)
    app._ptt_toggle()
    assert not app.recorder.is_recording
    app.ptt_key.feed(False)
    assert not app.ptt_key.feed(True)
    assert not app.ptt_key.feed(False)
    finish(app)
    app.ptt_enabled.set(True)
    app._ptt_toggle()


def test_autopaste_waits_for_english_translation(app):
    import threading
    from src.translator import Translation
    entered, complete = threading.Event(), threading.Event()
    original = app.translate

    def slow_translation(*args, **kwargs):
        entered.set()
        assert complete.wait(3)
        return Translation("Fresh English only.", "offline")

    app.translate = slow_translation
    app.paste_english.set(True)
    app.paster.paste.reset_mock()
    try:
        app.ptt_key.feed(True)
        wait_for(app, lambda: app.recorder.is_recording)
        app.ptt_key.feed(False)
        wait_for(app, entered.is_set)
        app.paster.paste.assert_not_called()
        complete.set()
        finish(app)
        app.paster.paste.assert_called_once_with("editor")
        assert app.clipboard_get() == "Fresh English only."
        # A duplicate completion cannot paste again.
        app._finish("Repeated completion")
        assert app.paster.paste.call_count == 1
    finally:
        complete.set()
        app.translate = original
        app.paste_english.set(False)


def test_failed_spanish_translation_never_pastes_spanish_or_old_english(app):
    original = app.translate
    app.translate = Mock(side_effect=RuntimeError("offline test"))
    app.paste_english.set(True)
    app.paster.paste.reset_mock()
    try:
        app.ptt_key.feed(True)
        wait_for(app, lambda: app.recorder.is_recording)
        app.ptt_key.feed(False)
        wait_for(app, lambda: not app.recorder.is_recording)
        finish(app)
        app.paster.paste.assert_not_called()
    finally:
        app.translate = original
        app.paste_english.set(False)


def test_english_paste_works_with_autocopy_and_translation_off(app):
    original = app.transcriber.transcribe.return_value
    from src.app import MODE_LABELS
    app.transcriber.transcribe.return_value = ("New English.", "en", 0.99, 1.0)
    app.translate_mode_var.set(MODE_LABELS["off"])
    app.autocopy_var.set(False)
    app.paste_english.set(True)
    app.paster.paste.reset_mock()
    try:
        app.ptt_key.feed(True)
        wait_for(app, lambda: app.recorder.is_recording)
        app.ptt_key.feed(False)
        wait_for(app, lambda: not app.recorder.is_recording)
        finish(app)
        assert app.clipboard_get() == "New English."
        app.paster.paste.assert_called_once_with("editor")
        # Manual recordings never auto-paste, even with the option enabled.
        app.paster.paste.reset_mock()
        app.toggle_recording()
        app.toggle_recording()
        finish(app)
        app.paster.paste.assert_not_called()
    finally:
        app.transcriber.transcribe.return_value = original
        app.translate_mode_var.set(MODE_LABELS["offline"])
        app.autocopy_var.set(True)
        app.paste_english.set(False)


def test_disabling_paste_cancels_pending_destination(app):
    app.paste_english.set(True)
    app._prepare_paste("editor")
    app._paste_text = "Do not paste."
    app.paste_english.set(False)
    app._paste_toggle()
    app.paster.paste.reset_mock()
    app._finish("Cancelled")
    app.paster.paste.assert_not_called()


def test_failure_stops_owned_recording_but_manual_controls_work(app):
    app.ptt_key.feed(True)
    app.ptt_recording.tick()
    app.ptt_listener.error = "Test listener disconnected"
    app._ptt_poll()
    assert not app.recorder.is_recording
    assert not app.ptt_enabled.get()
    assert app.ptt_listener.stopped
    finish(app)
    app.toggle_recording()
    assert app.recorder.is_recording
    app.toggle_recording()
    finish(app)
