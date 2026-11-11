# Speech to Text — F9 push-to-talk preview 1

Standalone optional edition based on v2.4.2. Windows and macOS downloads
contain Python and dependencies: you do not need to install Python.

## Downloads

- **Windows-GPU.zip:** Windows x64 with an NVIDIA GPU, including CUDA libraries.
- **Windows-CPU.zip:** Windows x64 without an NVIDIA GPU; smaller download.
- **macOS-AppleSilicon.dmg:** M-series Macs. Intel Macs can run from source.

Windows: unzip, open the SpeechToTextPTT folder, and launch SpeechToTextPTT.exe.
Mac: open the DMG, drag SpeechToTextPTT to Applications and open it.
Close your old SpeechToText window first: do not run both editions together.
This preview uses the same saved translation and clipboard preferences.

## Use F9

Wait for the model to finish loading. Hold F9 to record, then release it to
transcribe and translate. Enable Auto-copy and Always copy English to speak
Spanish and paste English. Uncheck Hold F9 to talk to restore normal F9 use.
Record/Stop, mini mode, and the existing Windows shortcuts still work.

On Mac, enable standard F1/F2/etc. keys in Keyboard > Keyboard Shortcuts >
Function Keys so F9 works without Fn. This changes the whole function row;
use Fn for the media functions afterwards. Windows laptops may need Fn Lock.

**Mac permissions:** allow SpeechToTextPTT under Privacy & Security >
Accessibility and, if requested, Input Monitoring. Allow Microphone too.
Quit and reopen the app after granting permissions. The Mac build is ad-hoc
signed, not Apple notarized; use Privacy & Security > Open Anyway on first
launch, as with the existing Mac edition.

## F13 later

F13 runs the identical recording flow. It needs a keyboard or programmable
button that sends key-down on press and key-up on release.

Windows: open the included Use F13.bat launcher.

Mac, after quitting the app:

```sh
open -a SpeechToTextPTT --args --key F13
```

## Preview status

Automated tests include platform-specific dependencies and UI/pipeline checks
with synthetic key events and fake audio, plus real speech/translation/grammar
model checks in the packaged applications. **Physical hold/release, microphone
recording, macOS permissions and Bluetooth hardware still need user testing.**

Each hold has a five-minute fallback limit. A lost key-up or Bluetooth
disconnect is not always detected immediately; use Stop or disable the
checkbox if needed. This limit does not change manual recordings.

The regular v2.4.2 release remains available and is not replaced. This preview
is built from the optional feature branch. SHA-256 hashes accompany the files.
