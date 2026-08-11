## Speech to Text v2.1.6 - a Mac download, at last

Until now, running this on a Mac meant cloning the repo and installing a
Python that Apple does not ship, because the built-in `python3` bundles a Tk
that cannot draw the window. This release adds a **macOS disk image** that
carries its own Python and its own Tk, so none of that applies: download,
drag to Applications, open.

Windows is unchanged and still signed.

### Download for Mac

| You have | Download | Size |
|---|---|---|
| A Mac with **Apple Silicon** (M1 or later) | `SpeechToText-macOS-AppleSilicon.dmg` | ~75 MB |
| An **Intel** Mac | Source, see the [README](README.md#install---macos) | - |

**It is not signed by Apple, so macOS will refuse to open it the first time.**
Signing requires a paid Apple Developer account, which this project does not
have yet. Nothing is wrong with the download; macOS simply cannot tell who
built it. To allow it, once:

- **macOS 15 Sequoia and later:** double-click, accept the refusal, then open
  *System Settings > Privacy & Security*, scroll to the message about
  SpeechToText, and click **Open Anyway**.
- **macOS 14 and earlier:** right-click the app > **Open** > **Open**.

If you would rather not run unsigned software, the README's Option B builds
the identical app from source on your own machine. Either way you can check
the download against `checksums.txt` below:

```bash
shasum -a 256 ~/Downloads/SpeechToText-macOS-AppleSilicon.dmg
```

First launch downloads the `small` speech model once (~460 MB); after that it
starts in seconds. On an M5 Pro it transcribes at roughly **7x real time**,
about 2 seconds for a 14-second dictation, with punctuation, accents and
EN/ES detection all correct.

### Smaller install from source on macOS

`pip install -r requirements.txt` no longer installs the `keyboard` package
on macOS. Global hotkeys there need root, so the app has skipped them since
v2.1.5 and the package was never used - but it pulled in the entire `pyobjc`
suite to support code that never ran.

### The README now shows the app

Two screenshots, both from a real session rather than mock-ups: the app after
one English and one Spanish dictation, and the mini pill floating over the
desktop.

### Which download?

| You have | Download | Size |
|---|---|---|
| A PC with an **NVIDIA GPU** | `SpeechToText-Windows-GPU.zip` | ~1.5 GB |
| **Any other Windows PC** | `SpeechToText-Windows-CPU.zip` | ~95 MB |
| A Mac with **Apple Silicon** | `SpeechToText-macOS-AppleSilicon.dmg` | ~75 MB |
| An Intel Mac, or you prefer Python | *Source code* below + see the [README](README.md) | - |

**Install on Windows:** unzip, then run `SpeechToText.exe`. The first launch
downloads the speech model once (GPU ~3 GB, CPU ~460 MB); after that it starts
in seconds. Upgrading: unzip over your existing folder, the model stays put.

Windows builds remain **digitally signed** (verified publisher: Jose
Mondragon, via Azure Trusted Signing) with SHA-256 `checksums.txt` attached,
built from hash-pinned dependencies so a tampered package cannot reach a
signed binary.

### What the app does

Dictate in **English or Spanish** with automatic language detection, local
Whisper transcription (audio never leaves your machine), both languages side
by side, editable, auto-copy to clipboard, global hotkeys (`Ctrl+Alt+R`, on
Windows), and a mini always-on-top mode. Untick **Translate (online)** and
the app makes zero network calls; see
[Privacy & security](README.md#privacy--security).
