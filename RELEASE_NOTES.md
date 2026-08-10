## Speech to Text v2.1.5 - macOS actually works now

Running from source on a Mac was rough: a 3 GB download that served no
purpose, two alarming errors on every startup, and on recent macOS a window
that opened and never drew anything. All fixed. Windows users get one real
fix too, described below.

**No more 3 GB download on Mac.** The loader asked for `large-v3` on CUDA
first and fell back to `small` when that failed. But the model weights are
fetched *before* the device is initialised, so every Mac downloaded all
3.1 GB of `large-v3`, discovered it had no NVIDIA GPU, threw it away and
then loaded `small`. A first launch sat on a blank window for minutes.
macOS now goes straight to the CPU model. You can delete the wasted cache:

```bash
rm -rf ~/.cache/huggingface/hub/models--Systran--faster-whisper-large-v3
```

**Two false alarms on startup are gone.** A `Must be run as administrator`
traceback and three `divide by zero ... in matmul` warnings both looked like
crashes and neither was. The first came from global hotkeys, which need root
on macOS and failed inside their own listener thread where the app could not
catch them; they are now skipped on macOS entirely, which is what the README
always claimed happened. The second came from Apple's Accelerate BLAS
leaving the CPU's floating-point flags set after a perfectly correct matrix
multiply.

**A rare crash on startup, on every platform.** Background threads called
into the UI toolkit directly, which is not thread safe, so the thread that
loads the speech model could collide with the main loop mid-redraw. Running
the test suite 15 times crashed 3 of those runs outright and failed 3 more;
after the fix, 15 for 15 clean. The window for it was the moment the model
finished loading, so it read as a random fluke rather than a bug. **This one
affects Windows too** and is the reason to take this release.

**Do not use Apple's built-in `python3` on macOS.** It is Python 3.9 with
Tk 8.5, and on recent macOS Tk 8.5 never completes a redraw: the window
opens and stays a blank black rectangle. Four lines of plain `tkinter`
reproduce it with none of this project involved, so there is nothing the app
can do about it. The [README](README.md#install--macos) now says so up front
and gives two ways to install a Python that works, one of which needs no
admin password.

For the record, on an M5 Pro the default `small` model transcribes at about
**7x real time** (roughly 2 seconds for a 14-second dictation) with correct
punctuation, accents and EN/ES detection. `STT_MODEL=medium` costs about 3x
the time for identical output on clean dictation, so `small` really is the
right default.

Windows builds remain **digitally signed** (verified publisher: Jose
Mondragon, via Azure Trusted Signing) with SHA-256 `checksums.txt` attached,
built from hash-pinned dependencies so a tampered package cannot reach a
signed binary.

### Which download?

| You have | Download | Size |
|---|---|---|
| A PC with an **NVIDIA GPU** | `SpeechToText-Windows-GPU.zip` | ~1.5 GB |
| **Any other Windows PC** | `SpeechToText-Windows-CPU.zip` | ~95 MB |
| A Mac, or you prefer Python | *Source code* below + see the [README](README.md) | - |

**Install:** unzip, then run `SpeechToText.exe`. The first launch downloads
the speech model once (GPU ~3 GB, CPU ~460 MB); after that it starts in
seconds. Upgrading: unzip over your existing folder, the model stays put.

### Recent additions

**The top bar fits at any window size (v2.1.4).** Shrink the window toward
its minimum and the status message used to get cut off by the **Detected**
badge. It now has its own line and shows in full at every size.

**One entry per recording (v2.1.0).** Each recording starts its own entry,
separated by a blank line and headed with its number and time
(`#3 · 2:41 PM`). Both panes use the same number and time, so the English
and Español sides line up. The headers are for reading, not pasting:
**Copy**, `Ctrl+C`, `Ctrl+X` and auto-copy all leave them out; **Save
transcript** keeps them.

### What the app does

Dictate in **English or Spanish** with automatic language detection, local
Whisper transcription (audio never leaves your machine), both languages side
by side, editable, auto-copy to clipboard, global hotkeys (`Ctrl+Alt+R`, on
Windows), and a mini always-on-top mode. Untick **Translate (online)** and
the app makes zero network calls; see
[Privacy & security](README.md#privacy--security).
