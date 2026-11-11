"""Build separate PTT binaries without touching the existing release scripts.

python scripts/build_ptt.py build
python scripts/build_ptt.py package    # after platform signing and self-tests
"""

import argparse
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
NAME = "SpeechToTextPTT"
DIST = ROOT / "dist" / "ptt"
WORK = ROOT / "build" / "ptt"
OUT = ROOT / "release" / "ptt"
VERSION = "2.4.2"


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True, cwd=ROOT)


def build():
    WORK.mkdir(parents=True, exist_ok=True)
    import tkinter
    if tkinter.TkVersion < 8.6:
        raise RuntimeError("Tk 8.6+ is required")
    args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
            "--windowed", "--name", NAME, "--distpath", DIST,
            "--workpath", WORK / "work", "--specpath", WORK,
            "--add-data", f"{ROOT / 'assets'}{os.pathsep}assets",
            "--exclude-module", "pytest"]
    for package in ("customtkinter", "faster_whisper", "sounddevice", "pynput"):
        args += ["--collect-all", package]
    if sys.platform == "win32":
        args += ["--icon", ROOT / "assets" / "icon.ico"]
    elif sys.platform == "darwin":
        iconset = WORK / "PTT.iconset"
        iconset.mkdir(exist_ok=True)
        for size in (16, 32, 128, 256, 512):
            for scale, suffix in ((1, ""), (2, "@2x")):
                run("sips", "-z", size * scale, size * scale,
                    ROOT / "assets" / "mdragon.png", "--out",
                    iconset / f"icon_{size}x{size}{suffix}.png")
        run("iconutil", "-c", "icns", iconset, "-o", WORK / "ptt.icns")
        args += ["--icon", WORK / "ptt.icns", "--osx-bundle-identifier",
                 "com.mondragon.speechtotext.ptt", "--exclude-module", "keyboard",
                 # setuptools 83 no longer provides pkg_resources. PyObjC's
                 # optional test namespace otherwise triggers its legacy
                 # PyInstaller runtime hook, crashing before our entry point.
                 "--exclude-module", "pkg_resources"]
    else:
        raise RuntimeError("Build this edition on Windows or macOS")
    run(*args, ROOT / "ptt_release.py")
    if sys.platform == "darwin":
        import plistlib
        app = DIST / f"{NAME}.app"
        plist = app / "Contents" / "Info.plist"
        with plist.open("rb") as file:
            info = plistlib.load(file)
        info.update(
            NSMicrophoneUsageDescription="Record your voice for transcription on this Mac.",
            CFBundleDisplayName="Speech to Text PTT",
            CFBundleShortVersionString=VERSION, CFBundleVersion=VERSION,
            NSHighResolutionCapable=True, LSMinimumSystemVersion="11.0")
        with plist.open("wb") as file:
            plistlib.dump(info, file)
        run("codesign", "--force", "--deep", "--sign", "-", app)
        run("codesign", "--verify", "--deep", "--strict", app)


def package():
    OUT.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        folder = DIST / NAME
        if not (folder / f"{NAME}.exe").is_file():
            raise RuntimeError("Build the executable first")
        shutil.copy2(ROOT / "PTT_RELEASE_NOTES.md", folder / "READ_ME.md")
        for filename, arguments in (("Use F13.bat", "--key F13"),
                                    ("Spanish F9.bat", "")):
            prefix = "set STT_MODEL=medium\n" if filename.startswith("Spanish") else ""
            (folder / filename).write_text(
                '@echo off\n' + prefix + f'start "" "%~dp0{NAME}.exe" {arguments}\n',
                encoding="utf-8")
        shutil.make_archive(str(OUT / "SpeechToText-PTT-Windows-CPU"),
                            "zip", DIST, NAME)
        spec = importlib.util.find_spec("nvidia")
        if spec is None:
            raise RuntimeError("NVIDIA runtime dependencies missing for GPU build")
        dlls = []
        for root in spec.submodule_search_locations:
            dlls.extend(Path(root).glob("*/bin/*.dll"))
        if not dlls:
            raise RuntimeError("No NVIDIA runtime DLLs found")
        for dll in dlls:
            shutil.copy2(dll, folder / "_internal" / dll.name)
        # Best/GPU mode already uses large-v3; do not offer a CPU model override.
        (folder / "Spanish F9.bat").unlink()
        shutil.make_archive(str(OUT / "SpeechToText-PTT-Windows-GPU"),
                            "zip", DIST, NAME)
    elif sys.platform == "darwin":
        arch = "AppleSilicon" if platform.machine() == "arm64" else "Intel"
        with tempfile.TemporaryDirectory() as temp:
            staging = Path(temp)
            shutil.copytree(DIST / f"{NAME}.app", staging / f"{NAME}.app", symlinks=True)
            (staging / "Applications").symlink_to("/Applications")
            shutil.copy2(ROOT / "PTT_RELEASE_NOTES.md", staging / "READ_ME.md")
            run("hdiutil", "create", "-volname", f"Speech to Text PTT {VERSION}",
                "-srcfolder", staging, "-ov", "-format", "UDZO",
                OUT / f"SpeechToText-PTT-macOS-{arch}.dmg")
    else:
        raise RuntimeError("Package on Windows or macOS")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("build", "package"))
    {"build": build, "package": package}[parser.parse_args().stage]()
