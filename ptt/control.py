"""Key ownership and recording ownership, independent of OS and GUI libraries."""

import queue
import threading
import time


class HoldKey:
    """Consume only unmodified presses of the selected key.

    Native hooks call ``feed``; the UI consumes the small transition queue.
    No audio, GUI work, text or unrelated keystrokes enter that queue.
    A press retains its original decision until release, including repeats
    and enable/disable changes while the physical key is held.
    """

    def __init__(self, capture_release=None):
        self.events = queue.SimpleQueue()
        self.capture_release = capture_release
        self._lock = threading.Lock()
        self._enabled = False
        self._down = False
        self._claimed = False
        self._active = False
        self._token = 0

    def set_enabled(self, enabled):
        with self._lock:
            self._enabled = enabled
            if not enabled and self._active:
                self._active = False
                self.events.put(("up", self._token))

    def feed(self, pressed, modified=False):
        """Return True to suppress this selected-key event at the OS hook."""
        with self._lock:
            if pressed:
                if not self._down:
                    self._down = True
                    self._claimed = self._enabled and not modified
                    self._active = self._claimed
                    if self._claimed:
                        self._token += 1
                        self.events.put(("down", self._token))
                return self._claimed
            consumed = self._claimed
            if self._active:
                if self.capture_release is None:
                    self.events.put(("up", self._token))
                else:
                    try:
                        target = self.capture_release()
                    except Exception:
                        target = None
                    self.events.put(("up", self._token, target))
            self._down = self._claimed = self._active = False
            return consumed

    def active(self, token):
        with self._lock:
            return self._active and token == self._token


class HoldRecording:
    """Own only the recording started by this particular key press.

    All methods run on the UI thread. The app calls ``state_changed`` when
    its existing buttons, shortcuts, errors or recording limit change state.
    This prevents a late release from stopping a later manual recording.
    """

    def __init__(self, app, key, max_seconds=300, clock=time.monotonic,
                 on_release=None):
        self.app = app
        self.key = key
        self.max_seconds = max_seconds
        self.clock = clock
        self.owner = None
        self.started = None
        self.last_tick = clock()
        self.on_release = on_release

    def state_changed(self, state):
        if state != "recording":
            self.owner = None
            self.started = None

    def stop(self):
        owned = self.owner is not None
        self.owner = None
        self.started = None
        if owned and self.app.recorder.is_recording:
            self.app.toggle_recording()

    def tick(self):
        now = self.clock()
        reason = None
        if self.owner is not None:
            if now - self.last_tick > 2:
                reason = "Recording stopped after a pause in the application."
            elif now - self.started >= self.max_seconds:
                reason = "Push-to-talk time limit reached; release and press again."
            if reason:
                self.stop()
        self.last_tick = now
        while True:
            try:
                action, token, *context = self.key.events.get_nowait()
            except queue.Empty:
                break
            if action == "up":
                if self.owner == token:
                    if context and self.on_release:
                        self.on_release(context[0])
                    self.stop()
            elif (self.owner is None and self.key.active(token)
                  and self.app.model_ready and not self.app._processing
                  and not self.app.recorder.is_recording):
                self.app.toggle_recording()
                if self.app.recorder.is_recording:
                    self.owner = token
                    self.started = self.clock()
                    # A release during mic startup is already queued. Consume
                    # it next, including its destination, before stopping.
        return reason
