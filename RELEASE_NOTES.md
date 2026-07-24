## Speech to Text v2.1.0 — one entry per recording

Dictate, stop, dictate again — each recording now starts its **own entry**
instead of running into the one before it. A blank line separates them, and
a small gray header gives each entry a number and the time it was recorded
(`#3 · 2:41 PM`; the date is added on the first entry of a day). Both panes
use the same number and time for a given recording, so the English and
Español sides line up. Numbering restarts at `#1` once both panes are empty.

This is the mini-mode workflow fix: dictate all afternoon from the pill,
then open the window and see where each piece starts and when you said it.

**The headers are for reading, not for pasting.** The **Copy** button,
`Ctrl+C` on a selection, `Ctrl+X`, and auto-copy all leave them out — what
lands on your clipboard is just the words. **Save transcript** is the
exception and keeps them, since a saved `.txt` is a record of when things
were said.

Nothing else changed: same transcription, same speed, same privacy model.

Windows builds remain **digitally signed** (verified publisher: Jose
Mondragon, via Azure Trusted Signing) with SHA-256 `checksums.txt` attached.

### Which download?

| You have | Download | Size |
|---|---|---|
| A PC with an **NVIDIA GPU** | `SpeechToText-Windows-GPU.zip` | ~1.5 GB |
| **Any other Windows PC** | `SpeechToText-Windows-CPU.zip` | ~95 MB |
| A Mac, or you prefer Python | *Source code* below + see the [README](README.md) | — |

**Install:** unzip → run `SpeechToText.exe`. The first launch downloads the
speech model once (GPU ~3 GB, CPU ~460 MB); after that it starts in seconds.
Upgrading from v2.0.x: unzip over your existing folder, the model stays put.

### What the app does

Dictate in **English or Spanish** — automatic language detection, local
Whisper transcription (audio never leaves your machine), both languages
side by side, editable, auto-copy to clipboard, global hotkeys
(`Ctrl+Alt+R`), mini always-on-top mode. Untick **Translate (online)** and
the app makes zero network calls — see
[Privacy & security](README.md#privacy--security).
