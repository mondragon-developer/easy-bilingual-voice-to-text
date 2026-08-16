"""Unit tests for src.settings.

The happy path is two lines. Everything worth testing here is a failure the
app has to survive without complaining: no file, bad JSON, wrong types, a
directory it cannot write to.
"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from src.settings import DEFAULTS, Settings, default_path


@pytest.fixture
def store(tmp_path):
    return Settings(tmp_path / "settings.json")


class TestLoading:
    def test_no_file_yet_gives_the_defaults(self, store):
        assert store.load() == DEFAULTS

    def test_saved_values_come_back(self, store):
        store.save({"autocopy": False, "translate": False,
                    "always_copy_english": True})
        assert store.load() == {"autocopy": False, "translate": False,
                                "always_copy_english": True}

    def test_a_missing_key_falls_back_to_its_default(self, store):
        store.path.write_text(json.dumps({"autocopy": False}), encoding="utf-8")
        loaded = store.load()
        assert loaded["autocopy"] is False
        assert loaded["translate"] == DEFAULTS["translate"]

    def test_unknown_keys_are_ignored(self, store):
        store.path.write_text(json.dumps({"autocopy": False, "nonsense": 1}),
                              encoding="utf-8")
        assert set(store.load()) == set(DEFAULTS)


class TestSurvivingBadFiles:
    """None of these may raise. The app must start regardless."""

    def test_corrupt_json_gives_defaults(self, store):
        store.path.write_text("{not json at all", encoding="utf-8")
        assert store.load() == DEFAULTS

    def test_empty_file_gives_defaults(self, store):
        store.path.write_text("", encoding="utf-8")
        assert store.load() == DEFAULTS

    def test_json_that_is_not_an_object_gives_defaults(self, store):
        store.path.write_text("[1, 2, 3]", encoding="utf-8")
        assert store.load() == DEFAULTS

    @pytest.mark.parametrize("bad", ["false", 0, 1, None, [], {}])
    def test_a_wrong_type_falls_back_rather_than_being_coerced(self, store, bad):
        """The string "false" is not False; coercing would turn a typo into a
        setting the user never chose."""
        store.path.write_text(json.dumps({"autocopy": bad}), encoding="utf-8")
        assert store.load()["autocopy"] is DEFAULTS["autocopy"]

    def test_a_directory_where_the_file_should_be(self, store):
        store.path.mkdir(parents=True)
        assert store.load() == DEFAULTS


class TestSaving:
    def test_save_reports_success(self, store):
        assert store.save(dict(DEFAULTS)) is True
        assert store.path.exists()

    def test_unknown_keys_are_not_written(self, store):
        store.save({**DEFAULTS, "sneaky": "value"})
        assert "sneaky" not in json.loads(store.path.read_text(encoding="utf-8"))

    def test_missing_keys_are_simply_omitted(self, store):
        store.save({"autocopy": False})
        assert json.loads(store.path.read_text(encoding="utf-8")) == {
            "autocopy": False}

    def test_parent_directories_are_created(self, tmp_path):
        store = Settings(tmp_path / "a" / "b" / "settings.json")
        assert store.save(dict(DEFAULTS)) is True
        assert store.path.exists()

    def test_a_blocked_location_reports_failure_but_does_not_raise(self, tmp_path):
        """A read-only home is not worth interrupting anyone over.

        The blocked path is made by putting a *file* where the parent
        directory needs to be, so ``mkdir`` fails for real on every platform.
        An earlier version of this test used an absolute path like
        ``/nope/settings.json`` and assumed it was unwritable - which held on
        macOS and failed on the Windows CI runner, where the user could
        happily create ``C:\\nope``.
        """
        blocker = tmp_path / "in-the-way"
        blocker.write_text("I am a file, not a directory", encoding="utf-8")
        store = Settings(blocker / "settings.json")
        assert store.save(dict(DEFAULTS)) is False

    def test_an_os_error_while_writing_reports_failure(self, store):
        """Covers the read-only-disk case without depending on a real one."""
        with patch("pathlib.Path.mkdir", side_effect=PermissionError("read-only")):
            assert store.save(dict(DEFAULTS)) is False

    def test_a_blocked_location_still_loads_defaults(self, tmp_path):
        blocker = tmp_path / "in-the-way"
        blocker.write_text("not a directory", encoding="utf-8")
        assert Settings(blocker / "settings.json").load() == DEFAULTS

    def test_no_temporary_files_are_left_behind(self, store):
        store.save(dict(DEFAULTS))
        leftovers = [p.name for p in store.path.parent.iterdir()
                     if p.name.startswith(".settings-")]
        assert leftovers == []

    def test_a_failed_write_leaves_the_previous_file_intact(self, store):
        """The write is atomic, so a crash mid-save cannot corrupt what was
        already there."""
        store.save({"autocopy": False})
        with patch("json.dump", side_effect=OSError("disk full")):
            assert store.save({"autocopy": True}) is False
        assert store.load()["autocopy"] is False

    def test_round_trip_survives_a_reopen(self, tmp_path):
        path = tmp_path / "settings.json"
        Settings(path).save({"always_copy_english": True})
        assert Settings(path).load()["always_copy_english"] is True


class TestLocation:
    """The file must never land in the working directory: a frozen macOS .app
    launched from Finder has / as its cwd."""

    def test_the_path_is_absolute(self):
        assert default_path().is_absolute()

    def test_it_is_not_in_the_current_directory(self):
        assert default_path().parent != Path.cwd()

    def test_it_is_named_for_the_app(self):
        assert default_path().parent.name == "SpeechToText"

    @pytest.mark.skipif(sys.platform != "darwin", reason="macOS layout")
    def test_macos_uses_application_support(self):
        assert "Library/Application Support" in str(default_path())

    def test_windows_uses_appdata(self):
        with patch.object(sys, "platform", "win32"), \
             patch.dict(os.environ, {"APPDATA": r"C:\Users\x\AppData\Roaming"}):
            assert "Roaming" in str(default_path())

    def test_linux_honours_xdg_config_home(self, tmp_path):
        with patch.object(sys, "platform", "linux"), \
             patch.dict(os.environ, {"XDG_CONFIG_HOME": str(tmp_path)}):
            assert str(tmp_path) in str(default_path())
