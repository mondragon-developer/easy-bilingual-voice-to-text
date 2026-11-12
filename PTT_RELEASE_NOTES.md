# Speech to Text - F9 English auto-paste preview 2

Hold F9, speak English or Spanish, and release. With **Paste English after
release** checked, the app inserts the English result into the active
destination after processing finishes. It does not press Enter.

This optional edition is based on v2.4.2. Python and dependencies are included.

## Download and open

- **SpeechToText-PTT-Windows-GPU.zip:** Windows x64 with an NVIDIA GPU,
  including CUDA libraries.
- **SpeechToText-PTT-Windows-CPU.zip:** Windows x64 without an NVIDIA GPU.
- **SpeechToText-PTT-macOS-AppleSilicon.dmg:** M-series Macs. No Intel installer.

Close the old SpeechToText app before opening this edition. On Windows,
extract the entire ZIP, open the SpeechToTextPTT folder, and double-click
SpeechToTextPTT.exe. On Mac, open the DMG, drag SpeechToTextPTT to Applications,
and open it. Wait for the model to load; first use downloads the models.

## Set up once per session

1. Leave **Hold F9 to talk** checked.
2. Check **Paste English after release** to enable automatic pasting.
3. If speaking Spanish, set **Translate** to **Offline** or **Online**.
4. Click the destination text field, hold F9, speak, and release.
5. Stay in the same field while processing finishes. Review the inserted text
   before submitting it yourself.

No command line or special launcher is required. The paste checkbox starts
off on a normal launch and applies to the current session. Auto-copy and
Always copy English are optional for manual clipboard use; automatic pasting
copies the fresh English result itself. It never pastes Spanish as a fallback
if English translation fails.

The destination is captured at release. Switching windows before processing
finishes cancels automatic pasting, leaving English on the clipboard.
Manual Record/Stop and safety timeout stops do not trigger automatic pasting.

## VS Code terminal: right-click works but F9 shows ^V

Some Windows PowerShell terminals forward Ctrl+V to the program running
inside them. In VS Code, press Ctrl+Shift+P, open **Preferences: Open Keyboard
Shortcuts (JSON)**, and add this object at the end of the existing array
(put a comma after the previous object):

```json
{
  "key": "ctrl+v",
  "command": "workbench.action.terminal.paste",
  "when": "terminalFocus"
}
```

Save, click the terminal, and try F9 again. Keep
**Terminal > Integrated: Send Keybindings To Shell** unchecked.
This binds Ctrl+V to the same direct paste command as the terminal's
context menu, only while the terminal is focused.

The app does not change your editor settings automatically. More help is
included in AUTO_PASTE.md and in the repository README.

## F9 without Fn and Mac permissions

Windows: enable your keyboard's Fn Lock or function-key mode if F9 normally
performs a media action. The setting depends on the keyboard manufacturer.

Mac: System Settings > Keyboard > Keyboard Shortcuts > Function Keys >
**Use F1, F2, etc. keys as standard function keys**. This changes the whole
function row; hold Fn for media functions afterwards.

Allow SpeechToTextPTT under Privacy & Security > **Accessibility** and,
if requested, **Input Monitoring**. Allow **Microphone** too. Quit and reopen
after granting permissions. The Mac app is ad-hoc signed, not Apple notarized;
use Privacy & Security > Open Anyway when macOS blocks its first launch.

## Optional F13

F13 uses the same flow and needs a key or button that sends both press and
release events. On Windows, use the included Use F13.bat. On Mac, quit first:

```sh
open -a SpeechToTextPTT --args --key F13
```

Advanced launchers can add --paste-english to start with automatic paste on.

## Validation and limits

Windows dictation and English paste in a VS Code terminal were confirmed
by the maintainer using the development build and the direct-paste binding.
Automated Windows/macOS tests cover hold/release ownership, destination
checks, UI processing, and simulated paste. Packaged checks load native
platform imports and real speech/translation/grammar models.

Physical F9 recording and paste on Mac, Windows Terminal, CPU-only hardware,
and Bluetooth buttons still need on-device testing. Successful shortcut
delivery cannot guarantee that every destination accepts it. Windows apps
running as administrator may reject input from a normally launched app.

Each hold has a five-minute fallback limit. A lost key-up or Bluetooth
disconnect may not be detected immediately; use Stop or disable Hold F9
if needed. This limit does not change manual recordings.

The regular v2.4.2 release remains available. This preview has signed Windows
binaries and SHA-256 checksums. Audio is processed locally; Online translation
sends transcript text to translation services. Use Offline after downloading
its models for local translation.
