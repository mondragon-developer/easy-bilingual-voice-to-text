## Speech to Text v2.1.1 — dependency and supply-chain hardening

No changes to how the app works. This release updates what ships inside it
and tightens how it is built.

**Updated dependencies.** Seven pinned packages moved to patched versions
(urllib3, requests, idna, filelock, protobuf, soupsieve, and the bundled
cuDNN runtime). The GPU build had been shipping a cuDNN wheel that NVIDIA
has since withdrawn from PyPI; it is now on the current supported one. None
of these were exploitable through this app's two fixed endpoints, but there
is no reason to ship known-vulnerable code.

**The build now verifies bytes, not just version numbers.**
`requirements-lock.txt` pins exact artifact hashes and CI installs it with
`--require-hashes`, so a hijacked re-upload to PyPI fails the build instead
of ending up inside a signed binary. Pinning the hashes also surfaced five
transitive packages that were being installed unpinned; the lockfile is now
the complete dependency closure.

**Every GitHub Action is pinned to a commit SHA** rather than a movable tag,
so a compromised action repository cannot reach the code-signing secrets.
Dependabot keeps both the action pins and the Python pins current.

The repository now has a [security policy](SECURITY.md) with private
vulnerability reporting.

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
Upgrading: unzip over your existing folder, the model stays put.

### New in v2.1.0: one entry per recording

Each recording starts its own entry, separated by a blank line and headed
with its number and time (`#3 · 2:41 PM`). Both panes use the same number
and time, so the English and Español sides line up. The headers are for
reading, not pasting — **Copy**, `Ctrl+C`, `Ctrl+X` and auto-copy all leave
them out; **Save transcript** keeps them.

### What the app does

Dictate in **English or Spanish** — automatic language detection, local
Whisper transcription (audio never leaves your machine), both languages
side by side, editable, auto-copy to clipboard, global hotkeys
(`Ctrl+Alt+R`), mini always-on-top mode. Untick **Translate (online)** and
the app makes zero network calls — see
[Privacy & security](README.md#privacy--security).
