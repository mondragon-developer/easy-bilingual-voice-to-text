"""Optional launcher: python push_to_talk.py [--key F9|F13]."""

import argparse
import multiprocessing
import sys


def options(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--key", type=str.upper, choices=("F9", "F13"), default="F9")
    parser.add_argument("--max-seconds", type=int, default=300,
                        help="Safety limit per hold, 1–1800 seconds (default: 300).")
    args = parser.parse_args(argv)
    if not 1 <= args.max_seconds <= 1800:
        parser.error("--max-seconds must be between 1 and 1800")
    return args


def main(argv=None):
    args = options(argv)
    if sys.platform == "win32":
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "mondragon.speechtotext.ptt")
    from ptt.app import PushToTalkApp
    PushToTalkApp(key_name=args.key, max_seconds=args.max_seconds).mainloop()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
