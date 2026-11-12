# Paste English after releasing F9

Available in the **v2.4.2-ptt.2** optional edition for Windows and macOS.
Open SpeechToTextPTT normally. No command line is needed.

1. Wait for the speech model to load.
2. Leave **Hold F9 to talk** checked and check **Paste English after release**.
3. For Spanish dictation, select **Offline** or **Online** translation.
4. Click the field where you want to write.
5. Hold F9, speak, and release. Stay in that field while processing finishes.
6. The English result is copied and the app sends Ctrl+V on Windows or
   Command+V on macOS. The app never sends Enter.

The paste checkbox applies to this session and starts off on a normal launch.
An optional shortcut argument, `--key F9 --paste-english`, starts with it on.
Auto-copy and Always copy English remain useful for manual clipboard use;
they are not required for automatic pasting.

## If a terminal shows ^V instead of the text

On Windows, VS Code has a PowerShell-specific Ctrl+V binding,
`workbench.action.terminal.pastePwsh`. For text it sends a control character
to the shell, relying on PSReadLine to paste. Programs running inside that
terminal may display `^V` instead. Right-click > Paste uses a different
command that reads and pastes the clipboard directly.

1. In VS Code, press **Ctrl+Shift+P**.
2. Select **Preferences: Open Keyboard Shortcuts (JSON)**.
3. Add this object as the last entry inside the existing `[ ... ]` array.
   Keep existing entries and add a comma after the previous one.

```json
{
  "key": "ctrl+v",
  "command": "workbench.action.terminal.paste",
  "when": "terminalFocus"
}
```

4. Save the file.
5. In Settings, search for `terminal.integrated.sendKeybindingsToShell`
   and leave it unchecked, its default.
6. Click inside the terminal and test Ctrl+V, then hold and release F9.

No SpeechToText restart is needed for this VS Code setting. The binding affects
only a focused terminal and uses the same command as its context menu.
SpeechToText does not rewrite editor settings automatically.

This resolved the maintainer's VS Code terminal test on Windows.
Sources: [VS Code's PowerShell paste handler](https://github.com/microsoft/vscode/blob/main/src/vs/workbench/contrib/terminalContrib/sendSequence/browser/terminal.sendSequence.contribution.ts)
and [terminal keyboard routing](https://code.visualstudio.com/docs/terminal/advanced#keyboard-shortcuts-and-the-shell).

## Other paste problems

| Symptom | Check |
|---|---|
| No automatic paste anywhere | Open the PTT edition, check Paste English after release, and stop recording by releasing F9. |
| It copies but does not paste after switching apps | Keep the same destination active until processing finishes. Paste manually if you switch. |
| Spanish appears in the app but English is missing | Enable Offline or Online translation and wait for it to finish. Failed translation never triggers Spanish fallback pasting. |
| F9 changes volume or another media function | Use your keyboard's Fn Lock/function-key setting. On Mac, enable standard function keys in Keyboard Shortcuts > Function Keys. |
| F9 or paste fails on Mac | Allow Microphone and Accessibility, plus Input Monitoring if prompted, then quit and reopen SpeechToTextPTT. |
| Paste fails only in an elevated Windows app | Windows may block input between privilege levels. Use the destination's manual paste command. |
| A different terminal ignores Ctrl+V or Command+V | Check that terminal's Paste shortcut or use its context menu. Windows Terminal and other terminal apps have not yet been validated for this preview. |

## Destination and recording behavior

The destination is captured when F9/F13 is released. If the active window
changes, pasting is skipped and English remains on the clipboard. Windows
also checks the native focused control. Web pages and some modern apps can
have several fields inside one native control, so stay in the same field.
The app does not restore focus or activate another window.

Automatic pasting only applies to recordings stopped by releasing F9 or F13.
Manual stops, disabling push-to-talk, and timeout stops do not trigger it.
Only the latest recording's completed English result is pasted, once.
Shortcut delivery does not prove that every receiving app accepted the text.

Windows uses layout-aware scan codes for Ctrl+V. This is separate from the
VS Code PowerShell routing rule above; scan codes alone do not override it.
Mac uses Command+V and requires on-device confirmation of the full recording
and paste flow.
