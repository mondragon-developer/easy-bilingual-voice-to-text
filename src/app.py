"""CustomTkinter UI: record, transcribe, translate, edit, copy.

Layout
------
    [ ● Record ]  status...............  Detected: Español (98%)  [level]
    +--------------------------+---------------------------+
    | English - spoken         | Español - translation     |
    | (editable textbox)       | (editable textbox)        |
    | [Copy] [Clear]           | [Copy] [Clear]            |
    +--------------------------+---------------------------+
    [ Save transcript ]                       model / device

Every recording appends: the spoken text goes to its language's pane and the
translation to the other, so each pane always holds the full transcript in
one language. Each recording starts a new entry, set off by a blank line and
a small gray header (``#3 · 2:41 PM``); the same number and time head the
entry in both panes, so the two sides line up. Headers are display only -
every copy path strips them, so what you paste is just the words. Both panes
are plain editable text with native Ctrl+C/X/V, a right-click menu, and
Ctrl+A select-all.

Mini mode collapses the app into a small always-on-top pill (record button +
level meter) docked at the screen edge; the global hotkeys Ctrl+Alt+R
(record/stop) and Ctrl+Alt+M (mini/restore) work system-wide, so you can
dictate into any application: hotkey -> speak -> hotkey -> paste (the spoken
text is auto-copied to the clipboard when Auto-copy is on).
"""

import sys
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from . import __version__
from .dispatch import UiDispatcher
from .hotkeys import HOTKEY_MINI, HOTKEY_RECORD
from .hotkeys import create as create_hotkey_manager
from .languages import DEFAULT_LANG, LANG_NAMES, PANE_ORDER, counterpart
from .recorder import MAX_RECORDING_SECONDS, SAMPLE_RATE, AudioRecorder
from .transcriber import Transcriber
from .transcript import TranscriptLog
from .translator import translate

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

RECORD_COLOR = "#2563eb"
RECORD_HOVER = "#1d4ed8"
STOP_COLOR = "#dc2626"
STOP_HOVER = "#b91c1c"
BUSY_COLOR = "#b45309"
DONE_COLOR = "#15803d"
MINI_BG = "#111827"
TEXT_FONT = ("Segoe UI", 15)
UI_FONT = ("Segoe UI", 13)
STAMP_FONT = ("Segoe UI", 11, "bold")
STAMP_COLOR = "#6b7280"
STAMP_TAG = "stamp"          # marks entry headers, which no copy path emits


def _asset_path(name: str) -> str:
    """Absolute path to a bundled asset file.

    Works both when running from source (assets/ next to main.py) and from
    a PyInstaller build (assets/ inside the frozen bundle).

    Args:
        name: File name inside the assets directory.

    Returns:
        str: Absolute path to the asset.
    """
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return str(base / "assets" / name)


class SpeechToTextApp(ctk.CTk):
    """Main window: recording control, bilingual panes, mini mode, hotkeys.

    All heavy work (model loading, transcription, translation) runs on
    daemon worker threads; results are marshalled back to the Tk main loop
    through ``UiDispatcher`` so the UI never freezes and no thread but the
    main one ever calls into Tk.

    Collaborators are injected: see ``__init__``. What is left here is the
    window itself - widgets, wiring and the recording flow. Entry numbering
    lives in ``transcript``, thread hand-off in ``dispatch``, global hotkeys
    in ``hotkeys``, and the EN/ES pairing in ``languages``.
    """

    def __init__(self, recorder=None, transcriber=None, translator=None,
                 hotkeys=None):
        """
        Collaborators are injected with working defaults, so the app is still
        ``SpeechToTextApp()`` in ``main.py`` while a test can hand it a fake
        without reaching into another module's namespace to patch a global.

        Args:
            recorder: Object with the ``AudioRecorder`` interface.
            transcriber: Object with the ``Transcriber`` interface.
            translator: Callable ``(text, target) -> str``.
            hotkeys: Object with the ``hotkeys`` manager interface.
        """
        super().__init__()
        self.title(f"Speech to Text v{__version__} - EN / ES")
        self.geometry("1000x660")
        self.minsize(820, 520)
        self._set_window_icon()

        self.recorder = recorder if recorder is not None else AudioRecorder()
        self.transcriber = (transcriber if transcriber is not None
                            else Transcriber())
        self.translate = translator if translator is not None else translate
        self.hotkeys = (hotkeys if hotkeys is not None
                        else create_hotkey_manager())
        self.log = TranscriptLog()
        self.model_ready = False
        self._rec_start = 0.0
        self._processing = False          # a transcription is in flight
        self._state = "disabled"          # idle | recording | processing | done | disabled
        self.mini = None                  # the mini-mode pill widget, when open
        self.autocopy_var = tk.BooleanVar(value=True)
        self.translate_var = tk.BooleanVar(value=True)
        # Off by default: this changes what lands on the clipboard, so it is
        # opt-in rather than a surprise for anyone upgrading.
        self.english_clip_var = tk.BooleanVar(value=False)
        self._dispatch = UiDispatcher(self, on_error=self._on_ui_error)

        self._build_ui()
        self._bind_shortcuts()
        self.hotkeys.register(
            on_record=lambda: self._ui(self.toggle_recording),
            on_mini=lambda: self._ui(self.toggle_mini_mode))
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Start draining before any worker exists, so nothing can be queued
        # with no pump running to pick it up.
        self._dispatch.start()

        # Load the Whisper model on a worker thread so the window opens instantly.
        self._set_status("Loading Whisper model… (first run downloads it, one time)")
        threading.Thread(target=self._load_model, daemon=True).start()

    # ------------------------------------------------------------------ UI

    def _set_window_icon(self):
        """Apply the dragon logo to the title bar and taskbar (best effort)."""
        try:
            self.iconbitmap(_asset_path("icon.ico"))  # crisp on Windows
        except tk.TclError:
            pass
        try:
            # Cross-platform fallback; also inherited by Toplevel windows.
            self._icon_img = tk.PhotoImage(file=_asset_path("icon_64.png"))
            self.iconphoto(True, self._icon_img)
        except tk.TclError:
            pass

    def _build_ui(self):
        """Create all widgets: top bar, the two text panes, and bottom bar."""
        self.grid_columnconfigure((0, 1), weight=1, uniform="panes")
        self.grid_rowconfigure(1, weight=1)

        # --- top bar -----------------------------------------------------
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, columnspan=2, sticky="ew", padx=16, pady=(14, 8))
        top.grid_columnconfigure(1, weight=1)

        self.record_btn = ctk.CTkButton(
            top, text="●  Record   (Ctrl+R)", width=190, height=40,
            font=("Segoe UI", 15, "bold"),
            fg_color=RECORD_COLOR, hover_color=RECORD_HOVER,
            state="disabled", command=self.toggle_recording,
        )
        self.record_btn.grid(row=0, column=0, sticky="w")

        # Its own row: the badge, meter and Mini button all want fixed width,
        # so at the minimum window size the status was the one that gave -
        # its cell ended up under the badge and the text read "…speaking (EN".
        self.status_lbl = ctk.CTkLabel(top, text="", font=UI_FONT, anchor="w")
        self.status_lbl.grid(row=1, column=0, columnspan=5, sticky="ew",
                             pady=(8, 0))

        self.lang_badge = ctk.CTkLabel(
            top, text="Detected: -", font=UI_FONT,
            fg_color="#1f2937", corner_radius=8, padx=10, pady=4,
        )
        self.lang_badge.grid(row=0, column=2, sticky="e", padx=(0, 12))

        self.level_meter = ctk.CTkProgressBar(top, width=110)
        self.level_meter.set(0)
        self.level_meter.grid(row=0, column=3, sticky="e")

        self.mini_btn = ctk.CTkButton(top, text="🗕 Mini", width=70, height=32,
                                      font=UI_FONT, fg_color="#374151",
                                      hover_color="#4b5563",
                                      command=self.toggle_mini_mode)
        self.mini_btn.grid(row=0, column=4, sticky="e", padx=(12, 0))

        # --- text panes ----------------------------------------------------
        self.boxes, self.pane_titles = {}, {}
        for col, lang in enumerate(PANE_ORDER):
            pane = ctk.CTkFrame(self, corner_radius=12)
            pane.grid(row=1, column=col, sticky="nsew",
                      padx=(16, 8) if col == 0 else (8, 16), pady=4)
            pane.grid_columnconfigure(0, weight=1)
            pane.grid_rowconfigure(1, weight=1)

            title = ctk.CTkLabel(pane, text=LANG_NAMES[lang],
                                 font=("Segoe UI", 14, "bold"), anchor="w")
            title.grid(row=0, column=0, columnspan=2, sticky="ew",
                       padx=14, pady=(10, 4))
            self.pane_titles[lang] = title

            box = ctk.CTkTextbox(pane, wrap="word", font=TEXT_FONT,
                                 undo=True, corner_radius=8)
            box.grid(row=1, column=0, columnspan=2, sticky="nsew",
                     padx=10, pady=(0, 8))
            self._attach_editing_helpers(box)
            self._style_stamps(box)
            self.boxes[lang] = box

            copy_btn = ctk.CTkButton(pane, text="Copy", width=90, font=UI_FONT,
                                     command=lambda l=lang: self.copy_pane(l))
            copy_btn.grid(row=2, column=0, sticky="w", padx=10, pady=(0, 10))
            setattr(self, f"copy_btn_{lang}", copy_btn)

            ctk.CTkButton(pane, text="Clear", width=90, font=UI_FONT,
                          fg_color="#374151", hover_color="#4b5563",
                          command=lambda l=lang: self.boxes[l].delete("1.0", "end")
                          ).grid(row=2, column=1, sticky="e", padx=10, pady=(0, 10))

        # --- bottom bar --------------------------------------------------
        bottom = ctk.CTkFrame(self, fg_color="transparent")
        bottom.grid(row=2, column=0, columnspan=2, sticky="ew", padx=16, pady=(6, 12))

        ctk.CTkButton(bottom, text="Save transcript   (Ctrl+S)", width=200,
                      font=UI_FONT, command=self.save_transcript
                      ).grid(row=0, column=0, sticky="w")

        ctk.CTkCheckBox(bottom, text="Auto-copy spoken text", font=UI_FONT,
                        variable=self.autocopy_var, checkbox_width=20,
                        checkbox_height=20
                        ).grid(row=0, column=1, sticky="w", padx=16)

        # Translation is the app's only network call - make it a real choice.
        ctk.CTkCheckBox(bottom, text="Translate (online)", font=UI_FONT,
                        variable=self.translate_var, checkbox_width=20,
                        checkbox_height=20,
                        command=self._sync_english_clip_state
                        ).grid(row=0, column=2, sticky="w")

        # Only meaningful while Translate is on: with translation off there is
        # no English version to copy, so the box greys out rather than
        # promising something the app cannot deliver.
        self.english_clip_box = ctk.CTkCheckBox(
            bottom, text="Always copy English", font=UI_FONT,
            variable=self.english_clip_var, checkbox_width=20,
            checkbox_height=20)
        self.english_clip_box.grid(row=0, column=3, sticky="w", padx=16)
        self._sync_english_clip_state()

        bottom.grid_columnconfigure(4, weight=1)
        # Its own row: hotkey hint + model + device runs long, and a Tk label
        # does not clip to its cell - sharing row 0 let it draw over the
        # Translate checkbox once the text outgrew the window width.
        self.device_lbl = ctk.CTkLabel(bottom, text="", font=("Segoe UI", 12),
                                       text_color="#9ca3af", anchor="e")
        self.device_lbl.grid(row=1, column=0, columnspan=5, sticky="e",
                             pady=(6, 0))

    def _attach_editing_helpers(self, box):
        """Add a right-click Cut/Copy/Paste menu and Ctrl+A to a textbox.

        Args:
            box (ctk.CTkTextbox): The pane textbox to enhance.
        """
        # Events must target the tk.Text inside the CTkTextbox, not its frame.
        inner = getattr(box, "_textbox", box)
        menu = tk.Menu(self, tearoff=0)
        for label, event in (("Cut", "<<Cut>>"), ("Copy", "<<Copy>>"),
                             ("Paste", "<<Paste>>")):
            menu.add_command(label=label,
                             command=lambda e=event: inner.event_generate(e))
        menu.add_separator()
        menu.add_command(label="Select All",
                         command=lambda: self._select_all(inner))
        box.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))
        box.bind("<Control-a>", lambda e: self._select_all(inner) or "break")
        # Take over Ctrl+C/Ctrl+X (and the menu, which fires the same virtual
        # events) so a hand-made selection drops entry headers like the
        # Copy button does.
        inner.bind("<<Copy>>", lambda e: self._copy_selection(inner))
        inner.bind("<<Cut>>", lambda e: self._copy_selection(inner, cut=True))

    def _style_stamps(self, box):
        """Style the entry-header tag: small, gray, with room above it.

        The tag font has to be set on the inner tk.Text - CTkTextbox.tag_config
        rejects ``font`` because it cannot rescale it - so the display scale
        factor is applied here by hand, once, at build time.

        Args:
            box (ctk.CTkTextbox): The pane textbox to configure.
        """
        inner = getattr(box, "_textbox", box)
        scale = ctk.ScalingTracker.get_widget_scaling(self)
        family, size, weight = STAMP_FONT
        inner.tag_config(STAMP_TAG, foreground=STAMP_COLOR,
                         font=(family, int(size * scale), weight),
                         spacing1=int(8 * scale), spacing3=int(3 * scale))

    def _copy_selection(self, inner, cut=False):
        """Put the selection on the clipboard with entry headers removed.

        Args:
            inner (tkinter.Text): The pane's underlying text widget.
            cut (bool): Also delete the selection after copying it.

        Returns:
            str: ``"break"``, so Tk's own copy does not run as well.
        """
        try:
            first, last = inner.index("sel.first"), inner.index("sel.last")
        except tk.TclError:
            return "break"  # nothing selected
        text = self._strip_stamps(inner, first, last)
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)
        if cut:
            inner.delete(first, last)
        return "break"

    @staticmethod
    def _select_all(inner):
        """Select the full contents of a tk.Text widget.

        Args:
            inner (tkinter.Text): The underlying text widget of a pane.
        """
        inner.tag_add("sel", "1.0", "end-1c")
        inner.mark_set("insert", "end-1c")

    def _sync_english_clip_state(self):
        """Grey out "Always copy English" whenever translation is off.

        With translation off no English version is ever produced, so the
        setting could not be honoured. Disabling it says that, instead of
        leaving a tick box that silently does nothing.
        """
        self.english_clip_box.configure(
            state="normal" if self.translate_var.get() else "disabled")

    def _copy_to_clipboard(self, text):
        """Replace the clipboard contents.

        Args:
            text (str): Text to put on the clipboard. Empty text is ignored,
                so a failed step never wipes what the user already had.
        """
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)

    def _bind_shortcuts(self):
        """Bind in-app shortcuts (active while the window has focus)."""
        self.bind("<Control-r>", lambda e: self.toggle_recording())
        self.bind("<Control-s>", lambda e: self.save_transcript())

    # ------------------------------------------------------------ mini mode

    def toggle_mini_mode(self):
        """Collapse to the always-on-top pill, or restore the full window."""
        if self.mini is None or not self.mini.winfo_exists():
            self.mini = MiniWidget(self,
                                   on_record=self.toggle_recording,
                                   on_restore=self.toggle_mini_mode,
                                   on_exit=self._on_close)
            self.mini.set_state(self._state)
            self.withdraw()
        else:
            self.mini.destroy()
            self.mini = None
            self.deiconify()
            self.lift()
            self.focus_force()

    def _set_app_state(self, state):
        """Track the record/transcribe state and mirror it on the mini pill.

        Args:
            state (str): One of ``idle``, ``recording``, ``processing``,
                ``done``, or ``disabled``.
        """
        self._state = state
        if self.mini is not None and self.mini.winfo_exists():
            self.mini.set_state(state)

    # ------------------------------------------------------- model loading

    def _load_model(self):
        """Worker thread: load Whisper, then enable recording via the UI."""
        try:
            device = self.transcriber.load()
        except Exception as exc:  # e.g. model download interrupted
            self._ui(self._set_status, f"Model failed to load: {exc}")
            return
        # model_ready is set by _on_model_ready, on the main loop. Setting it
        # here instead left a window where a global hotkey could start a
        # recording that _on_model_ready then reset to "idle" underneath.
        self._ui(self._on_model_ready, device)

    def _on_model_ready(self, device):
        """Enable the UI once the model is loaded.

        Args:
            device (str): Device label returned by ``Transcriber.load``.
        """
        self.model_ready = True
        hint = (f"{HOTKEY_RECORD.title()}: record anywhere · "
                f"{HOTKEY_MINI.title()}: mini · "
                if self.hotkeys.available else "")
        self.device_lbl.configure(
            text=f"{hint}Whisper {self.transcriber.model_name} · {device}")
        self.record_btn.configure(state="normal")
        self._set_app_state("idle")
        if self.transcriber.gpu_error:
            self._set_status(
                "Ready - but running on CPU! GPU failed: "
                f"{self.transcriber.gpu_error[:80]}")
        else:
            self._set_status("Ready - press Record and start speaking (EN or ES).")

    # ----------------------------------------------------------- recording

    def toggle_recording(self):
        """Start recording, or stop it and kick off transcription.

        Bound to the Record button, Ctrl+R, the global Ctrl+Alt+R hotkey,
        and the mini pill's record button. Ignored while the model is still
        loading or a previous recording is being processed.
        """
        if not self.model_ready or self._processing:
            return
        if not self.recorder.is_recording:
            try:
                self.recorder.start()
            except Exception as exc:
                messagebox.showerror("Microphone error",
                                     f"Could not open the microphone:\n{exc}")
                return
            self._rec_start = time.monotonic()
            self.record_btn.configure(text="■  Stop   (Ctrl+R)",
                                      fg_color=STOP_COLOR, hover_color=STOP_HOVER)
            self._set_app_state("recording")
            self._tick_recording()
        else:
            audio = self.recorder.stop()
            self.level_meter.set(0)
            self.record_btn.configure(text="●  Record   (Ctrl+R)",
                                      fg_color=RECORD_COLOR, hover_color=RECORD_HOVER,
                                      state="disabled")
            self._processing = True
            self._set_app_state("processing")
            self._set_status("Transcribing…")
            threading.Thread(target=self._process_audio,
                             args=(audio, self.autocopy_var.get(),
                                   self.translate_var.get(),
                                   self.english_clip_var.get()),
                             daemon=True).start()

    def _tick_recording(self):
        """Update elapsed time + input level while the mic is open.

        Also stops for the user once the recorder hits its length cap, so a
        microphone left open does not quietly fill memory. The audio captured
        up to the cap is kept and transcribed as normal.
        """
        if not self.recorder.is_recording:
            return
        if self.recorder.limit_reached:
            limit_min = MAX_RECORDING_SECONDS // 60
            self.toggle_recording()  # stop and transcribe what we have
            self._set_status(
                f"Reached the {limit_min}-minute recording limit - "
                "transcribing what was captured.")
            return
        elapsed = int(time.monotonic() - self._rec_start)
        self._set_status(f"Recording…  {elapsed // 60}:{elapsed % 60:02d}")
        level = min(1.0, self.recorder.level * 6)
        self.level_meter.set(level)
        if self.mini is not None and self.mini.winfo_exists():
            self.mini.meter.set(level)
        self.after(80, self._tick_recording)

    # ------------------------------------------------- transcribe/translate

    def _process_audio(self, audio, autocopy, do_translate=True,
                       prefer_english=False):
        """Worker thread: audio -> text -> (optionally) translation.

        All UI updates are scheduled on the main loop with ``after()``.

        Args:
            audio (numpy.ndarray): 1-D float32 samples from the recorder.
            autocopy (bool): Whether to copy anything to the clipboard at all.
            do_translate (bool): Whether to call the online translator. When
                False, nothing ever leaves the machine.
            prefer_english (bool): Put the English version on the clipboard
                whichever language was spoken. Only reachable with
                ``do_translate``; ignored when English was already spoken,
                since the spoken text *is* the English. When it applies, the
                clipboard is written after the translation arrives rather than
                as soon as the words appear, and falls back to the spoken text
                if the translation fails.
        """
        if audio.size < SAMPLE_RATE * 0.3:  # under ~0.3 s of audio
            self._ui(self._finish, "Recording was too short - nothing to transcribe.")
            return
        try:
            t0 = time.perf_counter()
            text, lang, prob, duration = self.transcriber.transcribe(audio)
            elapsed = time.perf_counter() - t0
        except Exception as exc:
            self._ui(self._finish, f"Transcription failed: {exc}")
            return
        if not text:
            self._ui(self._finish, "No speech detected.")
            return

        speed = f"{duration:.0f}s of audio in {elapsed:.1f}s"
        other = counterpart(lang)

        # "Always copy English" only has anything to do when the spoken
        # language is not already English and a translation is actually
        # coming. In that one case the clipboard has to wait for the
        # translation, so the copy moves out of _show_result to below.
        wants_english = autocopy and prefer_english and do_translate
        defer_copy = wants_english and lang != DEFAULT_LANG
        copied = " · copied to clipboard" if autocopy and not defer_copy else ""

        self._ui(self._show_result, text, lang, prob,
                 autocopy and not defer_copy)

        if not do_translate:
            self._ui(self._finish,
                     f"Done - transcribed {speed}{copied}. (Translation off.)")
            return
        self._ui(self._set_status,
                 f"Transcribed {speed} - translating to {LANG_NAMES[other]}…")
        try:
            translated = self.translate(text, target=other)
        except Exception:
            # Fall back to the spoken text: a failed translation must not
            # leave the clipboard holding whatever was there before.
            if defer_copy:
                self._ui(self._copy_to_clipboard, text)
            self._ui(self._finish,
                     f"Transcribed, but translation failed - are you online? "
                     f"({LANG_NAMES[other]} pane not updated.)"
                     f"{' · spoken text copied instead' if defer_copy else copied}")
            return
        self._ui(self._append_to_pane, other, translated)
        if defer_copy:
            self._ui(self._copy_to_clipboard, translated)
            copied = " · English copied to clipboard"
        self._ui(self._finish, f"Done - transcribed {speed}{copied}.")

    def _show_result(self, text, lang, prob, autocopy=False):
        """Show a finished transcription: badge, pane titles, spoken text.

        Args:
            text (str): The transcript of the latest recording.
            lang (str): Detected language, ``"en"`` or ``"es"``.
            prob (float): Language-detection confidence (0..1).
            autocopy (bool): Copy ``text`` to the clipboard when True. The
                caller decides this: with "Always copy English" active on a
                Spanish dictation it passes False here and copies the
                translation later instead.
        """
        self._begin_entry()
        self.lang_badge.configure(
            text=f"Detected: {LANG_NAMES[lang]} ({prob:.0%})")
        self.pane_titles[lang].configure(text=f"{LANG_NAMES[lang]} - spoken")
        other = counterpart(lang)
        self.pane_titles[other].configure(text=f"{LANG_NAMES[other]} - translation")
        self._append_to_pane(lang, text)
        if autocopy:
            # Latest spoken chunk goes straight to the clipboard for pasting.
            self._copy_to_clipboard(text)

    def _begin_entry(self):
        """Open a new transcript entry: bump the counter, stamp the clock.

        Runs once per recording, before any of its text is appended, so the
        spoken pane and the translation pane share one number and one time.
        The header is only *computed* here - writing it is left to
        ``_append_to_pane``, so a pane that receives nothing for this entry
        (translation off, or it failed) is not left with a bare header.
        """
        self.log.begin_entry(panes_empty=not any(
            box.get("1.0", "end-1c").strip() for box in self.boxes.values()))

    def _append_to_pane(self, lang, text):
        """Append text to a language pane, under the current entry's header.

        Args:
            lang (str): Pane key, ``"en"`` or ``"es"``.
            text (str): Text to append.
        """
        box = self.boxes[lang]
        existing = box.get("1.0", "end-1c")
        header = self.log.claim_header(lang)
        if header:
            if existing.strip():
                # Land on exactly one blank line, whatever the pane ends with.
                trailing = len(existing) - len(existing.rstrip("\n"))
                box.insert("end", "\n" * max(0, 2 - trailing))
            # The header's newline carries the tag too, so stripping a header
            # takes its line break with it and paragraphs stay clean.
            box.insert("end", f"{header}\n", STAMP_TAG)
        elif existing and not existing.endswith((" ", "\n")):
            box.insert("end", " ")
        box.insert("end", text)
        box.see("end")

    def _pane_text(self, lang, keep_stamps=False):
        """Return a pane's contents, without the entry headers by default.

        Args:
            lang (str): Pane key, ``"en"`` or ``"es"``.
            keep_stamps (bool): Keep the ``#n · time`` headers in the result.

        Returns:
            str: The pane's text.
        """
        box = self.boxes[lang]
        if keep_stamps:
            return box.get("1.0", "end-1c")
        return self._strip_stamps(box, "1.0", "end-1c")

    @staticmethod
    def _strip_stamps(widget, start, end):
        """Text between two indices with every entry header left out.

        Args:
            widget: A tk.Text, or a CTkTextbox, which proxies the same calls.
            start (str): Index to read from.
            end (str): Index to read to.

        Returns:
            str: The text in that span, minus the header-tagged runs.
        """
        parts, cursor = [], start
        ranges = widget.tag_ranges(STAMP_TAG)  # Tk returns these in order
        for first, last in zip(ranges[::2], ranges[1::2]):
            if widget.compare(last, "<=", cursor):
                continue
            if widget.compare(first, ">=", end):
                break
            if widget.compare(first, ">", cursor):
                parts.append(widget.get(cursor, first))
            cursor = last
        if widget.compare(cursor, "<", end):
            parts.append(widget.get(cursor, end))
        return "".join(parts)

    def _finish(self, message):
        """Re-enable recording after processing and show a final status.

        Args:
            message (str): Status-bar text describing the outcome.
        """
        self._set_status(message)
        self._processing = False
        self.record_btn.configure(state="normal")
        # Flash a green check on the mini pill, then settle back to idle.
        self._set_app_state("done")
        self.after(1500, lambda: self._set_app_state("idle")
                   if self._state == "done" else None)

    # ------------------------------------------------------------- actions

    def copy_pane(self, lang):
        """Copy a pane's full text to the clipboard with button feedback.

        Args:
            lang (str): Pane key, ``"en"`` or ``"es"``.
        """
        text = self._pane_text(lang).strip()
        if not text:
            return
        self.clipboard_clear()
        self.clipboard_append(text)
        btn = getattr(self, f"copy_btn_{lang}")
        btn.configure(text="✓ Copied")
        self.after(1200, lambda: btn.configure(text="Copy"))

    def save_transcript(self):
        """Save both panes to a UTF-8 ``.txt`` chosen via a file dialog.

        Unlike the copy paths, the saved file keeps the entry headers - it is
        a record, so when each part was said is worth having.
        """
        en = self._pane_text("en", keep_stamps=True).strip()
        es = self._pane_text("es", keep_stamps=True).strip()
        if not en and not es:
            messagebox.showerror("Nothing to save", "Both panes are empty.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        parts = []
        if en:
            parts.append(f"=== English ===\n{en}")
        if es:
            parts.append(f"=== Español ===\n{es}")
        try:
            with open(path, "w", encoding="utf-8") as fh:
                fh.write("\n\n".join(parts) + "\n")
        except OSError as exc:
            messagebox.showerror("Save failed",
                                 f"Could not write the file:\n{path}\n\n{exc}")
            return
        self._set_status(f"Saved to {path}")

    # ------------------------------------------------------------- helpers

    def _set_status(self, message):
        """Update the status label in the top bar.

        Args:
            message (str): Text to display.
        """
        self.status_lbl.configure(text=message)

    def _ui(self, callback, *args):
        """Run a callback on the Tk main loop, from any thread.

        Args:
            callback: Callable to run on the main loop.
            *args: Positional arguments for the callback.
        """
        self._dispatch.post(callback, *args)

    def _on_ui_error(self, exc):
        """Surface a queued callback that blew up, instead of losing it.

        The dispatcher swallows the exception so the pump keeps running; this
        is what makes the failure visible rather than leaving the app looking
        merely stuck.

        Args:
            exc (BaseException): Whatever the callback raised.
        """
        try:
            self._set_status(f"Something went wrong: {type(exc).__name__}: {exc}")
            self._processing = False
            self.record_btn.configure(state="normal")
            self._set_app_state("idle")
        except tk.TclError:
            pass  # window is going away; nothing to report on

    def _on_close(self):
        """Clean up (mic stream, global hotkeys) and close the app."""
        if self.recorder.is_recording:
            self.recorder.stop()
        self.hotkeys.unregister()
        self.destroy()


class MiniWidget(ctk.CTkToplevel):
    """Always-on-top pill: record/stop + level meter + restore, drag to move.

    Takes the three things it can do as callbacks rather than the whole app.
    It used to hold a reference to the window and call ``app._on_close`` -
    a private method, from another class - so the pill could reach anything
    the app could.
    """

    def __init__(self, master, on_record, on_restore, on_exit):
        """
        Args:
            master: Parent window.
            on_record: Called by the pill's record/stop button.
            on_restore: Called to leave mini mode.
            on_exit: Called by the right-click *Exit app* item.
        """
        super().__init__(master)
        self.overrideredirect(True)          # no title bar
        self.attributes("-topmost", True)
        # Rounded corners: fill the window with a color Windows renders as
        # transparent so only the rounded frame is visible.
        self.configure(fg_color="#000001")
        try:
            self.wm_attributes("-transparentcolor", "#000001")
        except tk.TclError:
            pass

        body = ctk.CTkFrame(self, corner_radius=24, fg_color=MINI_BG,
                            border_width=1, border_color="#374151")
        body.pack()

        self.rec_btn = ctk.CTkButton(
            body, text="●", width=40, height=40, corner_radius=20,
            font=("Segoe UI", 16, "bold"),
            fg_color=RECORD_COLOR, hover_color=RECORD_HOVER,
            command=on_record)
        self.rec_btn.grid(row=0, column=0, padx=(9, 6), pady=8)

        self.meter = ctk.CTkProgressBar(body, width=64)
        self.meter.set(0)
        self.meter.grid(row=0, column=1, padx=2)

        ctk.CTkButton(body, text="⛶", width=32, height=32,
                      font=("Segoe UI", 14), fg_color="transparent",
                      hover_color="#374151", command=on_restore
                      ).grid(row=0, column=2, padx=(6, 9))

        # Dock near the right edge of the screen.
        self.update_idletasks()
        x = self.winfo_screenwidth() - self.winfo_reqwidth() - 16
        y = int(self.winfo_screenheight() * 0.35)
        self.geometry(f"+{x}+{y}")

        # Drag the pill anywhere; right-click for restore/exit.
        for widget in (body, self.meter):
            widget.bind("<Button-1>", self._drag_start)
            widget.bind("<B1-Motion>", self._drag_move)
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Restore window", command=on_restore)
        menu.add_separator()
        menu.add_command(label="Exit app", command=on_exit)
        body.bind("<Button-3>", lambda e: menu.tk_popup(e.x_root, e.y_root))

    def _drag_start(self, event):
        """Remember the grab offset when a drag begins."""
        self._dx = event.x_root - self.winfo_x()
        self._dy = event.y_root - self.winfo_y()

    def _drag_move(self, event):
        """Move the pill with the cursor during a drag."""
        self.geometry(f"+{event.x_root - self._dx}+{event.y_root - self._dy}")

    def set_state(self, state):
        """Restyle the pill's record button for the given app state.

        Args:
            state (str): One of ``idle``, ``recording``, ``processing``,
                ``done``, or ``disabled``.
        """
        self.rec_btn.configure(**{
            "idle":       dict(text="●", fg_color=RECORD_COLOR,
                               hover_color=RECORD_HOVER, state="normal"),
            "recording":  dict(text="■", fg_color=STOP_COLOR,
                               hover_color=STOP_HOVER, state="normal"),
            "processing": dict(text="…", fg_color=BUSY_COLOR,
                               hover_color=BUSY_COLOR, state="disabled"),
            "done":       dict(text="✓", fg_color=DONE_COLOR,
                               hover_color=DONE_COLOR, state="disabled"),
            "disabled":   dict(text="●", fg_color="#4b5563",
                               hover_color="#4b5563", state="disabled"),
        }[state])
        if state != "recording":
            self.meter.set(0)
