"""System-wide hotkeys, and the do-nothing stand-in for platforms without them.

Two implementations behind one interface, chosen by ``create``. The window
asks for a manager and calls the same three methods either way, so the
platform test lives here instead of inside the UI.
"""

import sys

HOTKEY_RECORD = "ctrl+alt+r"
HOTKEY_MINI = "ctrl+alt+m"


class NullHotkeyManager:
    """Registers nothing, on platforms where global hotkeys are unavailable.

    On macOS the ``keyboard`` backend needs root, and it fails inside its own
    listener thread: ``add_hotkey`` returns happily and a traceback appears on
    stderr seconds later, so the failure cannot be caught at the call site.
    Not registering at all is the only clean way to keep that traceback off
    the console. Linux has the same root requirement.
    """

    #: False, so the UI knows not to advertise hotkeys it does not have.
    available = False

    def register(self, on_record, on_mini):
        """Accept the callbacks and do nothing with them."""

    def unregister(self):
        """Nothing was registered, so nothing to undo."""


class KeyboardHotkeyManager:
    """Global hotkeys via the ``keyboard`` package. Windows only."""

    def __init__(self):
        self.available = False

    def register(self, on_record, on_mini):
        """Bind the record and mini hotkeys system-wide.

        Failure is not fatal: the app works without global hotkeys, so a
        refusal here only clears ``available``.

        Args:
            on_record: Called when the record hotkey fires.
            on_mini: Called when the mini-mode hotkey fires.
        """
        try:
            import keyboard
            keyboard.add_hotkey(HOTKEY_RECORD, on_record)
            keyboard.add_hotkey(HOTKEY_MINI, on_mini)
            self.available = True
        except Exception:  # noqa: BLE001 - any failure means "no hotkeys"
            self.available = False

    def unregister(self):
        """Release the hooks, if any were taken."""
        if not self.available:
            return
        try:
            import keyboard
            keyboard.unhook_all_hotkeys()
        except Exception:  # noqa: BLE001 - shutting down anyway
            pass


def create():
    """Return the hotkey manager for this platform.

    Returns:
        KeyboardHotkeyManager on Windows, NullHotkeyManager everywhere else.
    """
    if sys.platform == "win32":
        return KeyboardHotkeyManager()
    return NullHotkeyManager()
