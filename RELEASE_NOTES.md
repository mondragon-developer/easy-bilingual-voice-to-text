## Speech to Text v2.0.0 — first public release 🐉

Dictate in **English or Spanish** — the app detects the language
automatically, transcribes **100% locally** with OpenAI's Whisper model, and
shows your words in **both languages** side by side, editable and ready to
paste anywhere.

### Which download?

| You have | Download | Size |
|---|---|---|
| A PC with an **NVIDIA GPU** | `SpeechToText-Windows-GPU.zip` | ~1.8 GB |
| **Any other Windows PC** | `SpeechToText-Windows-CPU.zip` | ~0.5 GB |
| A Mac, or you prefer Python | *Source code* below + see the [README](README.md) | — |

**Install:** unzip → run `SpeechToText.exe`. The first launch downloads the
speech model once (GPU ~3 GB, CPU ~460 MB); after that it starts in seconds.

> Windows SmartScreen may warn because this release is not yet code-signed —
> click **More info → Run anyway**. All source code is in this repository.

### Highlights

- Automatic EN/ES language detection — just speak
- Both languages always shown: spoken text + translation, both editable
- Whisper `large-v3` on NVIDIA GPUs (~17x realtime), `small` on CPU
- Record/stop with no time limit; global hotkeys `Ctrl+Alt+R` / `Ctrl+Alt+M`
- Mini always-on-top widget; auto-copy to clipboard for instant pasting
- Privacy: audio never leaves your machine; untick **Translate (online)**
  and the app makes **zero** network calls — see
  [Privacy & security](README.md#privacy--security)
- 46-test suite; security-reviewed before release;
  `requirements-lock.txt` records every bundled dependency version
