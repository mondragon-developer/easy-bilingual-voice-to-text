"""Put text on this PC's clipboard from the server.

A browser writes the clipboard only while its page has the focus, and
dictating at the PC usually means clicking Stop and going straight to the
window to paste in, before the transcription is back. The copy then fails
and the clipboard keeps the previous dictation. The server runs in the same
desktop session and has no such rule, so for a page opened on the PC itself
the server does the copy.
"""

import ctypes
import shutil
import subprocess
import sys
import time

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002


def copy(text: str) -> bool:
    """Replace the clipboard contents with ``text``; whether it worked."""
    if sys.platform == "win32":
        return _copy_windows(text)
    if sys.platform == "darwin" and shutil.which("pbcopy"):
        done = subprocess.run(["pbcopy"], input=text.encode("utf-8"),
                              check=False)
        return done.returncode == 0
    return False


def _copy_windows(text):
    from ctypes import wintypes

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    # Without explicit types ctypes assumes int, and a 64-bit handle comes
    # back cut in half.
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.OpenClipboard.restype = wintypes.BOOL
    user32.EmptyClipboard.restype = wintypes.BOOL
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.CloseClipboard.restype = wintypes.BOOL
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalUnlock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.argtypes = [wintypes.HANDLE]

    data = text.encode("utf-16-le") + b"\x00\x00"
    # Another program can hold the clipboard open for a moment.
    for _ in range(20):
        if user32.OpenClipboard(None):
            break
        time.sleep(0.05)
    else:
        return False
    try:
        user32.EmptyClipboard()
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            return False
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            return False
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.SetClipboardData(CF_UNICODETEXT, handle):
            kernel32.GlobalFree(handle)
            return False
        # The clipboard owns the memory from here; freeing it would be a
        # use-after-free in whichever program pastes.
        return True
    finally:
        user32.CloseClipboard()
