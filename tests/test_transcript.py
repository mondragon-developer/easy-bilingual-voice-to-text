"""Unit tests for src.transcript, with the clock driven by hand.

Pulling the numbering out of the window is what makes these possible: the
date rollover used to be reachable only by waiting until tomorrow.
"""

from datetime import datetime

from src.transcript import TranscriptLog


class FakeClock:
    """A clock the test moves itself."""

    def __init__(self, *moments):
        self._moments = list(moments)

    def __call__(self):
        return (self._moments.pop(0) if len(self._moments) > 1
                else self._moments[0])


class TestNumbering:
    def test_first_entry_is_one(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        assert log.begin_entry(panes_empty=True).startswith("#1 · ")

    def test_numbering_increments(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        log.begin_entry(panes_empty=True)
        assert log.begin_entry(panes_empty=False).startswith("#2 · ")

    def test_numbering_restarts_when_panes_are_empty(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        log.begin_entry(panes_empty=True)
        log.begin_entry(panes_empty=False)
        assert log.begin_entry(panes_empty=True).startswith("#1 · ")

    def test_reset_forgets_everything(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        log.begin_entry(panes_empty=True)
        log.reset()
        assert log.entry_no == 0 and log.stamp is None


class TestDateHeader:
    def test_date_shown_on_the_first_entry_of_a_day(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        assert log.begin_entry(panes_empty=True) == "#1 · Aug 16, 2:41 PM"

    def test_date_omitted_on_later_entries_the_same_day(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41),
                                            datetime(2026, 8, 16, 15, 5)))
        log.begin_entry(panes_empty=True)
        assert log.begin_entry(panes_empty=False) == "#2 · 3:05 PM"

    def test_date_returns_when_the_day_rolls_over(self):
        """The case that used to need a calendar to reach."""
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 23, 59),
                                            datetime(2026, 8, 17, 0, 1)))
        log.begin_entry(panes_empty=True)
        assert log.begin_entry(panes_empty=False) == "#2 · Aug 17, 12:01 AM"

    def test_midnight_hour_has_no_leading_zero(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 9, 5)))
        assert log.begin_entry(panes_empty=True) == "#1 · Aug 16, 9:05 AM"


class TestHeaderClaiming:
    def test_each_pane_gets_the_header_once(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        log.begin_entry(panes_empty=True)
        assert log.claim_header("en") == "#1 · Aug 16, 2:41 PM"
        assert log.claim_header("en") is None

    def test_both_panes_get_the_same_header(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        log.begin_entry(panes_empty=True)
        assert log.claim_header("en") == log.claim_header("es")

    def test_a_new_entry_lets_each_pane_claim_again(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41),
                                            datetime(2026, 8, 16, 15, 5)))
        log.begin_entry(panes_empty=True)
        log.claim_header("en")
        log.begin_entry(panes_empty=False)
        assert log.claim_header("en") == "#2 · 3:05 PM"

    def test_no_header_before_the_first_entry(self):
        log = TranscriptLog(clock=FakeClock(datetime(2026, 8, 16, 14, 41)))
        assert log.claim_header("en") is None
