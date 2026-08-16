"""Getting work from background threads onto the Tk main loop, safely.

Tkinter is not thread safe. Calling ``after()`` straight from a worker races
the main thread inside the Tcl interpreter and can segfault the process - most
visibly when the model-load thread finishes while the main loop is mid-redraw.
So workers only append to a queue, and the drain (which always runs on the
main loop) is the single place that touches Tk.
"""

import queue
import threading
import tkinter as tk

#: How often the main loop picks up work queued by the worker threads. Short
#: enough to read as instant, long enough not to busy-poll an idle app.
UI_POLL_MS = 16


class UiDispatcher:
    """Marshals callbacks from any thread onto the Tk main loop."""

    def __init__(self, widget, poll_ms: int = UI_POLL_MS, on_error=None):
        """
        Args:
            widget: Any Tk widget; used for its ``after`` and as the owner of
                the Tcl interpreter.
            poll_ms: Milliseconds between drains.
            on_error: Optional callable taking the exception raised by a
                queued callback. Errors are always swallowed so the pump
                survives them; this is the hook for reporting them.
        """
        self._widget = widget
        self._poll_ms = poll_ms
        self._on_error = on_error
        self._queue = queue.Queue()
        # Whichever thread built the window owns the Tcl interpreter; only it
        # may call into Tk. Recorded rather than assumed to be the main thread.
        self._ui_thread = threading.current_thread()

    def start(self):
        """Begin draining. Call before any worker can post."""
        self._drain()

    def post(self, callback, *args):
        """Hand a callback to the Tk main loop from any thread.

        Callers already on the Tk thread skip the queue: ``after()`` is only
        unsafe from *another* thread, and going straight through keeps the
        original scheduling for the code paths that never had a problem.

        Safe to call after the window has been closed: the callback is queued
        and simply never drained, which lets workers finish cleanly.

        Args:
            callback: Callable to run on the main loop.
            *args: Positional arguments for the callback.
        """
        if threading.current_thread() is self._ui_thread:
            try:
                self._widget.after(0, callback, *args)
            except (RuntimeError, tk.TclError):
                pass  # window already destroyed - nothing to update
            return
        self._queue.put((callback, args))

    def _drain(self):
        """Run whatever the workers have queued, then reschedule.

        Every callback is isolated. A queued callback that raises used to take
        the pump down with it: the exception escaped before the reschedule at
        the end, so nothing was ever drained again and the app went silently
        deaf to its own workers - no status updates, and the record button
        stuck disabled forever. The reschedule now runs in a ``finally``, and
        one bad callback costs only itself.
        """
        try:
            while True:
                try:
                    callback, args = self._queue.get_nowait()
                except queue.Empty:
                    break
                try:
                    callback(*args)
                except tk.TclError:
                    pass  # widget went away mid-update - nothing to draw on
                except Exception as exc:  # noqa: BLE001 - the pump must survive
                    if self._on_error is not None:
                        try:
                            self._on_error(exc)
                        except Exception:
                            pass
        finally:
            try:
                self._widget.after(self._poll_ms, self._drain)
            except (RuntimeError, tk.TclError):
                pass  # window destroyed - stop pumping
