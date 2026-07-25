## Speech to Text v2.1.4 — the top bar fits at any window size

Companion to v2.1.3, which fixed the same problem at the bottom of the
window. Shrink the window toward its minimum and the status message used to
run out of room and get cut off by the **Detected** badge, reading
`Ready — press Record and start speaking (EN`.

The Record button, badge, level meter and **Mini** button all need a fixed
amount of space, so the status line was always the one that gave. It now has
its own line under them and shows in full at every window size.

Cosmetic only; nothing behaved wrongly. Everything else is unchanged from
v2.1.3.

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

**Refreshed dependencies (v2.1.2).** Sixteen packages updated, including the
UI toolkit; the release self-check now covers the interface layer as well as
the speech model.

### What the app does

Dictate in **English or Spanish** — automatic language detection, local
Whisper transcription (audio never leaves your machine), both languages
side by side, editable, auto-copy to clipboard, global hotkeys
(`Ctrl+Alt+R`), mini always-on-top mode. Untick **Translate (online)** and
the app makes zero network calls — see
[Privacy & security](README.md#privacy--security).
