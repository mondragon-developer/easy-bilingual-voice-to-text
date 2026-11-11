"""Selective native interception through pynput, on Windows and macOS only.

    https://pynput.readthedocs.io/en/latest/faq.html

Never use suppress=True: it would swallow the entire keyboard. Only the
chosen F-key is consumed, and modified shortcuts pass through unchanged.
"""

import sys
import threading
import time


class KeyListener:
    def __init__(self, key, key_name="F9"):
        if key_name not in ("F9", "F13"):
            raise ValueError("Choose F9 or F13.")
        self.key = key
        self.key_name = key_name
        self.listener = None
        self.ready = threading.Event()
        self.failure = None
        self.started = None

    def start(self):
        if sys.platform not in ("win32", "darwin"):
            raise RuntimeError("Push-to-talk supports Windows and macOS only.")
        from pynput import keyboard

        self.code = getattr(keyboard.Key, self.key_name.lower()).value.vk
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            self.get_key_state = ctypes.windll.user32.GetAsyncKeyState
            self.get_key_state.argtypes = [wintypes.INT]
            self.get_key_state.restype = wintypes.SHORT
            self.listener = keyboard.Listener(
                win32_event_filter=self.windows_filter)
        else:
            import Quartz

            self.quartz = Quartz
            self.listener = keyboard.Listener(
                darwin_intercept=self.mac_intercept)
        self.started = time.monotonic()
        self.listener.start()
        # wait() has no timeout. Keep it off Tk; health() detects startup
        # failure/timeouts even if this daemon is waiting for readiness.
        threading.Thread(target=self._wait_ready, daemon=True).start()

    def _wait_ready(self):
        self.listener.wait()
        self.ready.set()

    def windows_filter(self, msg, data):
        if data.vkCode == self.code and msg in (0x100, 0x101, 0x104, 0x105):
            # Shift, Ctrl, Alt, left/right Windows keys. Caps Lock and Fn
            # are deliberately not modifiers for this purpose.
            modified = any(self.get_key_state(vk) & 0x8000
                           for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C))
            if self.key.feed(msg in (0x100, 0x104), modified):
                self.listener.suppress_event()
        return True

    def mac_intercept(self, event_type, event):
        q = self.quartz
        if event_type in (q.kCGEventTapDisabledByTimeout,
                          q.kCGEventTapDisabledByUserInput):
            self.failure = "macOS disabled the keyboard listener; restart the app."
            self.key.set_enabled(False)
            return event
        if event_type not in (q.kCGEventKeyDown, q.kCGEventKeyUp):
            return event
        if q.CGEventGetIntegerValueField(event, q.kCGKeyboardEventKeycode) != self.code:
            return event
        modifiers = (q.kCGEventFlagMaskShift | q.kCGEventFlagMaskControl
                     | q.kCGEventFlagMaskAlternate | q.kCGEventFlagMaskCommand)
        modified = bool(q.CGEventGetFlags(event) & modifiers)
        if self.key.feed(event_type == q.kCGEventKeyDown, modified):
            return None
        return event

    def health(self):
        """Return (ready, error); called from the UI without blocking."""
        if self.failure:
            return False, self.failure
        if not self.listener or not self.listener.is_alive():
            return False, (
                "Keyboard listener stopped. On Mac, allow Accessibility and "
                "Input Monitoring for this Python/Terminal app, then restart.")
        if self.ready.is_set():
            if sys.platform == "darwin" and not self.listener.IS_TRUSTED:
                return False, "Allow Accessibility for this Python/Terminal app, then restart."
            return True, None
        if time.monotonic() - self.started > 5:
            return False, "Keyboard listener did not start; check permissions and restart."
        return False, None

    def stop(self):
        self.key.set_enabled(False)
        if self.listener:
            self.listener.stop()
