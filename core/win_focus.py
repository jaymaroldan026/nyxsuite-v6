"""Reliable window foregrounding on Windows.

Windows refuses ``SetForegroundWindow`` from a process that does not already
own the foreground (the "foreground lock"). AdsPower automation must bring the
AdsPower window to the front before any click/type, otherwise input lands on
whatever window is on top. This module defeats the lock with the documented
combination that actually works in practice:

  1. Zero the foreground-lock timeout (SPI_SETFOREGROUNDLOCKTIMEOUT).
  2. Synthesise an ALT keypress (unlocks SetForegroundWindow for this call).
  3. AttachThreadInput to the current foreground thread while we promote.
  4. ShowWindow(RESTORE) + BringWindowToTop + SetForegroundWindow.

Everything is best-effort and degrades gracefully on non-Windows platforms so
the rest of the codebase can import it unconditionally.
"""
from __future__ import annotations

import ctypes
import time
from typing import Optional

try:
    import win32con
    import win32gui
    _WIN32 = True
except Exception:  # pragma: no cover - non-Windows / missing pywin32
    _WIN32 = False


SW_MINIMIZE = 6
SW_RESTORE = 9
SPI_SETFOREGROUNDLOCKTIMEOUT = 0x2001
SPIF_SENDCHANGE = 0x2
VK_MENU = 0x12          # ALT
KEYEVENTF_KEYUP = 0x0002


def _disable_foreground_lock():
    try:
        ctypes.windll.user32.SystemParametersInfoW(
            SPI_SETFOREGROUNDLOCKTIMEOUT, 0, 0, SPIF_SENDCHANGE
        )
    except Exception:
        pass


def _tap_alt():
    """Synthesise ALT down/up so the OS lets us call SetForegroundWindow."""
    try:
        ctypes.windll.user32.keybd_event(VK_MENU, 0, 0, 0)
        ctypes.windll.user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    except Exception:
        pass


def force_foreground(hwnd: int) -> bool:
    """Bring ``hwnd`` to the foreground. Returns True if it ended up foreground."""
    if not _WIN32 or not hwnd:
        return False

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32

    # Fast path: already foreground -> skip the (slow) ALT-tap + AttachThreadInput
    # dance. This is called before every UIA interaction, so it must be cheap when
    # the window is already in front.
    if user32.GetForegroundWindow() == hwnd:
        return True

    _disable_foreground_lock()
    _tap_alt()

    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None) if fg else 0
    our_thread = kernel32.GetCurrentThreadId()

    attached = False
    if fg_thread and fg_thread != our_thread:
        attached = bool(user32.AttachThreadInput(our_thread, fg_thread, True))
    try:
        try:
            if win32gui.IsIconic(hwnd):      # only restore if minimized
                win32gui.ShowWindow(hwnd, SW_RESTORE)  # preserves maximized state
        except Exception:
            pass
        try:
            win32gui.BringWindowToTop(hwnd)
        except Exception:
            pass
        for _ in range(3):
            try:
                win32gui.SetForegroundWindow(hwnd)
            except Exception:
                pass
            if user32.GetForegroundWindow() == hwnd:
                break
            _tap_alt()
            time.sleep(0.05)
    finally:
        if attached:
            user32.AttachThreadInput(our_thread, fg_thread, False)

    return user32.GetForegroundWindow() == hwnd


def find_window(title_substring: str) -> Optional[int]:
    """Return the hwnd of the first top-level window whose title contains
    ``title_substring`` (case-insensitive), or None."""
    if not _WIN32:
        return None
    needle = title_substring.lower()
    found = []

    def _cb(hwnd, _):
        try:
            if not win32gui.IsWindowVisible(hwnd):
                return True
            title = win32gui.GetWindowText(hwnd) or ""
            if needle in title.lower():
                found.append(hwnd)
        except Exception:
            pass
        return True

    try:
        win32gui.EnumWindows(_cb, None)
    except Exception:
        return None
    return found[0] if found else None


def minimize_window(hwnd: int) -> bool:
    """Minimize (collapse to taskbar) the given window. Returns True on success."""
    if not _WIN32 or not hwnd:
        return False
    try:
        win32gui.ShowWindow(hwnd, SW_MINIMIZE)
        return True
    except Exception:
        return False


def ensure_foreground(title_substring: str, retries: int = 3, settle: float = 0.4) -> Optional[int]:
    """Find a window by title substring and force it foreground. Returns hwnd or None."""
    hwnd = find_window(title_substring)
    if not hwnd:
        return None
    # Already foreground -> no focus change, no settle needed (fast common case).
    if _WIN32 and ctypes.windll.user32.GetForegroundWindow() == hwnd:
        return hwnd
    for _ in range(max(1, retries)):
        if force_foreground(hwnd):
            time.sleep(settle)
            return hwnd
        time.sleep(0.2)
    time.sleep(settle)
    return hwnd  # return anyway; caller may still proceed
