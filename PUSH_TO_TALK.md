# Optional hold-to-talk: F9 now, F13 later

This extension adds **hold to record, release to transcribe/translate/copy**
on Windows and macOS. It adds files only: `main.py`, `src/`, the existing
requirements, settings and release workflows are unchanged. Open the normal
app to get precisely the existing behavior; open the new launcher to opt in.

F9 and F13 use the same implementation. F9 is physically available on laptop
keyboards. F13 generally needs an external keyboard, a programmable button
or a key remapping. There is no difference in transcription or translation.

## Install and run from source

This is a **source extension**, not yet included in the published `.exe` or
`.dmg`. Close any other copy of SpeechToText before testing it (two copies
can contend for the microphone and clipboard). Use the same Python environment
that already runs `main.py`. A fresh environment also needs the original
`requirements.txt`. On Mac, use the Python/Tk setup in the main README.

Windows, from the repository folder:

```powershell
python -m pip install -r requirements-ptt.txt
python push_to_talk.py
```

Mac, from the repository folder (replace `python3` with your existing app's
Python executable if necessary):

```sh
python3 -m pip install -r requirements-ptt.txt
python3 push_to_talk.py
```

The app adds a **Hold F9 to talk** checkbox and a listener status line.
Wait for the speech model to be ready, hold F9, speak, then release. The
original processing pipeline and your existing settings decide the result:

- Translate Off: transcribe only.
- Translate Offline/Online: keep the existing bilingual behavior.
- Auto-copy enabled: copy the resulting text.
- Always copy English enabled (and translation on): Spanish speech copies
  its English translation. Paste with Ctrl+V / Cmd+V when processing finishes.

The extension does not force those settings or paste into other applications.
The original Record/Stop buttons, mini mode, in-app shortcuts and Windows
Ctrl+Alt+R / Ctrl+Alt+M shortcuts remain available.

### One physical key on Mac and Windows

On Mac, enable **System Settings > Keyboard > Keyboard Shortcuts > Function
Keys > Use F1, F2, etc. keys as standard function keys** to use F9 without Fn.
This changes the whole function row; use Fn for its media actions afterwards.
On Windows laptops, Fn Lock or a firmware function-row setting may be needed.
The extension listens for F9, not the media action printed on the same key.

On Mac, grant **Accessibility** and, if requested, **Input Monitoring** to the
Terminal/Python application hosting the launcher, then quit and reopen it.
Microphone permission is still required as before. Do not run as root.

F9 is **reserved globally while the checkbox is on**, including while loading
or processing. It will not also set breakpoints or trigger another app's F9
action. Uncheck it to restore ordinary F9 use. Modified shortcuts such as
Shift+F9 or Ctrl+F9 pass through, provided the modifier was held first.
Releasing F9 still stops an owned recording if a modifier was pressed later.

### Switch to F13 without changing code

```sh
python push_to_talk.py --key F13
```

Use `python3` on Mac if that is your interpreter. The hardware must send a
real **key-down when pressed and key-up when released**. A device that sends
short taps repeatedly while held is not equivalent and is not supported.
Pair the button with one computer at a time. No network or phone is needed.

## Limits and recovery

- Holding a key produces only one recording. Very short taps released before
  the UI handles them are ignored. Presses during model loading/processing
  are ignored; release and press again when ready.
- Releasing the key stops only the recording that press started. It never
  stops one started independently with the ordinary Record button.
- Disabling the checkbox finishes an active hold recording through the usual
  processing pipeline. An already-held key must be released before reenabling
  can start another recording.
- A listener failure disables the extension and stops its owned recording;
  the ordinary controls remain usable. Restart after correcting permissions.
- The extension stops a hold after **5 minutes**, or after the UI resumes from
  a pause of more than 2 seconds. To change the hold limit, use
  `--max-seconds 600` (1–1800 allowed). The original manual recording limit
  remains unchanged.
- A keyboard hook cannot reliably detect every Bluetooth disconnection,
  lost release, secure-input screen or silent OS hook removal. If release
  is missed, use the ordinary Stop button or disable the checkbox; the hold
  limit is the fallback, not an immediate disconnect guarantee.
- Keyboard hooks are subject to macOS secure input and Windows secure/elevated
  desktops. Do not assume they work on login/UAC/password screens.
- Closing the app removes the listener. Nothing is installed at login and
  no extra network endpoint or telemetry is added.

## Validation

Portable behavior and simulated native-filter tests (no mic or keyboard hook):

```sh
python -m pytest tests/ptt -q
```

Optional integration tests with real Tk widgets, fake audio/model services
and fake keyboard delivery (requires a desktop/display):

```sh
python -m pytest tests/ptt/test_ui.py --run-ptt-ui -q
```

These tests do **not** establish physical keyboard or microphone compatibility.
Before merging/releasing, do this on both Windows and Mac:

1. Open the normal launcher: original controls still work, F9 is unchanged.
2. Open this launcher, wait for Ready, hold F9 for a Spanish sentence and
   release. One recording stops and processes; English copies when selected.
3. Repeat with another app in front, then in mini mode; paste and check text.
4. Hold for several seconds: no repeated starts. Try a quick tap and a press
   during processing: neither should create a delayed recording.
5. Start manually, press/release F9: manual recording continues. Stop normally.
6. Start with F9, stop manually, start manually again, then release F9:
   the new manual recording continues.
7. Disable the checkbox: F9 regains its normal action. Reenable and repeat.
8. Check Ctrl+Alt+R / Ctrl+Alt+M on Windows; verify permission-denied behavior
   on Mac. Quit: the selected key is no longer intercepted.
9. When hardware is available, repeat using `--key F13`, including disconnect
   while held. Confirm the physical device's release semantics separately.

No existing release is replaced by this extension. Packaging into separate
signed Windows/macOS downloads is a later step after physical validation.
