#!/usr/bin/env bash
#
# Builds the macOS release into <repo>/release.
#   SpeechToText-macOS-<arch>.dmg   - drag-to-Applications disk image
#
# The point of this build is that the .app carries its own Python and Tk, so
# a Mac user never installs Python, never learns which python3 they have, and
# never meets the Tk 8.5 black window described in the README.
#
# Stages mirror scripts/build_release.ps1 so CI can sign between them:
#   build : PyInstaller only (a signing step would go here)
#   dmg   : package the (possibly signed) .app into the disk image
#   all   : everything (default; local unsigned builds)
#
# The result is UNSIGNED and un-notarized. Gatekeeper will refuse it on first
# launch until the user allows it; see the README. Signing is a later task and
# only changes the middle of this script, not its shape.

set -euo pipefail

stage="${1:-all}"
case "$stage" in
    all | build | dmg) ;;
    *)
        echo "usage: $0 [all|build|dmg]" >&2
        exit 2
        ;;
esac

proj="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
out="$proj/release"
app="$proj/dist/SpeechToText.app"
python="${PYTHON:-python3}"
cd "$proj"

version="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' src/__init__.py)"
[ -n "$version" ] || { echo "could not read __version__ from src/__init__.py" >&2; exit 1; }

# arm64 -> AppleSilicon, x86_64 -> Intel. PyInstaller cannot cross-compile, so
# the build machine's architecture is the one the .dmg supports, and the file
# name has to say so rather than leave the user to find out by double-clicking.
case "$(uname -m)" in
    arm64) arch_label="AppleSilicon" ;;
    x86_64) arch_label="Intel" ;;
    *) arch_label="$(uname -m)" ;;
esac
dmg="$out/SpeechToText-macOS-${arch_label}.dmg"

if [ "$stage" = "all" ] || [ "$stage" = "build" ]; then
    # The whole reason this build exists. Apple's Python 3.9 ships Tk 8.5,
    # which never completes a redraw on recent macOS: building against it
    # would bundle the black window into the .app and hand it to every user.
    # Fail here rather than ship that.
    "$python" - <<'PY'
import sys
import tkinter

print(f"Tk {tkinter.TkVersion}")
if tkinter.TkVersion < 8.6:
    sys.exit("Tk 8.6+ required to build: this Python would ship a blank window")
PY

    # Icon: macOS wants .icns, and the repo keeps the artwork as one 1254px
    # PNG, so derive it here instead of committing a generated binary.
    iconset="$proj/build/SpeechToText.iconset"
    rm -rf "$iconset"
    mkdir -p "$iconset"
    for size in 16 32 128 256 512; do
        sips -z $size $size assets/mdragon.png \
            --out "$iconset/icon_${size}x${size}.png" >/dev/null
        sips -z $((size * 2)) $((size * 2)) assets/mdragon.png \
            --out "$iconset/icon_${size}x${size}@2x.png" >/dev/null
    done
    iconutil -c icns "$iconset" -o "$proj/build/icon.icns"

    "$python" -m PyInstaller --noconfirm --clean --windowed --name SpeechToText \
        --icon "$proj/build/icon.icns" \
        --add-data "$proj/assets:assets" \
        --collect-all customtkinter \
        --collect-all faster_whisper \
        --collect-all sounddevice \
        --osx-bundle-identifier com.mondragon.speechtotext \
        --exclude-module keyboard \
        main.py

    # Without NSMicrophoneUsageDescription macOS kills the app the moment it
    # opens the microphone, instead of showing a permission prompt. The rest
    # is what makes the bundle look like a real app rather than a script.
    plist="$app/Contents/Info.plist"
    set_plist() {
        /usr/libexec/PlistBuddy -c "Delete :$1" "$plist" 2>/dev/null || true
        /usr/libexec/PlistBuddy -c "Add :$1 $2 $3" "$plist"
    }
    set_plist NSMicrophoneUsageDescription string \
        "Speech to Text records your voice so it can transcribe it on this Mac. Audio is never uploaded."
    set_plist CFBundleShortVersionString string "$version"
    set_plist CFBundleVersion string "$version"
    set_plist NSHighResolutionCapable bool true
    set_plist LSMinimumSystemVersion string "11.0"

    # Editing Info.plist invalidates whatever signature PyInstaller applied,
    # and an arm64 binary with a broken signature will not launch at all. Sign
    # again, ad-hoc, so the .app runs once the user clears Gatekeeper.
    codesign --force --deep --sign - "$app"
    codesign --verify --deep --strict "$app"
fi

if [ "$stage" = "build" ]; then
    echo "BUILD_STAGE_DONE"
    exit 0
fi

mkdir -p "$out"
rm -f "$dmg"

# Staging folder: the .app plus the /Applications symlink users expect to drag
# onto. mktemp so a stale staging directory can never end up inside the image.
staging="$(mktemp -d)"
trap 'rm -rf "$staging"' EXIT
cp -R "$app" "$staging/"
ln -s /Applications "$staging/Applications"

hdiutil create \
    -volname "Speech to Text $version" \
    -srcfolder "$staging" \
    -ov -format UDZO \
    "$dmg" >/dev/null

echo "ASSET: $(basename "$dmg")  $(du -m "$dmg" | cut -f1) MB"
echo "BUILD_DONE"
