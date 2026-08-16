"""Unit tests for src.dispatch, using a fake widget instead of a window.

The dispatcher only needs ``after``, so these run without a display.
"""

import threading

import pytest

from src.dispatch import UiDispatcher


class FakeWidget:
    """Stands in for a Tk widget, recording what would be scheduled.

    ``after(0, ...)`` runs immediately, matching the same-thread fast path;
    the periodic reschedule is only recorded, so a drain does not recurse.
    """

    def __init__(self):
        self.scheduled = []
        self.immediate = []

    def after(self, delay, callback, *args):
        if delay == 0:
            self.immediate.append((callback, args))
            callback(*args)
        else:
            self.scheduled.append((delay, callback))


def _drain(dispatcher):
    """Run one drain cycle the way the main loop would."""
    dispatcher._drain()


class TestPosting:
    def test_same_thread_post_runs_immediately(self):
        widget = FakeWidget()
        got = []
        UiDispatcher(widget).post(got.append, "hello")
        assert got == ["hello"]

    def test_worker_thread_post_is_queued_until_drained(self):
        widget = FakeWidget()
        dispatcher = UiDispatcher(widget)
        got = []
        worker = threading.Thread(target=dispatcher.post, args=(got.append, "x"))
        worker.start()
        worker.join()
        assert got == [], "must not run on the worker thread"
        _drain(dispatcher)
        assert got == ["x"]

    def test_queued_callbacks_run_in_order(self):
        widget = FakeWidget()
        dispatcher = UiDispatcher(widget)
        got = []
        for item in ("a", "b", "c"):
            threading.Thread(target=dispatcher.post,
                             args=(got.append, item)).start()
            # join each so ordering is the queue's, not the scheduler's
            for thread in threading.enumerate():
                if thread is not threading.current_thread() and thread.is_alive():
                    thread.join(timeout=1)
        _drain(dispatcher)
        assert got == ["a", "b", "c"]


class TestPumpSurvival:
    """A raising callback used to kill the pump for the rest of the session."""

    def _post_from_worker(self, dispatcher, callback, *args):
        worker = threading.Thread(target=dispatcher.post,
                                  args=(callback, *args))
        worker.start()
        worker.join()

    def test_a_raising_callback_does_not_stop_the_reschedule(self):
        widget = FakeWidget()
        dispatcher = UiDispatcher(widget)
        self._post_from_worker(dispatcher, lambda: 1 / 0)
        _drain(dispatcher)
        assert widget.scheduled, "pump must reschedule itself after a failure"

    def test_later_callbacks_still_run_after_one_raises(self):
        widget = FakeWidget()
        dispatcher = UiDispatcher(widget)
        got = []
        self._post_from_worker(dispatcher, lambda: 1 / 0)
        self._post_from_worker(dispatcher, got.append, "survived")
        _drain(dispatcher)
        assert got == ["survived"]

    def test_the_error_is_reported_not_swallowed_silently(self):
        widget = FakeWidget()
        seen = []
        dispatcher = UiDispatcher(widget, on_error=seen.append)
        self._post_from_worker(dispatcher, lambda: 1 / 0)
        _drain(dispatcher)
        assert len(seen) == 1
        assert isinstance(seen[0], ZeroDivisionError)

    def test_a_raising_error_handler_cannot_stop_the_pump(self):
        widget = FakeWidget()

        def bad_handler(_exc):
            raise RuntimeError("handler is broken too")

        dispatcher = UiDispatcher(widget, on_error=bad_handler)
        self._post_from_worker(dispatcher, lambda: 1 / 0)
        _drain(dispatcher)
        assert widget.scheduled


class TestShutdown:
    def test_post_after_teardown_does_not_raise(self):
        class DeadWidget:
            def after(self, *_args):
                raise RuntimeError("main thread is not in main loop")

        dispatcher = UiDispatcher(DeadWidget())
        dispatcher.post(lambda: None)  # must not propagate

    def test_drain_stops_quietly_once_the_widget_is_gone(self):
        class DeadWidget:
            def after(self, *_args):
                raise RuntimeError("application has been destroyed")

        dispatcher = UiDispatcher(DeadWidget())
        _drain(dispatcher)  # must not propagate


@pytest.mark.parametrize("poll_ms", [1, 16, 100])
def test_reschedule_uses_the_configured_interval(poll_ms):
    widget = FakeWidget()
    dispatcher = UiDispatcher(widget, poll_ms=poll_ms)
    _drain(dispatcher)
    assert widget.scheduled[0][0] == poll_ms
