"""Frozen optional edition, with build checks and the normal PTT launcher."""

import multiprocessing
import sys


if __name__ == "__main__":
    multiprocessing.freeze_support()
    if "--selftest" in sys.argv:
        from main import selftest
        sys.exit(selftest())
    if "--ptt-selftest" in sys.argv:
        from ptt.selftest import run
        sys.exit(run())
    from push_to_talk import main
    main()
