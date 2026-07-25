# macOS support - implementation plan

**Status:** planned, not started. Deferred deliberately, not forgotten.
**Blocked on:** Task 0 below, which only you can run.
**Written:** 2026-07-25, against v2.1.4.

Read Task 0 first. Its outcome decides whether the rest is worth doing at
all, and it costs about fifteen minutes.

## Where things stand today

The app already runs on macOS from source. What does not exist yet is a Mac
*download*, and two features degrade:

| | Windows today | macOS today | After this plan |
|---|---|---|---|
| Install | Download a signed zip | Clone the repo, `pip install` | Download a signed `.dmg` |
| Transcription | GPU, `large-v3` | CPU, `small` | CPU, unchanged (see Task 5) |
| Global hotkeys | Work everywhere | **Disabled** | Work everywhere |
| Mini pill | Rounded, transparent | Dark rectangle | Rounded |
| Panes, stamps, copy, translate | Work | Work | Work |

The reason transcription is CPU-only is worth stating plainly, because no
amount of hardware changes it: `src/transcriber.py` asks for CUDA and falls
back to CPU, and the engine underneath it (CTranslate2, via faster-whisper)
has **no Apple GPU backend at all**. On an M-series Mac the GPU cores sit
idle no matter what is configured. Task 5 is the only thing that changes
that, and it is a much bigger job than Tasks 1-4.

---

## Task 0 - Does CPU transcription feel fast enough? (you, ~15 min)

Everything else depends on this answer, so do it before spending money or
effort. On the Mac:

```bash
git clone https://github.com/mondragon-developer/easy-bilingual-voice-to-text.git
cd easy-bilingual-voice-to-text
python3 -m pip install -r requirements.txt
python3 main.py
```

If Python cannot find `tkinter`, install a Python that bundles Tk - the
python.org installer does, or `brew install python-tk` for Homebrew Python.

Then dictate a few normal sentences and judge the wait between pressing Stop
and seeing text.

- Try the default first (it will pick `small` automatically).
- Then try `STT_MODEL=medium python3 main.py` for better accuracy.
- The status bar shows the model and device it actually chose.

**Pass:** `medium` (or `small`) returns text quickly enough that you would
use it daily. Proceed to Task 1.

**Fail:** even `small` feels slow. Stop - do not buy an Apple Developer
membership yet. Task 5 becomes the real question instead, because packaging
a slow app nicely does not make it useful.

Note the microphone permission prompt on the first recording. If you miss
it: System Settings > Privacy & Security > Microphone, enable it for your
terminal.

---

## Task 1 - Apple signing credentials (you)

**This is the part only you can do**, because it is tied to your identity
and your payment method. Everything here happens on the Mac, in a browser
and in Keychain Access. Nothing in this section touches the repo.

Your Windows certificate (Azure Trusted Signing) does **not** carry over.
Apple is a separate authority, a separate cost, and a separate process.

### 1.1 Enroll in the Apple Developer Program

1. Go to <https://developer.apple.com/programs/enroll/>.
2. Sign in with your Apple ID. It must have two-factor authentication on.
3. Choose **Individual** unless you specifically want the company name on
   the certificate. Individual is faster: Organization requires a D-U-N-S
   number and legal-entity verification.
4. Pay **$99 USD/year**.
5. Wait for approval. Individual is usually a day or two, occasionally
   longer if Apple asks for ID.

### 1.2 Create the signing certificate

The type you need is **Developer ID Application**. That is the one for apps
distributed outside the App Store. Not "Apple Development", not "Mac App
Distribution" - those will not help here.

1. Open **Keychain Access** on the Mac.
2. Menu: *Keychain Access > Certificate Assistant > Request a Certificate
   From a Certificate Authority*.
3. Enter your email and name, choose **Saved to disk**, and save the
   `.certSigningRequest` file.
4. Go to <https://developer.apple.com/account/resources/certificates/list>.
5. Click **+**, choose **Developer ID Application**, upload the request file
   from step 3.
6. Download the resulting `.cer` and double-click it to install it into your
   login keychain.

### 1.3 Export the certificate for CI

The build machine needs the certificate *and* its private key, as one file:

1. In Keychain Access, open **My Certificates**.
2. Find `Developer ID Application: <your name> (<TEAMID>)`.
3. Right-click it, **Export**, save as `.p12`, and set a strong password.
   Keep this password - it becomes a GitHub secret.
4. Convert it for GitHub:

   ```bash
   base64 -i DeveloperID.p12 | pbcopy
   ```

   That puts the encoded certificate on your clipboard.

**Treat the `.p12` like a house key.** Anyone holding it and its password
can sign software as you. Do not commit it, do not email it. It goes into
GitHub Secrets and nowhere else.

### 1.4 Create notarization credentials

Signing proves who built the app. **Notarization** is a separate step where
Apple scans it and blesses it, and without it macOS still warns users. Use
an App Store Connect API key - it is the CI-friendly option and does not
expire the way passwords do.

1. Go to <https://appstoreconnect.apple.com/access/integrations/api>.
2. Under **Team Keys**, generate a key with the **Developer** role.
3. Record the **Issuer ID** (a UUID at the top of the page) and the
   **Key ID**.
4. Download the `AuthKey_<KEYID>.p8`. **Apple lets you download it once.**
   Save it somewhere safe, then encode it the same way:

   ```bash
   base64 -i AuthKey_XXXXXXXX.p8 | pbcopy
   ```

### 1.5 Find your Team ID

<https://developer.apple.com/account> > *Membership details*. It is a
ten-character code like `A1B2C3D4E5`.

### 1.6 Add the GitHub secrets

Repo > Settings > Secrets and variables > Actions > New repository secret.
Create these six:

| Secret name | What goes in it |
|---|---|
| `APPLE_CERT_P12_BASE64` | The base64 blob from step 1.3 |
| `APPLE_CERT_PASSWORD` | The password you set on the `.p12` |
| `APPLE_TEAM_ID` | The ten-character code from 1.5 |
| `APPLE_API_KEY_ID` | Key ID from 1.4 |
| `APPLE_API_ISSUER_ID` | Issuer ID from 1.4 |
| `APPLE_API_KEY_P8_BASE64` | The base64 blob from 1.4 |

**Hand-off checklist.** When all six exist, tell me - that is my signal to
start Task 2. I never need to see any of the values; the workflow reads them
by name, the same way the Windows signing job already does.

---

## Task 2 - macOS build in CI (me)

Adds a `macos-latest` job to `.github/workflows/release.yml`, so a version
bump publishes a Mac download next to the Windows zips.

- A macOS build script alongside `scripts/build_release.ps1`, since
  PowerShell and PyInstaller's Windows flags do not carry over.
- An `Info.plist` carrying `NSMicrophoneUsageDescription`. Without it macOS
  kills the app instead of asking for the microphone.
- An entitlements file. Hardened runtime is mandatory for notarization, and
  it needs `com.apple.security.device.audio-input` for the mic. PyInstaller
  bundles unsigned dylibs, so `com.apple.security.cs.disable-library-validation`
  is likely required too - I will confirm against the real build rather than
  guess.
- Sign, package as `.dmg`, notarize with `notarytool`, staple the ticket,
  attach to the release with a SHA-256 checksum like the Windows assets.
- Verification in CI: `codesign --verify --deep --strict` and
  `spctl -a -t open --context context:primary-signature`, so a broken
  signature fails the build instead of shipping.

One honest limit: I cannot test any of this from Windows. PyInstaller does
not cross-compile, so the first real proof is a CI run, and the first *user*
proof is you opening the `.dmg` on your Mac.

**Without Task 1**, I can still do Task 2 and produce an unsigned `.dmg`.
You would right-click > Open on first launch to get past Gatekeeper, and so
would anyone else who downloads it. That is a legitimate way to start if you
want to defer the $99.

## Task 3 - Global hotkeys on macOS (me)

The feature you actually use: dictate into any app without switching to it.

The current `keyboard` library needs root on macOS, which is why the app
disables hotkeys there. The replacement is a macOS-native path, either
`pynput` (Quartz event taps, needs Accessibility permission) or Carbon
`RegisterEventHotKey` through `pyobjc` (no permission prompt, but a smaller
hotkey vocabulary).

Contained work: `_register_global_hotkeys` in `src/app.py` is one function
of about ten lines, already written to degrade gracefully when registration
fails. The user-visible cost is one permission grant in System Settings >
Privacy & Security > Accessibility.

Worth noting these two tasks reinforce each other: macOS remembers
permission grants per signing identity, so a *signed* app keeps its
Accessibility permission across updates. An unsigned one can lose it on
every rebuild.

## Task 4 - Mini pill appearance (me)

The rounded pill uses `-transparentcolor`, which is Windows-only; the code
already catches the failure, which is why the Mac shows a dark rectangle
instead of crashing. macOS has its own transparency attribute, so this is a
small platform branch in `MiniWidget`.

## Task 5 - Apple GPU speed (optional, large)

Only worth opening if Task 0 came back slow. It means adding a second speech
engine behind the existing `Transcriber` interface - whisper.cpp with Metal,
or MLX - and keeping both engines working. Substantially more work than
Tasks 1-4 combined, and it changes what the app ships and how it is tested.

Do not start this speculatively. Decide it with real numbers from Task 0.

---

## Cost and time

| Item | Cost | Elapsed |
|---|---|---|
| Task 0 - test on Mac | free | 15 min, yours |
| Task 1 - Apple enrollment + certs | $99/year | 1-2 days, mostly waiting on Apple |
| Task 2 - CI build, sign, notarize | free | mine |
| Task 3 - hotkeys | free | mine |
| Task 4 - pill | free | mine |
| Task 5 - Metal engine | free | mine, and much larger |

The $99 is the only money, it recurs annually, and it buys exactly one
thing: no Gatekeeper warning. Everything else works without it.

## Order of work

1. **You:** Task 0. Report whether the speed is usable.
2. **You:** Task 1, only if Task 0 passed and you want the warning gone.
   Ping me when the six secrets exist.
3. **Me:** Task 2, then 3, then 4 - each shipping as its own release, the
   same way v2.1.2 through v2.1.4 went out.
4. **Both:** revisit Task 5 only if Task 0 said the speed is not good enough.
