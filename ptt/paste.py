"""Paste into the release-time destination only while it is still active.

No window activation, Enter key, clipboard reading, or stored dictation.
Platform objects are created on startup, not inside the keyboard hook.
"""

import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Destination:
    pid: int
    window: int
    focus: int = 0


class PasteError(RuntimeError):
    pass


class WindowsPaste:
    def __init__(self):
        import ctypes as c
        from ctypes import wintypes as w

        self.c = c
        self.w = w
        self.user = c.WinDLL("user32", use_last_error=True)

        class GuiInfo(c.Structure):
            _fields_ = [("cbSize", w.DWORD), ("flags", w.DWORD),
                        ("hwndActive", w.HWND), ("hwndFocus", w.HWND),
                        ("hwndCapture", w.HWND), ("hwndMenuOwner", w.HWND),
                        ("hwndMoveSize", w.HWND), ("hwndCaret", w.HWND),
                        ("rcCaret", w.RECT)]

        class KeyboardInput(c.Structure):
            _fields_ = [("vk", w.WORD), ("scan", w.WORD),
                        ("flags", w.DWORD), ("time", w.DWORD),
                        ("extra", c.c_size_t)]

        class MouseInput(c.Structure):
            _fields_ = [("dx", w.LONG), ("dy", w.LONG),
                        ("data", w.DWORD), ("flags", w.DWORD),
                        ("time", w.DWORD), ("extra", c.c_size_t)]

        class InputUnion(c.Union):
            _fields_ = [("keyboard", KeyboardInput), ("mouse", MouseInput)]

        class Input(c.Structure):
            _fields_ = [("kind", w.DWORD), ("value", InputUnion)]

        self.GuiInfo, self.Input = GuiInfo, Input
        self.user.GetForegroundWindow.argtypes = []
        self.user.GetForegroundWindow.restype = w.HWND
        self.user.GetWindowThreadProcessId.argtypes = [w.HWND, c.POINTER(w.DWORD)]
        self.user.GetWindowThreadProcessId.restype = w.DWORD
        self.user.GetGUIThreadInfo.argtypes = [w.DWORD, c.POINTER(GuiInfo)]
        self.user.GetGUIThreadInfo.restype = w.BOOL
        self.user.GetAsyncKeyState.argtypes = [c.c_int]
        self.user.GetAsyncKeyState.restype = w.SHORT
        self.user.SendInput.argtypes = [w.UINT, c.POINTER(Input), c.c_int]
        self.user.SendInput.restype = w.UINT
        self.user.GetKeyboardLayout.argtypes = [w.DWORD]
        self.user.GetKeyboardLayout.restype = w.HKL
        self.user.MapVirtualKeyExW.argtypes = [w.UINT, w.UINT, w.HKL]
        self.user.MapVirtualKeyExW.restype = w.UINT

    def _paste_events(self, target):
        # VS Code/Electron resolves shortcuts using the physical key code.
        # Supply scan codes for shortcut handlers. VS Code's PowerShell
        # forwarding rule is separate; see AUTO_PASTE.md for its binding.
        thread = self.user.GetWindowThreadProcessId(target.window, None)
        if not thread:
            raise PasteError("Destination closed; English is copied. Paste it manually.")
        layout = self.user.GetKeyboardLayout(thread)
        scans = [self.user.MapVirtualKeyExW(vk, 4, layout) for vk in (0xA2, 0x56)]
        if not all(scans):
            raise PasteError("Keyboard layout unavailable; English is copied. Paste it manually.")
        events = (self.Input * 4)()
        for event, (scan, release) in zip(events, (
                (scans[0], False), (scans[1], False),
                (scans[1], True), (scans[0], True))):
            event.kind = 1
            event.value.keyboard.scan = scan & 0xFF
            event.value.keyboard.flags = 0x08 | (0x02 if release else 0)
            if scan & 0xFF00 == 0xE000:
                event.value.keyboard.flags |= 0x01
        return events

    def capture(self):
        c, w, u = self.c, self.w, self.user
        window = u.GetForegroundWindow()
        pid = w.DWORD()
        thread = u.GetWindowThreadProcessId(window, c.byref(pid))
        info = self.GuiInfo()
        info.cbSize = c.sizeof(info)
        if (not window or not thread or pid.value == os.getpid()
                or not u.GetGUIThreadInfo(thread, c.byref(info))
                or info.flags & 0x1E or not info.hwndFocus):
            return None
        return Destination(pid.value, window, info.hwndFocus)

    def paste(self, target):
        if target is None or self.capture() != target:
            raise PasteError("Destination changed; English is copied. Paste it manually.")
        if any(self.user.GetAsyncKeyState(vk) & 0x8000
               for vk in (0x10, 0x11, 0x12, 0x5B, 0x5C, 0x56)):
            raise PasteError("A shortcut key is held; English is copied. Paste it manually.")
        # One batch prevents our Ctrl/V transitions from interleaving.
        events = self._paste_events(target)
        if self.capture() != target:
            raise PasteError("Destination changed; English is copied. Paste it manually.")
        if self.user.SendInput(4, events, self.c.sizeof(self.Input)) != 4:
            # Release only our synthetic keys after a partial injection.
            self.user.SendInput(2, self.c.cast(self.c.byref(events, 2 * self.c.sizeof(self.Input)),
                                             self.c.POINTER(self.Input)),
                                self.c.sizeof(self.Input))
            raise PasteError("Windows blocked pasting; English is copied. Paste it manually.")


class MacPaste:
    def __init__(self):
        import AppKit
        import Quartz
        self.workspace = AppKit.NSWorkspace.sharedWorkspace()
        self.q = Quartz

    def capture(self):
        app = self.workspace.frontmostApplication()
        if app is None or app.processIdentifier() == os.getpid():
            return None
        pid = app.processIdentifier()
        q = self.q
        windows = q.CGWindowListCopyWindowInfo(
            q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements,
            q.kCGNullWindowID) or []
        for window in windows:
            if (window.get(q.kCGWindowOwnerPID) == pid
                    and window.get(q.kCGWindowLayer) == 0):
                return Destination(pid, window[q.kCGWindowNumber])
        return None

    def paste(self, target):
        if target is None or self.capture() != target:
            raise PasteError("Destination changed; English is copied. Paste it manually.")
        q = self.q
        flags = q.CGEventSourceFlagsState(q.kCGEventSourceStateCombinedSessionState)
        modifiers = (q.kCGEventFlagMaskShift | q.kCGEventFlagMaskControl
                     | q.kCGEventFlagMaskAlternate | q.kCGEventFlagMaskCommand)
        if flags & modifiers:
            raise PasteError("A shortcut key is held; English is copied. Paste it manually.")
        # Command-V, never Return. Accessibility permission is also needed
        # by the F9 listener; no additional service or helper is launched.
        down = q.CGEventCreateKeyboardEvent(None, 9, True)
        up = q.CGEventCreateKeyboardEvent(None, 9, False)
        if down is None or up is None:
            raise PasteError("macOS could not paste; English is copied. Paste it manually.")
        for event in (down, up):
            q.CGEventSetFlags(event, q.kCGEventFlagMaskCommand)
            q.CGEventPost(q.kCGHIDEventTap, event)


def create_paster():
    if sys.platform == "win32":
        return WindowsPaste()
    if sys.platform == "darwin":
        return MacPaste()
    raise PasteError("Automatic pasting supports Windows and macOS only.")
