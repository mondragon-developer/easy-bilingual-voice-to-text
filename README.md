# Speech to Text — EN / ES

Dictate in **English or Spanish** — the app auto-detects the language,
transcribes it with OpenAI's Whisper model (running **locally on your
machine**), and shows the text in **both languages** side by side. Both panes
are fully editable with native copy/cut/paste.

## Features

- 🎙️ **Auto language detection** — speak EN or ES, no switch to flip
- 🌐 **Both languages always shown** — spoken text in its pane, translation in the other
- ✅ **Precise** — Whisper produces punctuated, correctly spelled text
- ⚡ **Fast** — GPU-accelerated on NVIDIA cards (17x realtime on a modern GPU); automatic CPU mode everywhere else
- ⏱️ **No time limit** — Record / Stop whenever you want
- ✏️ **Editable panes** — fix anything by hand; right-click menu, Ctrl+A/C/X/V, undo
- 📋 **Auto-copy** — dictated text lands on your clipboard, ready to paste anywhere
- 🔘 **Mini mode** — collapse to a tiny always-on-top pill at the screen edge
- ⌨️ **Global hotkeys** (Windows) — record from inside any app
- 🔒 **Private by design** — audio never leaves your computer. The translation
  pane sends each recording's transcribed **text** (never audio) to Google
  Translate; untick **Translate (online)** and nothing leaves your machine
  at all

## Install — Windows

### Option A: Download (no Python needed)

1. Go to [**Releases**](../../releases) and download the zip that fits your PC:
   - **`SpeechToText-Windows-GPU.zip`** (~1.5 GB) — for PCs with an NVIDIA GPU (much faster)
   - **`SpeechToText-Windows-CPU.zip`** (~300 MB) — for any Windows PC
2. Unzip anywhere, open the folder, and run **`SpeechToText.exe`**.
3. First launch downloads the speech model once (GPU build ~3 GB,
   CPU build ~460 MB) — later launches start in seconds.

> **Windows SmartScreen note:** the first time you run the app Windows may say
> "Windows protected your PC" because the download is not yet code-signed.
> Click **More info → Run anyway**. The full source code is in this repository
> if you want to verify what the app does.

### Option B: Run from source

```bash
git clone https://github.com/mondragon-developer/speech-to-text-en-es.git
cd speech-to-text-en-es
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+. GPU acceleration needs an NVIDIA card with recent
drivers; otherwise the app automatically uses CPU mode.

## Install — macOS

Run from source (a signed/notarized .app download is planned):

```bash
git clone https://github.com/mondragon-developer/speech-to-text-en-es.git
cd speech-to-text-en-es
python3 -m pip install -r requirements.txt
python3 main.py
```

macOS notes:

- **Microphone permission**: the first recording triggers a permission prompt
  (or enable it in *System Settings → Privacy & Security → Microphone* for
  your terminal/Python).
- **Speed**: there is no NVIDIA CUDA on Mac, so transcription runs on CPU and
  the app automatically selects the lighter `small` model. On Apple Silicon
  it is fast enough for dictation. Prefer more accuracy? Run with
  `STT_MODEL=medium python3 main.py`.
- **Global hotkeys** (Ctrl+Alt+R from other apps) are not available on macOS
  without elevated permissions — the app detects this and simply disables
  them. In-app shortcuts (Ctrl+R / Ctrl+S) still work.

## How to use

| Action | How |
|---|---|
| Start / stop recording | **● Record** button, `Ctrl+R`, or `Ctrl+Alt+R` from **any** app (Windows) |
| Mini mode / restore | **🗕 Mini** button or `Ctrl+Alt+M` (Windows) |
| Copy a pane | **Copy** button under the pane |
| Save both languages to .txt | **Save transcript** or `Ctrl+S` |
| Edit text | Click and type; right-click for Cut/Copy/Paste; `Ctrl+Z` undo |
| Auto-copy after dictation | Checkbox in the bottom bar (on by default) |
| Translation on/off | **Translate (online)** checkbox — untick to stay 100% offline |

**Dictate-anywhere workflow (Windows):** minimize to the pill →
`Ctrl+Alt+R` → speak → `Ctrl+Alt+R` → wait for the green ✓ → `Ctrl+V` in
whatever app you're writing in.

Each recording **appends**: the spoken text goes to its language's pane and
the translation to the other, so each pane always holds the full transcript
in one language — even if you switch languages between recordings.

## Choosing a model

The app picks automatically: `large-v3` (best accuracy) on NVIDIA GPUs,
`small` (fast) on CPU. Override with the `STT_MODEL` environment variable:
`tiny`, `base`, `small`, `medium`, `large-v3`, `distil-large-v3`.

## Privacy & security

- Speech recognition runs **100% locally** — your voice never leaves the machine.
  Models are downloaded once over HTTPS from the official
  `huggingface.co/Systran/faster-whisper-*` repositories.
- When **Translate (online)** is ticked (default), the latest recording's
  **transcribed text** (never audio, never your edits) is sent to Google
  Translate. No account, no API key. **Untick it and the app makes zero
  network calls.**
- **About the global hotkeys (Windows):** Ctrl+Alt+R / Ctrl+Alt+M are
  implemented with the Python [`keyboard`](https://github.com/boppreh/keyboard)
  library, which registers a system-wide keyboard hook — the standard
  technique every hotkey utility uses, and one some antivirus tools flag
  because keyloggers use hooks too. This app registers exactly two hotkey
  patterns and **never reads, stores, or transmits keystrokes** — the entire
  usage is ~10 lines in [`src/app.py`](src/app.py) (`_register_global_hotkeys`),
  and the hook is released on exit. On macOS and Linux the hook needs
  elevated permissions, so the app simply disables global hotkeys there.
- Auto-copy writes to your clipboard only when the checkbox is on.
- No telemetry, no analytics, no accounts. Transcripts are saved only when
  you click Save. Audio is never written to disk.

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not open the microphone" | Check the OS default input device and mic permissions |
| Status says CPU but I have an NVIDIA GPU | Update NVIDIA drivers; the status bar shows the exact CUDA error |
| Translation pane says translation failed | You're offline or Google is unreachable — the spoken pane still works |
| First start is slow | The model downloads once to `~/.cache/huggingface`; later starts are fast |

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/        # 43 unit tests
```

```
main.py              entry point
src/
  recorder.py        threaded 16 kHz mic capture (sounddevice -> numpy)
  transcriber.py     faster-whisper wrapper + language auto-detection
  translator.py      EN<->ES translation with sentence-aware chunking
  app.py             CustomTkinter two-pane UI, mini mode, global hotkeys
tests/               pytest suite (logic, recorder, transcriber, translator, UI)
```

## License

[MIT](LICENSE) © 2026 Jose Mondragon
