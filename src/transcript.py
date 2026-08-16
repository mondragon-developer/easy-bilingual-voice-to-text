"""Entry numbering and the ``#3 · 2:41 PM`` headers above each recording.

Pure bookkeeping, deliberately free of Tk: the log decides *what* a header
says and *whether* a pane still needs one, and the window decides where to
draw it. That split is what lets the numbering rules be tested without
opening a window, including the date rollover, which is otherwise only
reachable by waiting until tomorrow.
"""

from datetime import datetime


class TranscriptLog:
    """Numbers the recordings and stamps each one with a time.

    One entry per recording. Both panes share that entry's number and time,
    so the two sides line up, and each pane is stamped at most once per entry.

    Attributes:
        entry_no (int): Number of the entry currently being written.
        stamp (str | None): Header text for the current entry, or None before
            the first ``begin_entry``.
    """

    def __init__(self, clock=datetime.now):
        """
        Args:
            clock: Callable returning the current ``datetime``. Injected so
                tests can drive the date rollover rather than wait for it.
        """
        self._clock = clock
        self.entry_no = 0
        self.stamp = None
        self._stamp_day = None
        self._stamped = set()

    def begin_entry(self, panes_empty: bool) -> str:
        """Open a new entry and return its header text.

        Numbering restarts at #1 whenever both panes are empty, and the date
        appears only on the first entry of a day, so it stays out of the way
        during a long session.

        Args:
            panes_empty: True when no pane currently holds any text.

        Returns:
            str: The header for this entry, e.g. ``"#3 · 2:41 PM"``.
        """
        if panes_empty:
            self.entry_no = 0
            self._stamp_day = None
        self.entry_no += 1
        now = self._clock()
        clock = now.strftime("%I:%M %p").lstrip("0")  # %-I/%#I are not portable
        if now.date() == self._stamp_day:
            self.stamp = f"#{self.entry_no} · {clock}"
        else:
            self.stamp = f"#{self.entry_no} · {now:%b} {now.day}, {clock}"
            self._stamp_day = now.date()
        self._stamped = set()
        return self.stamp

    def claim_header(self, pane: str):
        """Take this entry's header for a pane, once.

        The header is handed out only when a pane actually receives text, so
        a pane that gets nothing for this entry (translation off, or it
        failed) is never left with a bare header above no words.

        Args:
            pane: Pane key, e.g. ``"en"``.

        Returns:
            str | None: The header on the first call for this pane in this
            entry, None afterwards.
        """
        if not self.stamp or pane in self._stamped:
            return None
        self._stamped.add(pane)
        return self.stamp

    def reset(self):
        """Forget all numbering, as if the app had just started."""
        self.entry_no = 0
        self.stamp = None
        self._stamp_day = None
        self._stamped = set()
