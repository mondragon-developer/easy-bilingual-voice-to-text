"""Remembering the checkbox states between launches.

Deliberately small: three booleans in a JSON file. The care here is not in the
format, it is in never letting a settings problem stop the app from starting.
A missing file, unreadable JSON, a wrong type, a read-only disk - every one of
them falls back to defaults and carries on.

Location matters more than it looks. The file must *not* live next to the
executable or in the working directory: a frozen macOS ``.app`` launched from
Finder has ``/`` as its working directory, so a relative path would fail
silently, and an app inside ``/Applications`` cannot write beside itself
without admin rights. Each platform's own per-user config directory is used
instead.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

APP_DIR_NAME = "SpeechToText"

#: Setting name -> default. Also the allowlist: anything else in the file is
#: ignored, so a hand-edited or downgraded file cannot inject unknown keys.
DEFAULTS = {
    "autocopy": True,
    "translate": True,
    "always_copy_english": False,
}


def default_path() -> Path:
    """The per-user settings file for this platform.

    Returns:
        Path: ``%APPDATA%\\SpeechToText\\settings.json`` on Windows,
        ``~/Library/Application Support/SpeechToText/settings.json`` on macOS,
        and ``$XDG_CONFIG_HOME`` (or ``~/.config``) elsewhere.
    """
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming")
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return base / APP_DIR_NAME / "settings.json"


class Settings:
    """Loads and stores the checkbox states, tolerating every failure."""

    def __init__(self, path=None):
        """
        Args:
            path: Where to keep the file. Defaults to ``default_path()``;
                tests pass a temporary path instead.
        """
        self.path = Path(path) if path is not None else default_path()

    def load(self) -> dict:
        """Read the saved settings, falling back to defaults per key.

        A corrupt file is not an error worth showing anyone: the app simply
        starts with defaults, and the next save overwrites the bad file.

        Returns:
            dict: Every key in ``DEFAULTS``, with saved values where they were
            present and of the right type.
        """
        values = dict(DEFAULTS)
        try:
            with open(self.path, encoding="utf-8") as fh:
                stored = json.load(fh)
        except (OSError, ValueError):
            return values          # missing, unreadable, or not valid JSON
        if not isinstance(stored, dict):
            return values          # a JSON list or string where we want an object
        for key, default in DEFAULTS.items():
            found = stored.get(key, default)
            # Only accept the type we expect. A string "false" is not False,
            # and silently coercing it would turn a typo into a setting.
            if isinstance(found, type(default)):
                values[key] = found
        return values

    def save(self, values: dict) -> bool:
        """Write the settings, ignoring anything not in ``DEFAULTS``.

        Written to a temporary file in the same directory and then renamed, so
        an interrupted write cannot leave a half-written file behind: the
        rename is atomic, and readers see either the old file or the new one.

        Args:
            values: Setting names to values. Unknown keys are dropped.

        Returns:
            bool: True if the file was written. False means the settings could
            not be saved - a read-only home directory, say - which the caller
            is expected to ignore, since the app still works without it.
        """
        payload = {key: values[key] for key in DEFAULTS if key in values}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp = tempfile.mkstemp(dir=str(self.path.parent),
                                            prefix=".settings-", suffix=".tmp")
            try:
                with os.fdopen(handle, "w", encoding="utf-8") as fh:
                    json.dump(payload, fh, indent=2, sort_keys=True)
                    fh.write("\n")
                os.replace(temp, self.path)
            except BaseException:
                # Never leave the scratch file behind on a failed write.
                try:
                    os.unlink(temp)
                except OSError:
                    pass
                raise
        except (OSError, ValueError, TypeError):
            return False
        return True
