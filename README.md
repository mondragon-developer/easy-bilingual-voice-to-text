# Speech to Text — EN / ES

![Tests](https://github.com/mondragon-developer/easy-bilingual-voice-to-text/actions/workflows/ci.yml/badge.svg)
![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)

Dictate in **English or Spanish** — the app auto-detects the language,
transcribes it with OpenAI's Whisper model (running **locally on your
machine**), and shows the text in **both languages** side by side. Both panes
are fully editable with native copy/cut/paste.

## Features

- 🎙️ **Auto language detection** — speak EN or ES, no switch to flip
- 🌐 **Both languages always shown** — spoken text in its pane, translation in the other
- 🗂️ **One entry per recording** — each dictation starts a new block headed by its number and time; the headers are never copied or pasted
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
   - **`SpeechToText-Windows-CPU.zip`** (~95 MB) — for any Windows PC
2. Unzip anywhere, open the folder, and run **`SpeechToText.exe`**.
3. First launch downloads the speech model once (GPU build ~3 GB,
   CPU build ~460 MB) — later launches start in seconds.

> **✅ Signed for Windows:** releases from v2.0.1 onward are digitally signed
> by verified publisher **Jose Mondragon** through Microsoft Azure Trusted
> Signing — right-click `SpeechToText.exe` → *Properties → Digital
> Signatures* to verify. Each release also ships a `checksums.txt` (SHA-256)
> so you can confirm your download is byte-identical to what CI built.
> If SmartScreen still shows a prompt on very new releases (reputation for
> fresh signatures builds up over days), the publisher name shown is mine —
> and the full source code is in this repository if you want to see exactly
> what the app does.

### Option B: Run from source

```bash
git clone https://github.com/mondragon-developer/easy-bilingual-voice-to-text.git
cd easy-bilingual-voice-to-text
pip install -r requirements.txt
python main.py
```

Requires Python 3.10+. GPU acceleration needs an NVIDIA card with recent
drivers; otherwise the app automatically uses CPU mode.

## Install — macOS

Run from source (a signed/notarized .app download is planned):

```bash
git clone https://github.com/mondragon-developer/easy-bilingual-voice-to-text.git
cd easy-bilingual-voice-to-text
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

A signed Mac download, working global hotkeys, and the rounded mini pill are
planned — the steps, costs and order of work are written up in
[MACOS_PLAN.md](MACOS_PLAN.md).

## How to use

| Action | How |
|---|---|
| Start / stop recording | **● Record** button, `Ctrl+R`, or `Ctrl+Alt+R` from **any** app (Windows) |
| Mini mode / restore | **🗕 Mini** button or `Ctrl+Alt+M` (Windows) |
| Copy a pane | **Copy** button under the pane (entry headers are left out) |
| Save both languages to .txt | **Save transcript** or `Ctrl+S` (headers kept) |
| Edit text | Click and type; right-click for Cut/Copy/Paste; `Ctrl+Z` undo |
| Auto-copy after dictation | Checkbox in the bottom bar (on by default) |
| Translation on/off | **Translate (online)** checkbox — untick to stay 100% offline |

**Dictate-anywhere workflow (Windows):** minimize to the pill →
`Ctrl+Alt+R` → speak → `Ctrl+Alt+R` → wait for the green ✓ → `Ctrl+V` in
whatever app you're writing in.

Each recording **appends**: the spoken text goes to its language's pane and
the translation to the other, so each pane always holds the full transcript
in one language — even if you switch languages between recordings.

Every recording is its own **entry**, set off by a blank line and a small
gray header with a number and the time (`#3 · 2:41 PM`) — the date is added
on the first entry of the day. Both panes use the same number and time for a
given recording, so the two sides line up. Numbering restarts at `#1` once
both panes are empty.

The headers are for reading, not for pasting: **Copy**, `Ctrl+C` on a
selection, `Ctrl+X`, and auto-copy all leave them out, so you paste only the
words. **Save transcript** is the exception — the `.txt` file keeps the
headers, since a saved transcript is a record of when things were said.

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
- **Signed, reproducible releases:** Windows binaries are code-signed
  (Azure Trusted Signing, verified publisher), built by GitHub Actions from
  the exact versions in `requirements-lock.txt` — the build logs are public
  in the Actions tab — and published with SHA-256 checksums.
- **Supply chain:** `requirements-lock.txt` pins exact versions *and* artifact
  hashes, installed with `--require-hashes`, so a hijacked re-upload to PyPI
  fails the build rather than shipping inside a signed binary. Every GitHub
  Action is pinned to a commit SHA instead of a movable tag, keeping a
  compromised action away from the signing secrets. Dependabot updates both
  weekly. To report a vulnerability, see [SECURITY.md](SECURITY.md).

## Troubleshooting

| Problem | Fix |
|---|---|
| "Could not open the microphone" | Check the OS default input device and mic permissions |
| Status says CPU but I have an NVIDIA GPU | Update NVIDIA drivers; the status bar shows the exact CUDA error |
| Translation pane says translation failed | You're offline or Google is unreachable — the spoken pane still works |
| First start is slow | The model downloads once to `~/.cache/huggingface`; later starts are fast |
| "Model failed to load: [WinError 3]" | You're on v2.0.0/v2.0.1 — [update to v2.0.2+](../../releases/latest), which fixed this packaging bug |

### Verify your download

- **Integrity:** compare your zip's SHA-256 against `checksums.txt` attached
  to the release — `Get-FileHash SpeechToText-Windows-*.zip` in PowerShell.
- **Authenticity:** right-click `SpeechToText.exe` → *Properties → Digital
  Signatures* — the publisher is Jose Mondragon.
- **Health:** run `SpeechToText.exe --selftest` — it loads the speech model
  and transcribes a test signal without opening a window, writes
  `selftest.log`, and exits with code 0 when everything works. CI runs this
  exact check on every release before it can publish.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest tests/        # 60 tests
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

### Releasing

Bump `__version__` in `src/__init__.py`, rewrite `RELEASE_NOTES.md` (it
becomes the release body), and push to `main`. CI tests the code, builds and
signs both Windows zips, self-tests the built exe, and publishes the release
tagged with that version. Pushes that leave the version alone don't release.

### Dependencies

`requirements-lock.txt` is what release builds install, and it carries
artifact hashes, so any version change has to be followed by:

```bash
python scripts/lock_hashes.py
```

That rewrites the file from the PyPI API. The pinned set must be the complete
resolved closure — under `--require-hashes` pip refuses to install anything
missing a pin, so a forgotten transitive dependency fails the release build.

## License

[MIT](LICENSE) © 2026 Jose Mondragon
