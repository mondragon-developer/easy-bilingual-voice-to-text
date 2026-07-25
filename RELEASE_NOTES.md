## Speech to Text v2.1.2 — refreshed dependencies

A maintenance release. The app works the same; what ships inside it is newer.

**Sixteen dependencies updated**, including the UI toolkit (customtkinter
5.2.2 → 6.0.0) and the numeric and HTTP stacks (numpy, requests, cffi,
certifi, idna, filelock, soupsieve, tqdm, packaging, fsspec and others). The
window may render at a slightly different size than v2.1.1 did — the new
toolkit handles display scaling differently. Everything in it works the
same; if it looks off on your monitor, say so and it gets fixed.

Two updates were deliberately **not** taken: numpy 2.5.x needs Python 3.12
and this app builds on 3.11, and mpmath 1.4 contradicts what sympy accepts.
Both would have broken the build rather than the app.

**The build self-check now covers the UI toolkit too.** Every release runs
the shipped `SpeechToText.exe --selftest` in CI and refuses to publish if it
fails; until now that check loaded the speech model but never touched the
interface layer, so a packaging fault in the UI could have slipped past it.
That gap is closed — the check that gates this release verified both.

Windows builds remain **digitally signed** (verified publisher: Jose
Mondragon, via Azure Trusted Signing) with SHA-256 `checksums.txt` attached,
built from hash-pinned dependencies so a tampered package cannot reach a
signed binary.

### Which download?

| You have | Download | Size |
|---|---|---|
| A PC with an **NVIDIA GPU** | `SpeechToText-Windows-GPU.zip` | ~1.5 GB |
| **Any other Windows PC** | `SpeechToText-Windows-CPU.zip` | ~95 MB |
| A Mac, or you prefer Python | *Source code* below + see the [README](README.md) | — |

**Install:** unzip → run `SpeechToText.exe`. The first launch downloads the
speech model once (GPU ~3 GB, CPU ~460 MB); after that it starts in seconds.
Upgrading: unzip over your existing folder, the model stays put.

### Recent additions

**One entry per recording (v2.1.0).** Each recording starts its own entry,
separated by a blank line and headed with its number and time
(`#3 · 2:41 PM`). Both panes use the same number and time, so the English
and Español sides line up. The headers are for reading, not pasting —
**Copy**, `Ctrl+C`, `Ctrl+X` and auto-copy all leave them out; **Save
transcript** keeps them.

### What the app does

Dictate in **English or Spanish** — automatic language detection, local
Whisper transcription (audio never leaves your machine), both languages
side by side, editable, auto-copy to clipboard, global hotkeys
(`Ctrl+Alt+R`), mini always-on-top mode. Untick **Translate (online)** and
the app makes zero network calls — see
[Privacy & security](README.md#privacy--security).
