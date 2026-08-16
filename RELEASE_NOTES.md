## Speech to Text v2.1.8 - dictate in Spanish, paste in English

Dictate in **English or Spanish**, get both languages side by side, with all
speech recognition running on your own computer.

**New in this release:** a checkbox called **Always copy English**. Tick it and
whatever you dictate - English or Spanish - the *English* version is what lands
on your clipboard, ready to paste. Speak Spanish, paste English, without
touching either panel.

---

# Which file do I download?

| Your computer | Download this | Size |
|---|---|---|
| **Mac** with Apple Silicon (M1 or later) | `SpeechToText-macOS-AppleSilicon.dmg` | ~81 MB |
| **Windows PC** with an NVIDIA graphics card | `SpeechToText-Windows-GPU.zip` | ~1.5 GB |
| **Any other Windows PC** | `SpeechToText-Windows-CPU.zip` | ~98 MB |
| An **Intel** Mac | No download yet - see the [README](README.md#install---macos) | - |

Not sure which Mac you have? Apple menu > **About This Mac**. If the *Chip*
line says Apple M-something, you have Apple Silicon.

---

# Installing on a Mac

**1.** Download `SpeechToText-macOS-AppleSilicon.dmg` and open it.

**2.** You will see two app icons and an Applications folder. Drag
**SpeechToText** onto **Applications**.

> There is a second icon called **Modo espanol**. Only drag that one too if you
> dictate in Spanish - see *Better Spanish* below. English-only users can
> ignore it completely.

**3.** Open **SpeechToText** from your Applications folder.

**4. macOS will refuse to open it.** You will see:

> *"Apple could not verify SpeechToText is free of malware that may harm your
> Mac or compromise your privacy."*

**This is expected. Nothing is wrong with the download.** The app is not
registered with Apple's paid developer programme, so macOS cannot confirm who
built it. To allow it:

- Click **Done** on that message. **Do not click *Move to Trash*.**
- Open **System Settings** > **Privacy & Security**.
- Scroll down to the message about SpeechToText and click **Open Anyway**.
- Authenticate with Touch ID or your password.
- **Open the app again.** This second attempt is the one that works.

That last step is the one people miss. *Open Anyway* only grants permission -
it does not start the app.

**5.** Click **Allow** when macOS asks for the microphone.

**6.** The first launch downloads the speech model once, about 460 MB. After
that it starts in seconds.

---

# Installing on Windows

**1.** Download the zip that matches your PC from the table above.

**2.** Unzip it anywhere.

**3.** Open the folder and run **`SpeechToText.exe`**.

**4.** The first launch downloads the speech model once - about 3 GB on the GPU
build, about 460 MB on the CPU build. After that it starts in seconds.

Upgrading from an older version? Unzip over your existing folder. The model
stays where it is and is not downloaded again.

Windows builds are **digitally signed** (verified publisher: Jose Mondragon,
via Azure Trusted Signing), so you will not see a security warning.

---

# Better Spanish

**Most people can skip this.** The app already spells every Spanish word
correctly. What it misses on some computers is two pieces of Spanish
punctuation: the accent in a name like **Mondragón**, and the opening **¿** on
a question.

Whether this affects you depends on your computer, not on anything you chose:

| Your computer | Spanish accents and ¿ |
|---|---|
| Windows with an NVIDIA graphics card | **Already correct.** Nothing to do. |
| Any other Windows PC | Missing - fix below |
| Any Mac | Missing - fix below |

### The fix on Mac

Open **Modo espanol** instead of SpeechToText. That is the whole change.

macOS will block it on first open exactly as it did the main app, because it
checks each app separately. Do the **Open Anyway** steps from above once more
for this one.

### The fix on Windows

In the folder where you unzipped the app, next to `SpeechToText.exe`, there is
a file called **`Modo espanol.bat`**. Double-click **that** instead of the exe.

*(It is only in the CPU download. The GPU download does not need it.)*

### Either way

The first time, this downloads a larger speech model - about 1.4 GB - and then
starts normally every time after. Transcribing takes a few seconds instead of
one or two, in exchange for correct Spanish punctuation.

To go back to normal, just open the app the usual way. Nothing is permanently
changed, and both use the same window and settings.

**Did it work?** The small grey text in the bottom-right of the window should
say `Whisper medium` instead of `Whisper small`.

### Why is this not the default?

Because on English the two produce **byte-for-byte identical** text - we
measured it - so making it the default would make every English speaker wait
three times as long for exactly the same words.

---

# Always copy English

Normally the app copies **what you said**. Dictate in Spanish and you get
Spanish on the clipboard.

Tick **Always copy English** in the bottom bar and you get the English version
instead, whichever language you spoke. Useful when you think in Spanish but
write to people in English.

**How to use it:** tick the box. That is all. Speak, wait a moment, paste.

Things worth knowing:

- **It needs *Translate (online)* switched on**, because the English version is
  the translation. With translation off the box greys out, rather than
  pretending to work.
- **It is off by default**, so nothing changes for anyone who does not want it.
- **Dictating in English changes nothing** - what you said is already English.
- **The clipboard fills a moment later than usual**, once the translation
  arrives, instead of the instant your words appear. The status line says
  *English copied to clipboard* when it is genuinely ready.
- **If the translation fails** (offline, or a network that never replies), your
  spoken text is copied instead so the clipboard is never left stale. The
  status line says so.
- It adds **no extra network call**. It uses the translation the app already
  made for the other panel.

---

# What else changed

Everything below shipped in v2.1.7 and is included here.

**Four bugs fixed**, two of which could leave the app looking frozen:

- **A stalled translation no longer breaks recording.** On a network that
  accepts the connection but never replies - hotel and airport wifi is the
  classic case - the app used to wait forever, leaving the Record button
  disabled with no explanation until you restarted it. It now gives up after
  20 seconds and says the translation failed, keeping your transcript.
- **One internal error no longer stops the window updating.** A single failure
  used to leave the app unable to receive anything further from its background
  work, so it appeared frozen while still running.
- **Recordings now stop at 30 minutes** instead of growing until your computer
  runs out of memory. Whatever was captured is transcribed as usual.
- A rare timing fault when a global hotkey was pressed at the exact moment the
  speech model finished loading.

**A speech model that quietly broke Spanish was removed** from the options. It
was English-only, and selecting it produced English-ish nonsense from Spanish
audio instead of an error.

**Under the hood:** the code was reorganised into smaller modules and the test
suite grew from **60 to 114 tests**. No change to how the app behaves.

---

# What the app does

Dictate in **English or Spanish** with automatic language detection. Whisper
transcribes it **on your own machine** - your audio is never uploaded and never
written to a file. Both languages appear side by side, fully editable, and the
text lands on your clipboard automatically. There is a mini always-on-top mode,
and global hotkeys (`Ctrl+Alt+R`) on Windows.

Untick **Translate (online)** and the app makes **zero** network connections.
Translation is the only thing that ever leaves your computer, and it sends text
only, never audio. See [Privacy & security](README.md#privacy--security), or
the plain-English guide, [How this app works](HOW_IT_WORKS.md).

# Verifying your download

Every file's SHA-256 is listed in `checksums.txt` attached below.

```bash
shasum -a 256 ~/Downloads/SpeechToText-macOS-AppleSilicon.dmg
```

```powershell
Get-FileHash SpeechToText-Windows-CPU.zip
```
