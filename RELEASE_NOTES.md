## Speech to Text v2.0.2 — critical fix: "Model failed to load" 🛠️

**If you downloaded v2.0.0 or v2.0.1, please update to this version.**
Those builds showed *"Model failed to load: [WinError 3]"* at startup and
could not transcribe. The cause was a packaging bug in how the app looked
for GPU libraries inside the frozen build — fixed here, and covered by a
regression test.

**New safeguard:** every release now runs a built-in self-test in CI — the
actual shipped `SpeechToText.exe` must load the Whisper model and transcribe
before the release can publish. You can run it yourself anytime:
`SpeechToText.exe --selftest` (writes `selftest.log`, exit code 0 = healthy).

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

### What the app does

Dictate in **English or Spanish** — automatic language detection, local
Whisper transcription (audio never leaves your machine), both languages
side by side, editable, auto-copy to clipboard, global hotkeys
(`Ctrl+Alt+R`), mini always-on-top mode. Untick **Translate (online)** and
the app makes zero network calls — see
[Privacy & security](README.md#privacy--security).
