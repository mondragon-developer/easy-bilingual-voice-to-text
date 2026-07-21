## Speech to Text v2.0.1 — signed Windows builds 🐉🔏

Same great app as v2.0.0 — now `SpeechToText.exe` is **digitally signed**
(Azure Trusted Signing, publisher-validated), so Windows can verify the
authenticity and integrity of your download. `checksums.txt` (SHA-256) is
also attached for manual verification.

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
Whisper transcription (nothing recorded ever leaves your machine), both
languages shown side by side, editable, with auto-copy to clipboard, global
hotkeys (`Ctrl+Alt+R`), and a mini always-on-top mode. Untick
**Translate (online)** and the app makes zero network calls — see
[Privacy & security](README.md#privacy--security).
