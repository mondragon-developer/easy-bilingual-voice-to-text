"""Exercise the real platform filters with synthetic native event structures.

These prove routing and suppression, not physical OS delivery/permissions.
No keyboard hooks or microphone are opened by these tests.
"""

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from ptt.backend import KeyListener
from ptt.control import HoldKey
from push_to_talk import options


@pytest.fixture(params=["F9", "F13"])
def listener(request):
    key = HoldKey()
    key.set_enabled(True)
    backend = KeyListener(key, request.param)
    backend.code = 0x78 if request.param == "F9" else 0x7C
    backend.listener = Mock()
    backend.get_key_state = Mock(return_value=0)
    return backend


def test_windows_only_suppresses_selected_unmodified_key(listener):
    b = listener
    b.windows_filter(0x100, SimpleNamespace(vkCode=0x41))
    b.listener.suppress_event.assert_not_called()
    for msg in (0x100, 0x100, 0x101):
        b.windows_filter(msg, SimpleNamespace(vkCode=b.code))
    assert b.listener.suppress_event.call_count == 3
    assert b.key.events.get_nowait() == ("down", 1)
    assert b.key.events.get_nowait() == ("up", 1)
    assert b.key.events.empty()


def test_windows_alt_shortcut_passes_through(listener):
    b = listener
    b.get_key_state = lambda vk: 0x8000 if vk == 0x12 else 0
    b.windows_filter(0x104, SimpleNamespace(vkCode=b.code))
    b.get_key_state = lambda vk: 0
    b.windows_filter(0x105, SimpleNamespace(vkCode=b.code))
    b.listener.suppress_event.assert_not_called()
    assert b.key.events.empty()


def quartz():
    return SimpleNamespace(
        kCGEventKeyDown=10, kCGEventKeyUp=11,
        kCGEventTapDisabledByTimeout=-1, kCGEventTapDisabledByUserInput=-2,
        kCGKeyboardEventKeycode=9,
        kCGEventFlagMaskShift=1, kCGEventFlagMaskControl=2,
        kCGEventFlagMaskAlternate=4, kCGEventFlagMaskCommand=8,
        CGEventGetIntegerValueField=lambda e, _: e.code,
        CGEventGetFlags=lambda e: e.flags)


def test_mac_selected_events_only_and_modifier_release(listener):
    b = listener
    b.quartz = quartz()
    other = SimpleNamespace(code=0, flags=0)
    assert b.mac_intercept(10, other) is other
    selected = SimpleNamespace(code=b.code, flags=0)
    assert b.mac_intercept(10, selected) is None
    selected.flags = 8  # Cmd pressed while already recording
    assert b.mac_intercept(11, selected) is None
    assert b.key.events.get_nowait() == ("down", 1)
    assert b.key.events.get_nowait() == ("up", 1)


def test_mac_shortcuts_and_media_events_pass_through(listener):
    b = listener
    b.quartz = quartz()
    event = SimpleNamespace(code=b.code, flags=8)
    assert b.mac_intercept(10, event) is event
    event.flags = 0
    assert b.mac_intercept(11, event) is event
    assert b.mac_intercept(14, event) is event
    assert b.key.events.empty()


def test_mac_disabled_tap_releases_hold_and_reports_failure(listener):
    b = listener
    b.quartz = quartz()
    b.key.feed(True)
    b.mac_intercept(-1, None)
    assert not b.key.active(1)
    assert "disabled" in b.health()[1]


def test_shutdown_disables_capture(listener):
    listener.key.feed(True)
    listener.stop()
    assert not listener.key.active(1)
    listener.listener.stop.assert_called_once()


def test_dead_listener_is_not_reported_ready(listener):
    listener.ready.set()
    listener.listener.is_alive.return_value = False
    ready, error = listener.health()
    assert not ready and "stopped" in error


def test_cli_defaults_and_f13():
    assert options([]).key == "F9"
    assert options(["--key", "f13"]).key == "F13"


@pytest.mark.parametrize("args", [["--key", "Z"], ["--max-seconds", "0"],
                                 ["--max-seconds", "1801"]])
def test_invalid_configuration_rejected(args):
    with pytest.raises(SystemExit):
        options(args)
