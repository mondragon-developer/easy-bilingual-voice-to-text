"""Regression scenarios: held/repeated keys, overlapping controls and failures."""

from types import SimpleNamespace

import pytest

from ptt.control import HoldKey, HoldRecording


class App:
    def __init__(self):
        self.model_ready = True
        self._processing = False
        self.recorder = SimpleNamespace(is_recording=False)
        self.starts = self.stops = 0
        self.hold = None

    def toggle_recording(self):
        if self._processing or not self.model_ready:
            return
        self.recorder.is_recording = not self.recorder.is_recording
        if self.recorder.is_recording:
            self.starts += 1
        else:
            self.stops += 1
            self._processing = True
            self.hold.state_changed("processing")


@pytest.fixture
def session():
    app, key, now = App(), HoldKey(), [0.0]
    key.set_enabled(True)
    hold = HoldRecording(app, key, max_seconds=5, clock=lambda: now[0])
    app.hold = hold
    return app, key, hold, now


def test_hold_repeat_release_records_once(session):
    app, key, hold, _ = session
    assert key.feed(True)
    hold.tick()
    for _ in range(20):
        assert key.feed(True)
        hold.tick()
    assert app.starts == 1 and app.stops == 0
    assert key.feed(False)
    hold.tick()
    assert app.stops == 1 and app._processing
    assert not key.feed(False)  # duplicate release does not restart
    hold.tick()
    assert app.starts == 1


@pytest.mark.parametrize("blocked", ["loading", "processing", "manual"])
def test_press_cannot_start_later_when_busy_clears(session, blocked):
    app, key, hold, _ = session
    app.model_ready = blocked != "loading"
    app._processing = blocked == "processing"
    app.recorder.is_recording = blocked == "manual"
    key.feed(True)
    hold.tick()
    app.model_ready = True
    app._processing = False
    if blocked != "manual":
        app.recorder.is_recording = False
    key.feed(True)  # key repeat after loading/processing is still ignored
    hold.tick()
    key.feed(False)
    hold.tick()
    assert (app.starts, app.stops) == (0, 0)
    assert app.recorder.is_recording == (blocked == "manual")


def test_release_does_not_stop_new_manual_recording(session):
    app, key, hold, _ = session
    key.feed(True)
    hold.tick()
    app.toggle_recording()  # user stops using the original button
    app._processing = False
    app.toggle_recording()  # user starts a different recording
    key.feed(False)
    hold.tick()
    assert app.recorder.is_recording
    assert (app.starts, app.stops) == (2, 1)


def test_short_tap_is_not_recorded_after_release(session):
    app, key, hold, _ = session
    key.feed(True)
    key.feed(False)
    hold.tick()
    assert (app.starts, app.stops) == (0, 0)


def test_stale_press_and_release_do_not_own_new_hold(session):
    app, key, hold, _ = session
    key.feed(True)
    key.feed(False)
    key.feed(True)
    hold.tick()
    assert app.starts == 1 and app.stops == 0
    key.feed(False)
    hold.tick()
    assert app.stops == 1


def test_disable_and_reenable_during_hold_needs_new_press(session):
    app, key, hold, _ = session
    key.feed(True)
    hold.tick()
    key.set_enabled(False)
    hold.stop()
    app._processing = False
    key.set_enabled(True)
    assert key.feed(True)  # retain suppression until original release
    hold.tick()
    assert app.starts == 1
    assert key.feed(False)
    hold.tick()
    assert app.stops == 1
    key.feed(True)
    hold.tick()
    assert app.starts == 2


def test_modified_shortcut_stays_untouched_until_release(session):
    app, key, hold, _ = session
    assert not key.feed(True, modified=True)
    assert not key.feed(True, modified=False)  # modifier released first
    assert not key.feed(False)
    hold.tick()
    assert app.starts == 0


def test_modifier_pressed_during_recording_does_not_lose_release(session):
    app, key, hold, _ = session
    key.feed(True)
    hold.tick()
    assert key.feed(False, modified=True)
    hold.tick()
    assert app.stops == 1


def test_disabled_key_passthrough(session):
    app, key, hold, _ = session
    key.set_enabled(False)
    assert not key.feed(True)
    key.set_enabled(True)
    assert not key.feed(True)
    assert not key.feed(False)
    hold.tick()
    assert app.starts == 0


def test_time_limit_stops_without_autorestarting(session):
    app, key, hold, now = session
    key.feed(True)
    hold.tick()
    for second in range(1, 6):
        now[0] = second
        reason = hold.tick()
    assert "time limit" in reason
    app._processing = False
    key.feed(True)
    hold.tick()
    assert (app.starts, app.stops) == (1, 1)


def test_event_loop_pause_stops_owned_recording(session):
    app, key, hold, now = session
    key.feed(True)
    hold.tick()
    now[0] = 3
    assert "pause" in hold.tick()
    assert app.stops == 1


def test_microphone_open_failure_never_makes_release_start_recording(session):
    app, key, hold, _ = session
    app.toggle_recording = lambda: None  # existing app handled the open error
    key.feed(True)
    hold.tick()
    assert hold.owner is None
    key.feed(False)
    hold.tick()
    assert not app.recorder.is_recording


def test_release_while_microphone_is_opening_stops_immediately(session):
    app, key, hold, _ = session
    original_toggle = app.toggle_recording

    def slow_open():
        original_toggle()
        if app.recorder.is_recording:
            key.feed(False)

    app.toggle_recording = slow_open
    key.feed(True)
    hold.tick()
    assert (app.starts, app.stops) == (1, 1)


def test_original_app_limit_releases_ownership(session):
    app, key, hold, _ = session
    key.feed(True)
    hold.tick()
    app.toggle_recording()  # existing app reached its own limit
    key.feed(False)
    hold.tick()
    assert app.stops == 1
