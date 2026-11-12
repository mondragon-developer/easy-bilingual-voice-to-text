"""Destination checks and release ownership, without typing into user apps."""

import os
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ptt.control import HoldKey, HoldRecording
from ptt.paste import Destination, MacPaste, PasteError, WindowsPaste


def test_release_captures_destination_once_and_before_ui_poll():
    capture = Mock(return_value="release window")
    key = HoldKey(capture_release=capture)
    key.set_enabled(True)
    key.feed(True)
    key.feed(True)
    key.feed(False)
    capture.return_value = "later window"
    key.feed(False)
    assert key.events.get_nowait() == ("down", 1)
    assert key.events.get_nowait() == ("up", 1, "release window")
    capture.assert_called_once_with()


def test_disable_does_not_create_a_paste_destination():
    capture = Mock()
    key = HoldKey(capture_release=capture)
    key.set_enabled(True)
    key.feed(True)
    key.set_enabled(False)
    key.feed(False)
    assert key.events.get_nowait() == ("down", 1)
    assert key.events.get_nowait() == ("up", 1)
    capture.assert_not_called()


def test_capture_failure_does_not_break_key_release():
    key = HoldKey(capture_release=Mock(side_effect=RuntimeError("closed")))
    key.set_enabled(True)
    key.feed(True)
    assert key.feed(False)
    key.events.get_nowait()
    assert key.events.get_nowait() == ("up", 1, None)


def test_only_owned_physical_release_arms_paste():
    app = SimpleNamespace(model_ready=True, _processing=False,
                          recorder=SimpleNamespace(is_recording=False))
    key = HoldKey(capture_release=lambda: "editor")
    release = Mock()
    hold = HoldRecording(app, key, on_release=release)

    def toggle():
        app.recorder.is_recording = not app.recorder.is_recording
        if not app.recorder.is_recording:
            hold.state_changed("processing")

    app.toggle_recording = toggle
    key.set_enabled(True)
    key.feed(True)
    hold.tick()
    key.feed(False)
    hold.tick()
    release.assert_called_once_with("editor")
    release.reset_mock()
    key.feed(True)
    hold.tick()
    hold.stop()  # manual stop, timeout, or disable
    key.feed(False)
    hold.tick()
    release.assert_not_called()


@pytest.fixture
def windows():
    if sys.platform != "win32":
        pytest.skip("Windows ABI check")
    paster = WindowsPaste()
    paster.user = Mock()
    paster.user.GetAsyncKeyState.return_value = 0
    paster.user.SendInput.return_value = 4
    paster.user.GetWindowThreadProcessId.return_value = 42
    paster.user.GetKeyboardLayout.return_value = 0x04090409
    paster.user.MapVirtualKeyExW.side_effect = lambda vk, mode, layout: {0xA2: 0x1D, 0x56: 0x2F}[vk]
    paster.capture = Mock(return_value=Destination(123, 456, 789))
    return paster


def test_windows_batches_ctrl_v_without_enter(windows):
    windows.paste(windows.capture())
    count, events, size = windows.user.SendInput.call_args.args
    assert count == 4
    assert size == (40 if windows.c.sizeof(windows.c.c_void_p) == 8 else 28)
    assert [(e.value.keyboard.vk, e.value.keyboard.scan, e.value.keyboard.flags)
            for e in events] == [
        (0, 0x1D, 8), (0, 0x2F, 8), (0, 0x2F, 10), (0, 0x1D, 10)]
    windows.user.GetKeyboardLayout.assert_called_once_with(42)


def test_windows_paste_uses_target_layout_not_us_key_position(windows):
    windows.user.GetKeyboardLayout.return_value = 0x04070407
    windows.user.MapVirtualKeyExW.side_effect = lambda vk, mode, layout: {0xA2: 0x1D, 0x56: 0x30}[vk]
    windows.paste(windows.capture())
    events = windows.user.SendInput.call_args.args[1]
    assert events[1].value.keyboard.scan == 0x30
    assert all(call.args[2] == 0x04070407
               for call in windows.user.MapVirtualKeyExW.call_args_list)


def test_windows_missing_scan_code_never_falls_back_to_raw_control_character(windows):
    windows.user.MapVirtualKeyExW.side_effect = lambda *args: 0
    with pytest.raises(PasteError, match="Keyboard layout"):
        windows.paste(windows.capture())
    windows.user.SendInput.assert_not_called()


def test_windows_rechecks_target_after_mapping_keys(windows):
    target = Destination(123, 456, 789)
    windows.capture.side_effect = [target, Destination(123, 999, 789)]
    with pytest.raises(PasteError, match="Destination changed"):
        windows.paste(target)
    windows.user.SendInput.assert_not_called()


@pytest.mark.parametrize("target", [None, Destination(123, 457, 789),
                                   Destination(123, 456, 999),
                                   Destination(999, 456, 789)])
def test_windows_does_not_paste_into_changed_destination(windows, target):
    with pytest.raises(PasteError, match="Destination changed"):
        windows.paste(target)
    windows.user.SendInput.assert_not_called()


def test_windows_held_modifier_prevents_paste(windows):
    windows.user.GetAsyncKeyState.return_value = 0x8000
    with pytest.raises(PasteError, match="shortcut key"):
        windows.paste(windows.capture())
    windows.user.SendInput.assert_not_called()


def test_windows_blocked_injection_is_reported(windows):
    windows.user.SendInput.return_value = 0
    with pytest.raises(PasteError, match="Windows blocked"):
        windows.paste(windows.capture())


def test_windows_own_app_is_not_a_destination(windows):
    paster = windows
    del paster.capture
    paster.user.GetForegroundWindow.return_value = 123

    def thread(window, pid):
        pid._obj.value = os.getpid()
        return 42

    paster.user.GetWindowThreadProcessId.side_effect = thread
    assert paster.capture() is None


def test_mac_posts_command_v_and_rejects_changed_window():
    paster = MacPaste.__new__(MacPaste)
    paster.capture = Mock(return_value=Destination(123, 456))
    q = SimpleNamespace(
        kCGEventSourceStateCombinedSessionState=0,
        kCGEventFlagMaskShift=1, kCGEventFlagMaskControl=2,
        kCGEventFlagMaskAlternate=4, kCGEventFlagMaskCommand=8,
        kCGHIDEventTap=0,
        CGEventSourceFlagsState=Mock(return_value=0),
        CGEventCreateKeyboardEvent=Mock(side_effect=["down", "up"]),
        CGEventSetFlags=Mock(), CGEventPost=Mock())
    paster.q = q
    paster.paste(Destination(123, 456))
    assert [call.args for call in q.CGEventCreateKeyboardEvent.call_args_list] == [
        (None, 9, True), (None, 9, False)]
    assert [call.args for call in q.CGEventSetFlags.call_args_list] == [
        ("down", 8), ("up", 8)]
    assert q.CGEventPost.call_count == 2
    with pytest.raises(PasteError):
        paster.paste(Destination(123, 999))
    assert q.CGEventPost.call_count == 2
