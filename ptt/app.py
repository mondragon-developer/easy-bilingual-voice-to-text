"""A separate app subclass adds controls; src/ and main.py remain untouched."""

import tkinter as tk

import customtkinter as ctk

from src.app import SpeechToTextApp

from .backend import KeyListener
from .control import HoldKey, HoldRecording
from .paste import create_paster


class PushToTalkApp(SpeechToTextApp):
    def __init__(self, key_name="F9", max_seconds=300, listener_factory=KeyListener,
                 paste_english=False, paster=None,
                 **kwargs):
        self.ptt_recording = None
        self.ptt_listener = None
        self._ptt_timer = None
        self._ptt_closed = False
        self._paste_pending = False
        self._paste_target = None
        self._paste_text = ""
        self.paster = paster if paster is not None else create_paster()
        super().__init__(**kwargs)
        self.title("Speech to Text v2.4.2-ptt.2 - EN / ES")
        self.ptt_key = HoldKey(capture_release=self.paster.capture)
        self.ptt_recording = HoldRecording(
            self, self.ptt_key, max_seconds, on_release=self._prepare_paste)
        self.ptt_enabled = tk.BooleanVar(value=True)
        self.paste_english = tk.BooleanVar(value=paste_english)
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=3, column=0, columnspan=2, sticky="ew", padx=16, pady=(0, 12))
        self.ptt_switch = ctk.CTkCheckBox(
            bar, text=f"Hold {key_name} to talk", variable=self.ptt_enabled,
            command=self._ptt_toggle, state="disabled")
        self.ptt_switch.grid(row=0, column=0, sticky="w")
        self.paste_switch = ctk.CTkCheckBox(
            bar, text="Paste English after release", variable=self.paste_english,
            command=self._paste_toggle)
        self.paste_switch.grid(row=0, column=1, sticky="w", padx=(24, 0))
        self.ptt_status = ctk.CTkLabel(bar, text="Starting keyboard listener…", anchor="w")
        self.ptt_status.grid(row=1, column=0, sticky="w")
        self.ptt_status.grid_configure(columnspan=2)
        try:
            self.ptt_listener = listener_factory(self.ptt_key, key_name)
            self.ptt_listener.start()
        except Exception as exc:
            self._ptt_fail(f"Push-to-talk unavailable: {exc}")
        else:
            self._ptt_poll()

    def _paste_toggle(self):
        if not self.paste_english.get():
            self._paste_pending = False
            self._paste_target = None

    def _prepare_paste(self, target):
        self._paste_pending = self.paste_english.get()
        self._paste_target = target
        self._paste_text = ""

    def _show_result(self, text, lang, prob, autocopy=False):
        if self._paste_pending and lang == "en":
            self._paste_text = text
        super()._show_result(text, lang, prob, autocopy)

    def _append_to_pane(self, lang, text):
        if self._paste_pending and lang == "en":
            self._paste_text = text
        super()._append_to_pane(lang, text)

    def _finish(self, message):
        pending, target, text = self._paste_pending, self._paste_target, self._paste_text
        self._paste_pending = False
        self._paste_target = None
        self._paste_text = ""
        if pending:
            if not text.strip():
                message += " English was not available; nothing pasted."
            else:
                try:
                    self._copy_to_clipboard(text)
                    self.paster.paste(target)
                except Exception as exc:
                    message += f" {exc}"
                else:
                    message += " English paste shortcut sent."
        super()._finish(message)

    def _ptt_toggle(self):
        enabled = self.ptt_enabled.get()
        self.ptt_key.set_enabled(enabled)
        if not enabled:
            self._paste_pending = False
            self.ptt_recording.stop()
        self.ptt_status.configure(text=(
            "Hold to record; release to process. This key is reserved while enabled."
            if enabled else "Push-to-talk off. The key works normally."))

    def _ptt_fail(self, message):
        self._paste_pending = False
        self.ptt_enabled.set(False)
        self.ptt_key.set_enabled(False)
        if self.ptt_recording:
            self.ptt_recording.stop()
        if self.ptt_listener:
            self.ptt_listener.stop()
        self.ptt_switch.configure(state="disabled")
        self.ptt_status.configure(text=message, wraplength=760)

    def _ptt_poll(self):
        if self._ptt_closed:
            return
        try:
            ready, error = self.ptt_listener.health()
            if error:
                self._ptt_fail(error)
                return
            if ready:
                if self.ptt_switch.cget("state") == "disabled":
                    self.ptt_switch.configure(state="normal")
                    self._ptt_toggle()
                reason = self.ptt_recording.tick()
                if reason:
                    self.ptt_status.configure(text=reason)
        except Exception as exc:
            self._ptt_fail(f"Push-to-talk stopped: {exc}")
            return
        self._ptt_timer = self.after(25, self._ptt_poll)

    def _set_app_state(self, state):
        if state == "recording":
            self._paste_pending = False
            self._paste_target = None
            self._paste_text = ""
        super()._set_app_state(state)
        if self.ptt_recording:
            self.ptt_recording.state_changed(state)

    def destroy(self):
        # Called both by the original close handler (including mini mode)
        # and direct destruction. Never leave a global hook alive afterwards.
        self._ptt_closed = True
        self._paste_pending = False
        self._paste_target = None
        if self._ptt_timer is not None:
            self.after_cancel(self._ptt_timer)
            self._ptt_timer = None
        if self.ptt_listener:
            self.ptt_listener.stop()
        if self.ptt_recording:
            self.ptt_recording.owner = None
        super().destroy()
