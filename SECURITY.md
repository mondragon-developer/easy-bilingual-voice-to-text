# Security policy

## Reporting a vulnerability

Report privately through GitHub: **Security → Report a vulnerability** on
this repository ([open the form](../../security/advisories/new)). That
creates a private advisory only you and the maintainer can see.

Please don't open a public issue for a security bug, and don't post it in a
discussion or PR - a public report is a working exploit for everyone still
running the old build.

Expect a first response within about a week. If the report is valid, the fix
ships in the next release and the advisory is published with credit, unless
you'd rather stay anonymous.

## What's in scope

This is a single-user desktop app with no server, no accounts, and no
listening sockets. The interesting surface is:

- **The published binaries** - anything that makes a downloaded
  `SpeechToText.exe` behave differently from this source tree.
- **The release pipeline** - the GitHub Actions workflows that build and
  code-sign what people download.
- **The two network calls** - Whisper model download from Hugging Face, and
  the optional Google translation of transcript text. Both are documented in
  [Privacy & security](README.md#privacy--security).
- **Local data** - transcripts, the clipboard, and `selftest.log`.

Out of scope: findings that require an attacker who already has code
execution on the user's machine as that user, and reports against the model
weights themselves (upstream Whisper).

## Supported versions

The latest release only. This is a small app with a fast release path - the
fix goes out as a new version rather than a backport.

## How releases are protected

- **Code signing.** Every release binary is Authenticode-signed through
  Azure Trusted Signing (publisher: Jose Mondragon) and RFC3161-timestamped.
- **Checksums.** `checksums.txt` (SHA-256) ships with every release; see
  [Verify your download](README.md#verify-your-download).
- **Hash-pinned dependencies.** `requirements-lock.txt` pins exact versions
  *and* artifact hashes, installed with `--require-hashes`, so a hijacked
  re-upload to PyPI fails the build instead of shipping inside a signed
  binary.
- **SHA-pinned CI actions.** Every GitHub Action is pinned to a full commit
  SHA, not a movable tag, so a compromised action repo cannot reach the
  signing secrets. Dependabot updates the pins weekly.
- **Build verification.** The built `.exe` must load the speech model and
  transcribe (`--selftest`) inside CI before a release can publish.
