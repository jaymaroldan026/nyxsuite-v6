"""AdsPower GUI automation (no Local API required).

The AdsPower Local API is permission-gated on this account (``/browser/start``
returns ``9110 No local API permission``), so profile *creation* and *starting*
cannot go through the API. This module drives the AdsPower desktop app directly.

Design — robust across resolution / DPI / window position
---------------------------------------------------------
* **Primary locator: Windows UI Automation (pywinauto/uia).** Every control is
  found by name and clicked at the centre of its *real* on-screen rectangle, so
  the flow is resolution- and DPI-independent (no hard-coded coordinates).
* **Foreground guarantee:** Windows blocks ``SetForegroundWindow`` from a
  background process, and Chromium only builds the form's accessibility tree
  once the window is focused. ``core.win_focus`` defeats the foreground lock
  before every interaction.
* **Clipboard paste** for text entry — matches AdsPower's proxy auto-parse
  (pasting ``host:port:user:pass`` into the Host field fills all four fields)
  and avoids per-keystroke flakiness.
* **Vision fallback:** ``core.ui_vision`` (opencv multi-scale template match) is
  the cross-platform safety net for the rare case UIA cannot see a control.

Public API
----------
    ctrl = AdsPowerUIController()
    info = ctrl.create_profile(name="Snapchat: Pending",
                               proxy="48.45.190.63:42438:hwwrghLD:j432NPbg",
                               group="Snapchat20")
    endpoint = ctrl.open_profile_by_id(info["profile_id"])   # ws:// for Playwright
"""
from __future__ import annotations

import functools
import re
import threading
import time
from dataclasses import dataclass
from typing import Optional

from core.logger import logger

# Every GUI action drives the one real mouse/keyboard, so all profile operations
# (create / open / rename / delete / close) must run one at a time. This must hold
# not just across threads but across *processes*: Nyx (main.py) and Nyxify
# (nyxify_runner.py) run as separate processes and can be active at the same time,
# so an in-process lock alone would let them fight over the mouse.
_GUI_RLOCK = threading.RLock()


class _GuiLock:
    """Serialise AdsPower GUI automation across threads AND across the separate
    Nyx and Nyxify runner processes. The cross-process part is a Windows named
    mutex (released automatically — WAIT_ABANDONED — if a holder crashes); on
    non-Windows it degrades to the in-process lock, which is fine because the GUI
    automation (pywinauto/win32) is Windows-only anyway. The Playwright work that
    follows an open still runs in parallel — only the GUI touchpoints serialise."""

    # Session-local namespace (no "Global\\"): both runners run as the same user
    # in the same session, so they share it without needing elevation.
    _MUTEX_NAME = "NyxSuite.AdsPowerGui.Lock"

    def __init__(self):
        self._mutex = None
        self._win32event = None
        try:
            import win32event
            self._win32event = win32event
            self._mutex = win32event.CreateMutex(None, False, self._MUTEX_NAME)
        except Exception:
            self._mutex = None

    def __enter__(self):
        _GUI_RLOCK.acquire()                       # intra-process (reentrant) first
        if self._mutex is not None:
            try:
                self._win32event.WaitForSingleObject(self._mutex, self._win32event.INFINITE)
            except Exception:
                pass
        return self

    def __exit__(self, *exc):
        if self._mutex is not None:
            try:
                self._win32event.ReleaseMutex(self._mutex)
            except Exception:
                pass
        _GUI_RLOCK.release()
        return False


_GUI_LOCK = _GuiLock()


def _serialized(fn):
    """Run a controller method under the global (cross-process) GUI lock."""
    @functools.wraps(fn)
    def wrapper(self, *args, **kwargs):
        with _GUI_LOCK:
            return fn(self, *args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# GUI batcher — coalesce concurrent opens/closes into ONE bulk search
# ---------------------------------------------------------------------------
class _BatchResult:
    """Per-id result slot the batch leader signals once it has done the row
    action (or failed) for that id. ``value`` carries an action return (e.g. the
    bool a close produces); opens leave it ``None``."""
    __slots__ = ("event", "ok", "error", "value")

    def __init__(self):
        self.event = threading.Event()
        self.ok = False
        self.error = None
        self.value = None


class _GuiBatcher:
    """Coalesce concurrent profile row-actions (within one process) into a single
    bulk ``Profile ID is <id1> <id2> ...`` search — used for both **open** and
    **close** so whenever more than one profile needs opening/closing at once it
    is one search instead of one per profile.

    The win: each open/close used to run its own full search under the global GUI
    lock (Reset -> paste -> dropdown-match -> list-settle, several seconds). When
    the runner opens/closes many profiles at once they queued behind that lock
    and each one paid for its own search. Here, whichever caller holds the GUI
    lock drains every other waiting caller and searches them ALL in one query,
    then does each row's action. Coalescing is driven by lock contention (no
    fixed timer), so a lone action still runs immediately as a one-id 'batch'.

    Per-process only: Nyx and Nyxify run as separate processes and serialise via
    the named mutex, so a cross-process pair won't share a search — but the
    parallel work that matters happens inside one runner (``max_parallel``)."""

    _GRACE = 0.3        # after taking the GUI lock, let a few stragglers register
    _MAX_BATCH = 12     # one page of AdsPower results

    def __init__(self, action: str, verb: str):
        self._action = action            # controller method name, e.g. "_bulk_open_locked"
        self._verb = verb                # human word for logs, e.g. "open" / "close"
        self._lock = threading.Lock()    # guards _pending (short holds only)
        self._pending = {}               # profile_id -> _BatchResult

    def submit(self, controller, profile_id: str):
        """Register ``profile_id`` and block until its row action has run (or
        failed). Returns the action's value (e.g. close's bool); raises
        ``AdsPowerUIError`` on failure."""
        with self._lock:
            res = self._pending.get(profile_id)
            if res is None or res.event.is_set():
                res = _BatchResult()
                self._pending[profile_id] = res
        self._drive(controller, profile_id)
        res.event.wait()
        if not res.ok:
            raise res.error or AdsPowerUIError(
                f"Could not {self._verb} profile {profile_id}.")
        return res.value

    def _drive(self, controller, my_id: str):
        """Become the batch leader under the GUI lock and process all pending ids
        in one search. If our id was already handled by a previous leader while we
        waited for the lock, return immediately (our event is/becomes set)."""
        with _GUI_LOCK:
            with self._lock:
                if my_id not in self._pending:
                    return                       # already handled by a prior leader
            time.sleep(self._GRACE)              # OUTSIDE _lock so stragglers can join
            with self._lock:
                batch = list(self._pending.items())[: self._MAX_BATCH]
                for pid, _res in batch:
                    self._pending.pop(pid, None)
            ids = [pid for pid, _res in batch]
            results = {pid: res for pid, res in batch}
            try:
                getattr(controller, self._action)(ids, results)
            except Exception as exc:             # whole-batch failure (e.g. no search bar)
                logger.warning(f"Bulk {self._verb} batch failed: {exc}")
            finally:
                for _pid, res in batch:          # never leave a caller blocked
                    if not res.event.is_set():
                        res.ok = False
                        res.error = res.error or AdsPowerUIError(
                            f"Bulk {self._verb} did not complete for {_pid}.")
                        res.event.set()


_OPEN_BATCHER = _GuiBatcher("_bulk_open_locked", "open")
_CLOSE_BATCHER = _GuiBatcher("_bulk_close_locked", "close")


try:
    from pywinauto import Application
    _PYWINAUTO = True
except Exception:  # pragma: no cover
    _PYWINAUTO = False

from core import win_focus
from core import ui_vision

try:
    import win32gui as _WG
    import win32con as _WC
except Exception:
    _WG = _WC = None

# AdsPower main-window title looks like "AdsPower Browser | 8.4.3 | 2.8.6.9".
_WINDOW_TITLE_SUBSTR = "AdsPower Browser |"

# A profile serial/ID in the No./ID column is an 8-ish char alphanumeric with at
# least one letter (e.g. "k1e0lch1"); the No. above it is digits-only.
_PROFILE_ID_RE = re.compile(r"^(?=.*[a-z])[a-z0-9]{7,9}$")

# Failure words that appear in AdsPower's proxy-check result toast/text.
_PROXY_FAIL_WORDS = ("failed", "timed out", "timeout", "unavailable", "unable",
                     "cannot", "error", "invalid", "not available")


class AdsPowerWindowNotFoundError(RuntimeError):
    """AdsPower desktop app is not running / window not found."""


class AdsPowerUIError(RuntimeError):
    """Generic AdsPower GUI-automation failure."""


@dataclass
class AdsPowerUIConfig:
    group_name: str = "Snapchat20"
    proxy_check_timeout: float = 12.0
    require_proxy_ok: bool = False     # if True, abort create when proxy check fails
    new_profile_wait: float = 2.0
    form_settle: float = 0.6
    create_id_timeout: float = 25.0
    open_cdp_timeout: float = 25.0
    capture_templates: bool = True     # auto-snapshot UIA-found controls for the vision fallback


def _pg():
    import pyautogui
    pyautogui.FAILSAFE = False
    # No implicit per-call pause — every place that needs the UI to react places
    # its own explicit (and now much shorter) wait, so this just added latency.
    pyautogui.PAUSE = 0.0
    return pyautogui


def _set_clipboard(text: str):
    try:
        import win32clipboard
        win32clipboard.OpenClipboard()
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardText(str(text), win32clipboard.CF_UNICODETEXT)
        win32clipboard.CloseClipboard()
        return
    except Exception:
        pass
    try:
        import pyperclip
        pyperclip.copy(str(text))
    except Exception as exc:
        logger.debug(f"clipboard set failed: {exc}")


class AdsPowerUIController:
    def __init__(self, config: Optional[AdsPowerUIConfig] = None):
        if not _PYWINAUTO:
            raise ImportError("pywinauto is required for AdsPower UI automation "
                              "(pip install pywinauto).")
        self.config = config or AdsPowerUIConfig()
        self._app = None
        self._win = None
        self._hwnd = None

    # ------------------------------------------------------------------
    # Window / connection
    # ------------------------------------------------------------------

    def _connect(self):
        """Foreground AdsPower and return its top window (reconnect if stale)."""
        hwnd = win_focus.ensure_foreground(_WINDOW_TITLE_SUBSTR)
        if not hwnd:
            raise AdsPowerWindowNotFoundError(
                "AdsPower desktop app not found. Launch AdsPower and sign in.")
        if hwnd != self._hwnd or self._app is None:
            self._app = Application(backend="uia").connect(handle=hwnd, timeout=10)
            self._hwnd = hwnd
        self._win = self._app.window(handle=hwnd)
        return self._win

    @staticmethod
    def _minimize_overlapping_browsers(main_hwnd):
        """Minimize any visible windows that might overlap the AdsPower main
        window — owned windows (profile browser panels) and other top-level
        windows whose title suggests an open Snapchat profile."""
        if _WG is None or not main_hwnd or not _WG.IsWindow(main_hwnd):
            return
        try:
            def _enum_cb(eh, _):
                if eh == main_hwnd or not _WG.IsWindowVisible(eh):
                    return True
                try:
                    if _WG.GetWindow(eh, _WC.GW_OWNER) == main_hwnd:
                        _WG.ShowWindow(eh, win_focus.SW_MINIMIZE)
                        return True
                    title = (_WG.GetWindowText(eh) or "").lower()
                    if "snapchat" in title or "bitmoji" in title:
                        _WG.ShowWindow(eh, win_focus.SW_MINIMIZE)
                except Exception:
                    pass
                return True
            _WG.EnumWindows(_enum_cb, None)
        except Exception:
            pass

    def _foreground(self):
        hwnd = win_focus.find_window(_WINDOW_TITLE_SUBSTR)
        if not hwnd:
            return
        if self._hwnd != hwnd:
            self._hwnd = hwnd
        # Fast path: already foreground → skip expensive EnumWindows scan.
        if _WG and _WG.GetForegroundWindow() == hwnd:
            return
        self._minimize_overlapping_browsers(hwnd)
        win_focus.ensure_foreground(_WINDOW_TITLE_SUBSTR)

    # ------------------------------------------------------------------
    # Low-level helpers (all resolution-independent: click real rects)
    # ------------------------------------------------------------------

    def _find(self, title: str, control_type: str, timeout: float = 3.0,
              retry: bool = True):
        """Find a control by name+type.

        ``exists(timeout)`` blocks for the *full* timeout when the element is
        absent, so absence checks must pass a short timeout and ``retry=False``
        (otherwise every "is X gone?" probe costs ~timeout*2 + a reconnect).
        Present elements resolve fast. ``retry`` adds one reconnect attempt for
        elements that should exist (the Chromium a11y tree is rebuilt on
        navigation, transiently invalidating cached refs)."""
        try:
            ctrl = self._win.child_window(title=title, control_type=control_type)
            if ctrl.exists(timeout=timeout):
                return ctrl
        except Exception as exc:
            logger.debug(f"_find({title!r},{control_type}) error: {exc}")
        if retry:
            self._connect()
            time.sleep(0.2)
            try:
                ctrl = self._win.child_window(title=title, control_type=control_type)
                if ctrl.exists(timeout=min(timeout, 1.5)):
                    return ctrl
            except Exception:
                pass
        return None

    @staticmethod
    def _center(rect):
        return (rect.left + rect.right) // 2, (rect.top + rect.bottom) // 2

    def _rect(self, title: str, control_type: str, timeout: float = 3.0):
        """Find a control and capture its screen rectangle *immediately*,
        retrying across reconnects. pywinauto specs resolve lazily, so holding a
        spec across a page reload and calling ``.rectangle()`` later throws
        ElementNotFound — capturing the geometry up front avoids that.
        Only returns a rect for elements that are actually **visible** on screen
        (``is_visible()`` checks the UIA ``IsOffscreen`` property), so hidden
        tab content or off-screen elements are safely ignored."""
        for attempt in range(2):
            ctrl = self._find(title, control_type,
                              timeout=timeout if attempt == 0 else 1.2, retry=False)
            if ctrl is not None:
                try:
                    r = ctrl.rectangle()
                    if r.width() > 0 and r.height() > 0 and ctrl.is_visible():
                        return r
                except Exception:
                    pass
            self._connect()
            time.sleep(0.3)
        return None

    def _click_rect(self, rect, template_name: str = ""):
        if self.config.capture_templates and template_name and rect is not None:
            try:
                ui_vision.save_template(template_name, rect.left, rect.top,
                                        rect.width(), rect.height())
            except Exception:
                pass
        _pg().click(*self._center(rect))
        time.sleep(0.08)

    def _click_xy(self, x: int, y: int):
        _pg().click(x, y)
        time.sleep(0.08)

    def _click_vision(self, template_name: str) -> bool:
        m = ui_vision.locate(template_name)
        if m:
            logger.info(f"UIA miss; located {template_name!r} via vision (score={m.score:.2f}).")
            self._click_xy(m.x, m.y)
            return True
        return False

    def _paste_rect(self, rect, text: str):
        """Focus an edit (by rect), clear it (text + any filter chips), paste."""
        pg = _pg()
        pg.click(*self._center(rect))
        time.sleep(0.08)
        pg.hotkey("ctrl", "a")
        pg.press("delete")
        for _ in range(3):              # backspace clears leftover filter chips
            pg.press("backspace")
        if text:
            _set_clipboard(text)
            time.sleep(0.03)
            pg.hotkey("ctrl", "v")
            time.sleep(0.12)            # let the search dropdown react to the paste

    def _type_rect(self, rect, text: str, interval: float = 0.06):
        pg = _pg()
        pg.click(*self._center(rect))
        time.sleep(0.15)
        pg.hotkey("ctrl", "a")
        pg.press("delete")
        time.sleep(0.1)
        pg.typewrite(text, interval=interval)
        time.sleep(0.2)

    # ------------------------------------------------------------------
    # CREATE PROFILE
    # ------------------------------------------------------------------

    @_serialized
    def create_profile(self, name: str, proxy: str, group: str = "") -> dict:
        """Create a profile through the GUI. Returns a dict with the resolved
        ``profile_id`` (discovered from the Profiles list), ``name``, ``group``,
        ``proxy`` and ``proxy_passed``."""
        group = (group or self.config.group_name).strip()
        name = name.strip()
        logger.info(f"AdsPower UI: creating profile name={name!r} group={group!r} "
                    f"proxy={proxy.split(':')[0]}:***")

        self._connect()

        # Record the highest existing serial. AdsPower serials increase
        # monotonically and the list is newest-first, so the profile we are
        # about to create will be the first row with serial > this watermark —
        # dup-safe even if several profiles share the temp name.
        before_max = self._max_serial()
        logger.debug(f"Serial watermark before create: {before_max}")

        self._open_new_profile_form()
        self._switch_tab("General")
        self._fill_name(name)
        if group:
            self._select_group(group)

        self._switch_tab("Proxy")
        time.sleep(self.config.form_settle)
        self._fill_proxy(proxy)
        proxy_ok = self._check_proxy()
        if not proxy_ok and self.config.require_proxy_ok:
            raise AdsPowerUIError("Proxy check did not pass; aborting profile creation.")

        self._click_ok()

        profile_id = self._wait_for_new_profile_id(name, before_max)
        logger.info(f"AdsPower UI: created profile {profile_id or '<unknown>'} ({name!r}).")
        return {
            "profile_id": profile_id,
            "name": name,
            "group": group,
            "proxy": proxy,
            "proxy_passed": proxy_ok,
        }

    def _open_new_profile_form(self):
        # Already on the form? (OK button present)
        if self._find("OK", "Button", timeout=0.8, retry=False):
            return
        rect = self._rect("New Profile", "Button", timeout=3)
        if rect is not None:
            self._click_rect(rect, template_name="new_profile_btn")
        elif not self._click_vision("new_profile_btn"):
            raise AdsPowerUIError("Could not find the 'New Profile' button.")
        time.sleep(self.config.new_profile_wait)
        self._foreground()
        time.sleep(self.config.form_settle)
        self._connect()
        if not self._find("OK", "Button", timeout=4):
            raise AdsPowerUIError("New Profile form did not open.")

    def _switch_tab(self, tab: str):
        rect = self._rect(tab, "Text", timeout=3)
        if rect is not None:
            self._click_rect(rect)
            time.sleep(0.3)
        else:
            logger.warning(f"Tab {tab!r} not found via UIA; assuming already active.")

    def _fill_name(self, name: str):
        rect = self._rect("Optional: profile name", "Edit", timeout=4)
        if rect is None:
            raise AdsPowerUIError("Profile name field not found.")
        self._paste_rect(rect, name)
        logger.info(f"Filled profile name: {name!r}")

    def _select_group(self, group: str):
        rect = self._rect("Find a group", "Edit", timeout=3)
        if rect is None:
            logger.warning("Group field not found; profile will use the default group.")
            return
        # Typing (not pasting) triggers AdsPower's group autocomplete.
        self._type_rect(rect, group, interval=0.08)
        time.sleep(0.9)
        # Click the dropdown option that exactly matches the group, if visible.
        if not self._click_dropdown_option(group, below_top=rect.bottom):
            pg = _pg()
            pg.press("down")
            time.sleep(0.2)
            pg.press("enter")
        time.sleep(0.3)
        try:
            val = self._find("Find a group", "Edit", timeout=1)
            logger.info(f"Selected group {group!r} (field now: {val.get_value()!r}).")
        except Exception:
            logger.info(f"Selected group {group!r}.")

    def _click_dropdown_option(self, text: str, below_top: int) -> bool:
        """Click a freshly-rendered dropdown option matching ``text``."""
        for ct in ("Text", "ListItem"):
            for d in self._win.descendants(control_type=ct):
                try:
                    if (d.window_text() or "").strip() != text:
                        continue
                    r = d.rectangle()
                    if r.top > below_top and r.width() > 0:
                        self._click_xy(*self._center(r))
                        return True
                except Exception:
                    continue
        return False

    def _fill_proxy(self, proxy: str):
        """Paste the full proxy string into the Host field. AdsPower auto-parses
        ``host:port:user:pass`` into host/port/user/pass; type defaults to Socks5
        and IP checker to IP2Location (verified)."""
        host = self._rect("Please enter host", "Edit", timeout=4)
        if host is None:
            raise AdsPowerUIError("Proxy Host field not found (is the Proxy tab open?).")
        self._paste_rect(host, proxy.strip())
        time.sleep(0.8)
        # Best-effort sanity log of the parsed result.
        try:
            port = self._find("Port", "Edit", timeout=1)
            logger.info(f"Proxy pasted; parsed port={port.get_value()!r}.")
        except Exception:
            pass

    def _check_proxy(self) -> bool:
        btn = self._rect("Check Proxy", "Button", timeout=3)
        if btn is None:
            logger.warning("Check Proxy button not found; skipping proxy verification.")
            return False
        self._click_rect(btn, template_name="check_proxy_btn")
        logger.info("Clicked 'Check Proxy'; waiting for result...")
        deadline = time.time() + self.config.proxy_check_timeout
        result = None
        while time.time() < deadline:
            time.sleep(1.0)
            text = self._visible_text_blob()
            low = text.lower()
            if any(w in low for w in _PROXY_FAIL_WORDS):
                result = False
                break
            # success markers: a country/IP echoed, or explicit success words
            if "success" in low or "connected" in low or "available" in low:
                result = True
                break
        if result is None:
            # No explicit verdict — assume OK (production pre-validates proxies
            # via SnapBoard before we ever get here).
            result = True
            logger.info("Proxy check: no explicit verdict; proceeding (assumed OK).")
        else:
            logger.info(f"Proxy check verdict: {'OK' if result else 'FAILED'}.")
        return result

    def _click_ok(self):
        btn = self._rect("OK", "Button", timeout=4)
        if btn is not None:
            self._click_rect(btn, template_name="ok_btn")
        elif not self._click_vision("ok_btn"):
            raise AdsPowerUIError("Could not find the form OK button.")
        # Wait for the form to close (OK gone / New Profile button back).
        deadline = time.time() + 12
        while time.time() < deadline:
            time.sleep(0.6)
            self._connect()
            if not self._find("OK", "Button", timeout=0.8, retry=False):
                logger.info("Profile form submitted (OK closed).")
                return
        logger.warning("OK still present after submit — possible validation error.")

    # ------------------------------------------------------------------
    # PROFILE DISCOVERY (Profiles list)
    # ------------------------------------------------------------------

    _HEADER_LABELS = {
        "no./id", "group", "name", "ip", "last opened", "last\xa0opened",
        "platform", "tags", "date created", "custom no.", "#", "action",
        "profiles", "proxies", "trash", "cloud phone", "reset", "and",
        "referral bonus", "active", "employee", "overview",
    }

    @staticmethod
    def _search_fragment(name: str) -> str:
        """The part of the temporary name to type into a 'Name contains' search:
        the text after the last ':' so the shared 'Snapchat:' prefix is dropped
        ('Snapchat: Pending' -> 'Pending'). Searching the distinctive suffix keeps
        the result set tight; the EXACT full name is still used for the row match.
        Falls back to the whole (separator-stripped) name when there's no suffix
        ('Snapchat:' -> 'Snapchat')."""
        parts = [p.strip() for p in str(name or "").split(":") if p.strip()]
        return parts[-1] if parts else str(name or "").strip()

    def _rows_for_name(self, name: str):
        """Search 'Name contains <suffix of the temp name>' and return rows whose
        full name matches ``name`` exactly.

        ``name`` is the Nyxify ``temporary_profile_name`` setting (e.g.
        'Snapchat: Pending'). We type only the distinctive suffix ('Pending') into
        the 'Name contains' filter — dropping the shared 'Snapchat:' prefix — then
        keep only rows whose full name equals the configured temp name. AdsPower
        lists newest-first, so the just-created row lands on page 1; the caller
        pairs this with a serial watermark to stay correct under concurrent
        creators."""
        target = name.strip().lower()
        fragment = self._search_fragment(name)
        for attempt in range(2):
            self._search_by(fragment, field="Name", operator="contains")
            rows = [r for r in self._scan_rows() if r[2].strip().lower() == target and r[1]]
            if rows:
                return rows
        return []

    def _wait_for_new_profile_id(self, name: str, before_max: int) -> str:
        """Poll until the just-created profile (name matches, serial > the
        pre-create watermark) appears; return its profile id."""
        deadline = time.time() + self.config.create_id_timeout
        while time.time() < deadline:
            rows = self._rows_for_name(name)
            fresh = [r for r in rows if r[0] > before_max]
            if fresh:
                fresh.sort(reverse=True)            # newest serial = just created
                return fresh[0][1]
            if rows:                                # name matched but watermark race
                rows.sort(reverse=True)
                return rows[0][1]
            time.sleep(1.2)
        logger.warning(f"Could not resolve new profile id for name {name!r}.")
        return ""

    @_serialized
    def find_profile_id_by_name(self, name: str) -> Optional[str]:
        self._connect()
        rows = self._rows_for_name(name)
        if rows:
            rows.sort(reverse=True)
            return rows[0][1]
        return None

    def _max_serial(self) -> int:
        """Highest serial currently on page 1 (newest-first). Scanned twice to
        tolerate a slow list reload after Reset."""
        self._reset_search()
        self._wait_list_settled()
        best = 0
        for _ in range(2):
            rows = self._scan_rows()
            serials = [r[0] for r in rows]
            if serials:
                best = max(best, max(serials))
            time.sleep(0.6)
        return best

    def _scan_rows(self):
        """Parse the visible Profiles list into ``(serial:int, profile_id:str,
        name:str)`` tuples.

        Position-independent: cells are classified by *content* (a digits-only
        No., an alphanumeric ID, a "Snapchat:" name) and a serial is paired with
        the ID directly beneath it in the *same column* (relative x), so it works
        regardless of window size, position, DPI or column layout.
        """
        win = self._win
        serials = []   # (top, left, intval)
        ids = []       # (top, left, str)
        names = []     # (top, left, str)
        for t in win.descendants(control_type="Text"):
            try:
                # Read the *name* first (a single, relatively cheap property) and
                # classify on it; only fetch the rectangle for the handful of
                # elements that are actually a serial / id / name cell. Every UIA
                # property read is a slow cross-process round-trip on AdsPower's
                # huge CEF tree, so skipping rectangle() (and is_visible()) for the
                # ~80% of Text nodes that aren't rows is a big speedup. Using
                # ``element_info`` reads instead of the wrapper methods is ~2x
                # faster again.
                info = t.element_info
                s = (info.name or "").strip()
                if not s:
                    continue
                low = s.lower()
                if low in self._HEADER_LABELS:
                    continue
                if low.startswith("profile id is") or "filter" in low:
                    continue
                is_serial = s.isdigit() and len(s) >= 5
                is_id = (not is_serial) and bool(_PROFILE_ID_RE.match(s))
                is_name = (not is_serial and not is_id) and low.startswith("snapchat:")
                if not (is_serial or is_id or is_name):
                    continue
                r = info.rectangle
                if r.width() <= 0:
                    continue
                if is_serial:
                    serials.append((r.top, r.left, int(s)))
                elif is_id:
                    ids.append((r.top, r.left, s))
                else:
                    names.append((r.top, r.left, s))
            except Exception:
                continue

        rows = []
        for (s_top, s_left, serial) in serials:
            pid = ""
            best = 999
            for (i_top, i_left, ival) in ids:           # ID is just below the No.,
                d = i_top - s_top                        # in the same column
                if 6 <= d <= 32 and abs(i_left - s_left) <= 30 and d < best:
                    best, pid = d, ival
            rname = ""
            for (n_top, _nl, nval) in names:             # name shares the row band
                if abs(n_top - (s_top + 9)) <= 24:
                    rname = nval
                    break
            rows.append((serial, pid, rname))
        return rows

    # ------------------------------------------------------------------
    # SEARCH + OPEN BY ID
    # ------------------------------------------------------------------

    def _goto_profiles(self):
        # If a form is open (OK button present), cancel it first.
        if self._find("OK", "Button", timeout=0.8, retry=False):
            cancel = self._rect("Cancel", "Text", timeout=1)
            if cancel is not None:
                self._click_rect(cancel)
                time.sleep(1.0)
                self._foreground()
                self._connect()
        nav = self._rect("Profiles", "Text", timeout=1)
        if nav is not None:
            self._click_rect(nav)
            time.sleep(0.6)
        # Verify we landed on the Profiles tab by looking for the search bar.
        self._connect()
        if not self._find("Search or new search criteria", "Edit", timeout=1.5, retry=False):
            logger.warning("Profiles nav click did not land on the Profiles tab; retrying...")
            nav = self._rect("Profiles", "Text", timeout=2)
            if nav is not None:
                self._click_rect(nav)
                time.sleep(0.8)
            self._connect()

    def _reset_search(self):
        """Remove any active search/filter via the 'Reset' link (user req:
        'first remove the current search'). 'Reset' only renders when a filter is
        active, so this is a fast absence-tolerant check."""
        self._connect()
        ctrl = self._find("Reset", "Text", timeout=0.8, retry=False)
        if ctrl is None:
            return
        try:
            r = ctrl.rectangle()
            self._click_rect(r)
            self._connect()
            self._wait_list_settled()   # return as soon as the unfiltered list renders
        except Exception:
            pass

    def _search_by(self, value: str, field: str, operator: str):
        """Clear the current search, type ``value``, then click the dropdown
        suggestion row matching ``field``+``operator`` (e.g. 'Profile ID'/'is' or
        'Name'/'contains'). Falls back to Enter if the suggestion isn't found."""
        self._connect()
        self._reset_search()
        search = self._rect("Search or new search criteria", "Edit", timeout=4)
        if search is None:
            self._goto_profiles()
            search = self._rect("Search or new search criteria", "Edit", timeout=4)
        if search is None:
            raise AdsPowerUIError("Search bar not found on the Profiles page.")
        below = search.bottom
        left_min = search.left - 30          # suggestions align under the search box
        self._paste_rect(search, value)
        # The dropdown renders after a variable delay and its rows can appear in
        # ANY order, so retry the content-based (field+operator) match for a few
        # seconds. Enter is only a last resort: it applies AdsPower's default top
        # suggestion, which is order-dependent and usually the WRONG field
        # ('Profile No./ID is' instead of 'Name contains').
        # For a Profile-ID search, AdsPower's default top suggestion — what Enter
        # applies — is exactly 'Profile ID is <value>', so skip the slow
        # dropdown-match loop and submit directly. That loop re-scans the whole
        # (huge) accessibility tree every ~0.15s and, for ID searches, always
        # ended up pressing Enter anyway. Name searches still need the dropdown
        # (Enter would pick the wrong default field there).
        is_id_search = field.strip().lower().startswith("profile")
        clicked = False
        if not is_id_search:
            deadline = time.time() + 4.5
            while time.time() < deadline:
                self._connect()
                if self._click_dropdown_row(field, operator, below_top=below, left_min=left_min):
                    clicked = True
                    break
                time.sleep(0.15)            # poll fast; the dropdown can render late
            if not clicked:
                logger.warning(
                    f"Dropdown row {field!r}/{operator!r} not found after retries; pressing Enter "
                    f"(may apply the wrong default filter).")
        if not clicked:
            _pg().press("enter")
        time.sleep(0.4)
        self._foreground()
        time.sleep(0.15)
        self._connect()
        self._wait_list_settled()

    def _search_by_ids(self, ids):
        """Bulk ``Profile ID is <id1> <id2> ...`` search. AdsPower matches every
        space-separated id and shows them on one page, so a whole batch of opens
        shares ONE search instead of one (slow) search per profile. A single id
        is just a one-element bulk search — same path as a plain id search."""
        query = " ".join(str(i).strip() for i in ids if str(i).strip())
        if not query:
            raise AdsPowerUIError("_search_by_ids requires at least one profile id.")
        self._search_by(query, field="Profile ID", operator="is")

    def _click_dropdown_row(self, field: str, operator: str, below_top: int,
                            left_min: int = 460) -> bool:
        """Click the suggestion row containing both ``field`` and ``operator``
        labels. AdsPower renders each suggestion as separate Text controls
        (field / operator / value) sharing a row top, so we cluster by top.

        ``left_min`` is the left edge of the suggestion column — it aligns under
        the search box (~L480), NOT far right, so the threshold is derived from
        the search box position. (The old hard-coded ``left > 600`` skipped the
        whole dropdown, so 'Name contains' never matched and the search fell back
        to AdsPower's default 'Profile No./ID is' — searching by id, not name.)"""
        # Collect suggestion labels (below the search bar, in the suggestion
        # column) then group them into ROWS by top-proximity. A suggestion's
        # field/operator/value labels share a row top; rows are ~34px apart.
        # (Fixed 6px-bucket rounding split same-row labels across a boundary, so
        # the field+operator match failed intermittently and fell back to Enter —
        # which is why id/name search was flaky and slow.)
        items = []
        for t in self._win.descendants(control_type="Text"):
            try:
                s = (t.window_text() or "").strip()
                r = t.rectangle()
                if s and r.width() > 0 and r.top > below_top and r.left >= left_min:
                    items.append((r.top, r.left, r.right, r.bottom, s.lower()))
            except Exception:
                continue
        items.sort()
        rows = []
        for it in items:
            if rows and abs(it[0] - rows[-1][0][0]) <= 12:   # same visual row
                rows[-1].append(it)
            else:
                rows.append([it])
        fl, op = field.lower(), operator.lower()
        for row in rows:
            labels = {x[4] for x in row}
            if fl in labels and op in labels:
                cx = (min(x[1] for x in row) + max(x[2] for x in row)) // 2
                cy = (min(x[0] for x in row) + max(x[3] for x in row)) // 2
                self._click_xy(cx, cy)
                return True
        return False

    def _wait_list_settled(self, timeout: float = 8.0):
        """Wait until the Profiles list finishes (re)loading: either rows appear
        or an explicit empty-state is shown. Prevents scanning mid-reload."""
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self._scan_rows():
                return
            blob = self._visible_text_blob().lower()
            if "no data" in blob or "total: 0" in blob:
                return
            time.sleep(0.2)

    def open_profile_by_id(self, profile_id: str) -> str:
        """Open the profile in the AdsPower GUI via the search bar, then return a
        live Playwright ``ws://`` CDP endpoint (resolved by core.adspower_cdp).

        Only the GUI interaction (search + click Open) holds the global GUI lock;
        the ``already open?`` probe and the post-click CDP-resolve wait are plain
        HTTP polls, so they run *unlocked* — another task can drive its own open
        while this profile's browser is still launching, instead of every open
        serialising end-to-end (important when the runner opens many in parallel)."""
        from core.adspower_cdp import find_open_profile_cdp_endpoint

        profile_id = str(profile_id or "").strip()
        if not profile_id:
            raise AdsPowerUIError("open_profile_by_id requires a profile id.")

        # Already open? Use the cheap direct cache-dir match (deep_scan=False) —
        # the deep fallback HTTP-probes every open browser and is pathologically
        # slow when many profiles are open and this one isn't.
        endpoint = find_open_profile_cdp_endpoint(profile_id, deep_scan=False)
        if endpoint:
            logger.info(f"Profile {profile_id} already open: {endpoint}")
            return endpoint

        # Coalesce with any other concurrent opens into ONE bulk search (the
        # batcher holds the GUI lock for the locked half); the CDP-resolve wait
        # below stays unlocked so browsers still launch in parallel.
        _OPEN_BATCHER.submit(self, profile_id)

        deadline = time.time() + self.config.open_cdp_timeout
        while time.time() < deadline:
            endpoint = find_open_profile_cdp_endpoint(profile_id, deep_scan=False)
            if endpoint:
                logger.info(f"Profile {profile_id} opened via GUI; CDP: {endpoint}")
                return endpoint
            time.sleep(1.5)
        raise AdsPowerUIError(
            f"Opened profile {profile_id} in the GUI but could not resolve its CDP "
            f"endpoint. Is the browser still launching?")

    def _bulk_open_locked(self, ids, results):
        """Leader path (the GUI lock is already held by ``_OPEN_BATCHER``): ONE
        bulk ``Profile ID is <id...>`` search for the whole batch, then click each
        row's Open. Per-id failures are isolated so one bad id can't sink the
        batch."""
        self._connect()
        self._goto_profiles()
        # user requirement: first remove the current search, then search the id(s)
        self._search_by_ids(ids)
        if len(ids) > 1:
            logger.info(f"AdsPower UI: one bulk search served {len(ids)} open(s): "
                        f"{' '.join(ids)}")
        for pid in ids:
            res = results.get(pid)
            if res is None or res.event.is_set():
                continue
            try:
                self._open_one_in_batch(pid)
                res.ok = True
            except Exception as exc:
                res.ok, res.error = False, exc
                logger.warning(f"Bulk open: {pid} failed: {exc}")
            finally:
                res.event.set()

    def _open_one_in_batch(self, profile_id: str):
        """Click Open on ``profile_id``'s row within the bulk-search results.

        Aligns to the id's *own* row (``require_aligned`` — never falls back to
        some other visible Open button) and tolerates the 'already open' case
        (row shows Close instead of Open). It relies on ``_click_row_action``'s
        own robust retry loop rather than a fixed deadline: a single scan of
        AdsPower's huge tree can take 10-40s, so the old 5s wait timed out before
        even one scan finished and wrongly reported the row missing."""
        try:
            self._click_row_action(profile_id, "Open", template_name="open_btn",
                                   require_aligned=True)
        except AdsPowerUIError:
            # No alignable Open button — the profile may already be open (its row
            # shows Close). Treat that as success; otherwise re-raise.
            if self._row_has_button(profile_id, "Close"):
                logger.info(f"Profile {profile_id} already open during bulk batch; "
                            f"no Open click needed.")
                return
            raise

    def _click_open_for_id(self, profile_id: str):
        """Click the Action-column 'Open' button on the id's row."""
        self._click_row_action(profile_id, "Open", template_name="open_btn")

    def _bulk_close_locked(self, ids, results):
        """Leader path (the GUI lock is already held by ``_CLOSE_BATCHER``): ONE
        bulk ``Profile ID is <id...>`` search for the whole batch, then click each
        running row's red Close. Per-id failures are isolated. Each result's
        ``value`` is the close bool (True once the row reverts to Open / wasn't
        running)."""
        self._connect()
        self._goto_profiles()
        # user requirement: first remove the current search, then search the id(s)
        self._search_by_ids(ids)
        if len(ids) > 1:
            logger.info(f"AdsPower UI: one bulk search served {len(ids)} close(s): "
                        f"{' '.join(ids)}")
        for pid in ids:
            res = results.get(pid)
            if res is None or res.event.is_set():
                continue
            try:
                res.value = self._close_one_in_batch(pid)
                res.ok = True
            except Exception as exc:
                res.ok, res.error = False, exc
                logger.warning(f"Bulk close: {pid} failed: {exc}")
            finally:
                res.event.set()

    def _close_one_in_batch(self, profile_id: str, wait_timeout: float = 12.0) -> bool:
        """Close ``profile_id``'s row within the bulk-search results (aligned to
        its own row — many Close buttons are visible at once during a bulk close).
        Returns True once the row's action reverts to Open (or it wasn't running).
        Relies on ``_click_row_action``'s robust retry rather than a fixed
        deadline (a single scan of AdsPower's huge tree can take 10-40s)."""
        self._connect()
        try:
            self._click_row_action(profile_id, "Close", template_name="close_btn",
                                   require_aligned=True)
        except AdsPowerUIError:
            # No alignable Close button for this row — it isn't running (shows
            # Open). Nothing to close.
            logger.info(f"Profile {profile_id} is not running (no Close button); "
                        f"nothing to close.")
            return True
        # closing is immediate in AdsPower (no confirm), but accept one if it appears
        self._maybe_confirm(("OK", "Confirm", "Yes"), timeout=0.8)
        if self._wait_row_button(profile_id, "Open", timeout=wait_timeout):
            logger.info(f"Profile {profile_id} closed via GUI.")
            return True
        logger.warning(f"Clicked Close for {profile_id} but could not confirm it closed.")
        return False

    # ------------------------------------------------------------------
    # row helpers shared by open / close / rename / delete
    # ------------------------------------------------------------------

    def _row_center_y(self, profile_id: str) -> Optional[int]:
        """Vertical centre of the row whose No./ID cell == profile_id."""
        for t in self._win.descendants(control_type="Text"):
            try:
                if (t.window_text() or "").strip() == profile_id and t.is_visible():
                    r = t.rectangle()
                    if r.width() > 0:
                        return (r.top + r.bottom) // 2
            except Exception:
                continue
        return None

    def _row_id_rect(self, profile_id: str):
        for t in self._win.descendants(control_type="Text"):
            try:
                if (t.window_text() or "").strip() == profile_id and t.is_visible():
                    r = t.rectangle()
                    if r.width() > 0:
                        return r
            except Exception:
                continue
        return None

    def _list_header_bottom(self) -> int:
        """Bottom Y of the column-header row ('No./ID', 'Name', 'Action', ...).
        Per-row controls live below it; the window titlebar and the batch
        toolbar live above it. Used to keep row scans off the titlebar Close /
        toolbar buttons (position-independent — derived from the headers)."""
        bottoms = []
        for t in self._win.descendants(control_type="Text"):
            try:
                if t.is_visible() and (t.window_text() or "").strip() in (
                    "No./ID", "Name", "Action", "Group", "Platform"):
                    bottoms.append(t.rectangle().bottom)
            except Exception:
                continue
        return max(bottoms) if bottoms else 460

    def _click_row_action(self, profile_id: str, label: str, template_name: str = "",
                          require_aligned: bool = False):
        """Click the Action-column button whose text == ``label`` on the row whose
        No./ID == ``profile_id``. Only considers buttons *below the column
        headers*, so the window titlebar 'Close' and the batch toolbar are never
        hit. Aligning to the id's row avoids the toolbar batch button.

        ``require_aligned`` (used by the bulk open/close paths, where MANY rows
        and many ``label`` buttons are visible at once): never fall back to the
        first/topmost button — only click the button on the id's *own* row, and
        keep retrying until that row's id text has rendered. Without this a
        missing/late-rendering id would click some other row's Open/Close."""
        id_top = None
        btns = []   # (centre_y, left, rect)
        for _ in range(8):                  # a11y tree can be briefly empty post-filter
            self._connect()
            header_bottom = self._list_header_bottom()
            id_top = self._row_center_y(profile_id)
            btns = []
            for b in self._win.descendants(control_type="Button"):
                try:
                    if not b.is_visible() or (b.window_text() or "").strip() != label:
                        continue
                    r = b.rectangle()
                    cy = (r.top + r.bottom) // 2
                    if r.width() > 0 and r.height() > 0 and cy > header_bottom:
                        btns.append((cy, r.left, r))
                except Exception:
                    continue
            # In bulk mode we MUST resolve the id's row before clicking; keep
            # retrying until both the buttons AND the id row are visible.
            if btns and (id_top is not None or not require_aligned):
                break
            time.sleep(1.0)
        if not btns:
            raise AdsPowerUIError(
                f"No row {label!r} button found for the filtered profile {profile_id}.")

        max_left = max(b[1] for b in btns)
        row_btns = [b for b in btns if b[1] >= max_left - 60]   # Action column only
        target = None
        if id_top is not None:
            aligned = [b for b in row_btns if abs(b[0] - id_top) <= 22]
            if aligned:
                target = min(aligned, key=lambda b: abs(b[0] - id_top))[2]
        if target is None:
            if require_aligned:
                raise AdsPowerUIError(
                    f"Row for profile {profile_id} not found among {label!r} buttons "
                    f"(bulk-safe: refusing to click a different row).")
            row_btns.sort()
            target = row_btns[0][2]
        self._click_rect(target, template_name=template_name)
        logger.info(f"Clicked {label} for profile {profile_id}.")

    def _row_has_button(self, profile_id: str, label: str) -> bool:
        header_bottom = self._list_header_bottom()
        row_y = self._row_center_y(profile_id)
        if row_y is None:
            return False
        for b in self._win.descendants(control_type="Button"):
            try:
                if (b.window_text() or "").strip() != label:
                    continue
                r = b.rectangle()
                cy = (r.top + r.bottom) // 2
                if cy > header_bottom and abs(cy - row_y) <= 22:
                    return True
            except Exception:
                continue
        return False

    def _wait_row_button(self, profile_id: str, label: str, timeout: float = 12.0) -> bool:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._connect()
            if self._row_has_button(profile_id, label):
                return True
            time.sleep(1.0)
        return False

    def _has_text_prefix(self, prefix: str) -> bool:
        for t in self._win.descendants(control_type="Text"):
            try:
                if (t.window_text() or "").strip().startswith(prefix):
                    return True
            except Exception:
                continue
        return False

    def _maybe_confirm(self, labels, timeout: float = 1.5) -> bool:
        """Click the first present dialog button whose text matches ``labels``."""
        for label in labels:
            ctrl = self._find(label, "Button", timeout=timeout, retry=False)
            if ctrl is not None:
                try:
                    r = ctrl.rectangle()
                    if r.width() > 0 and r.height() > 0:
                        self._click_rect(r)
                        return True
                except Exception:
                    pass
        return False

    # ------------------------------------------------------------------
    # CLOSE
    # ------------------------------------------------------------------

    def close_profile_by_id(self, profile_id: str, wait_timeout: float = 12.0) -> bool:
        """Close a running profile via the GUI (search id -> click the row's red
        'Close' button). Returns True once the row's action reverts to 'Open'.

        Coalesced with any other concurrent closes into ONE bulk search by
        ``_CLOSE_BATCHER`` (the batcher holds the GUI lock and runs
        ``_bulk_close_locked``), so closing several profiles at once is one search
        instead of one per profile."""
        profile_id = str(profile_id or "").strip()
        if not profile_id:
            raise AdsPowerUIError("close_profile_by_id requires a profile id.")
        return bool(_CLOSE_BATCHER.submit(self, profile_id))

    # ------------------------------------------------------------------
    # RENAME
    # ------------------------------------------------------------------

    def _name_cell_rect(self, row_y: int):
        """Rect of the Name-column value Text on the row (between the 'Name' and
        'IP' column headers). The edit pencil sits just to its right."""
        name_hdr = ip_hdr = None
        for t in self._win.descendants(control_type="Text"):
            try:
                s = (t.window_text() or "").strip()
                if s == "Name" and name_hdr is None:
                    name_hdr = t.rectangle()
                elif s == "IP" and ip_hdr is None:
                    ip_hdr = t.rectangle()
            except Exception:
                continue
        if name_hdr is None:
            return None
        lo = name_hdr.left - 40
        hi = (ip_hdr.left - 12) if ip_hdr is not None else (name_hdr.right + 280)
        best = None
        for t in self._win.descendants(control_type="Text"):
            try:
                r = t.rectangle()
                if r.width() <= 0:
                    continue
                cy = (r.top + r.bottom) // 2
                cx = (r.left + r.right) // 2
                if abs(cy - row_y) <= 16 and r.left >= lo and cx <= hi:
                    if best is None or r.left < best.left:
                        best = r
            except Exception:
                continue
        return best

    def _open_rename_dialog(self, profile_id: str) -> bool:
        for _ in range(5):
            self._connect()
            row_y = self._row_center_y(profile_id)
            if row_y is not None:
                name_rect = self._name_cell_rect(row_y)
                if name_rect is not None:
                    px = name_rect.right + 12     # the edit pencil, just right of the name
                    py = (name_rect.top + name_rect.bottom) // 2
                    self._click_xy(px, py)
                    time.sleep(0.7)
                    if self._find("Enter Name", "Edit", timeout=1.5, retry=False) is not None:
                        return True
            time.sleep(0.8)
        return False

    @_serialized
    def rename_profile_by_id(self, profile_id: str, new_name: str) -> dict:
        """Rename a profile via the GUI (search id -> click the Name edit pencil ->
        type into the 'Enter Name' field -> OK). Works whether the profile is
        running or not."""
        profile_id = str(profile_id or "").strip()
        new_name = str(new_name or "").strip()
        if not profile_id:
            raise AdsPowerUIError("rename_profile_by_id requires a profile id.")
        if not new_name:
            raise AdsPowerUIError("rename_profile_by_id requires a new name.")
        self._connect()
        self._goto_profiles()
        self._search_by(profile_id, field="Profile ID", operator="is")
        if not self._open_rename_dialog(profile_id):
            raise AdsPowerUIError(f"Could not open the rename dialog for {profile_id}.")
        rect = self._rect("Enter Name", "Edit", timeout=4)
        if rect is None:
            raise AdsPowerUIError("Rename dialog opened but the name field was not found.")
        self._type_rect(rect, new_name)
        ok = self._rect("OK", "Button", timeout=4)
        if ok is None:
            raise AdsPowerUIError("Rename dialog OK button not found.")
        self._click_rect(ok, template_name="rename_ok_btn")
        time.sleep(0.6)
        logger.info(f"Renamed AdsPower profile {profile_id} -> {new_name!r} via GUI.")
        return {"profile_id": profile_id, "name": new_name}

    # ------------------------------------------------------------------
    # DELETE
    # ------------------------------------------------------------------

    def _select_row(self, profile_id: str) -> bool:
        """Tick the row's checkbox (just left of the No./ID column)."""
        for _ in range(4):
            self._connect()
            idr = self._row_id_rect(profile_id)
            if idr is not None:
                cx = idr.left - 34
                cy = (idr.top + idr.bottom) // 2
                self._click_xy(cx, cy)
                time.sleep(0.5)
                if self._has_text_prefix("Selected:"):
                    return True
            time.sleep(0.6)
        return False

    def _toolbar_trash_center(self):
        """Centre of the Delete (trash) icon — the 3rd unnamed Button after the
        batch toolbar 'Open': [Open] [Close] [Export] [Trash] [More]. The icons
        carry no accessible name, so we locate by order relative to 'Open'
        (and fall back to an opencv template)."""
        self._connect()
        header_bottom = self._list_header_bottom()
        ob = None
        for b in self._win.descendants(control_type="Button"):
            try:
                if (b.window_text() or "").strip() == "Open":
                    r = b.rectangle()
                    cy = (r.top + r.bottom) // 2
                    if r.width() > 0 and cy < header_bottom:   # the toolbar Open, above headers
                        if ob is None or r.top < ob.top:
                            ob = r
            except Exception:
                continue
        if ob is None:
            m = ui_vision.locate("delete_trash_btn")
            if m:
                return (m.x, m.y)
            raise AdsPowerUIError("Toolbar 'Open' button not found; cannot locate Delete.")
        ob_cy = (ob.top + ob.bottom) // 2
        cands = []
        for b in self._win.descendants(control_type="Button"):
            try:
                r = b.rectangle()
                if r.width() <= 0:
                    continue
                cy = (r.top + r.bottom) // 2
                # same toolbar row, right of Open, within the icon cluster
                if abs(cy - ob_cy) < 10 and r.left > ob.right + 2 and r.left < ob.right + 400:
                    cands.append((r.left, (r.left + r.right) // 2, cy))
            except Exception:
                continue
        cands.sort()
        if len(cands) >= 3:
            _, cx, cy = cands[2]            # [Close, Export, Trash]
            if self.config.capture_templates:
                try:
                    ui_vision.save_template("delete_trash_btn", cx - 20, cy - 20, 40, 40)
                except Exception:
                    pass
            return (cx, cy)
        m = ui_vision.locate("delete_trash_btn")
        if m:
            return (m.x, m.y)
        raise AdsPowerUIError(
            f"Could not locate the Delete toolbar icon (found {len(cands)} toolbar icons).")

    @_serialized
    def _tick_clear_cache(self) -> bool:
        """Tick 'Clear cache as well' in the Delete-profile dialog. AdsPower exposes
        no CheckBox control for it, so we click the box that sits just left of its
        label text."""
        for t in self._win.descendants(control_type="Text"):
            try:
                if (t.window_text() or "").strip().lower() == "clear cache as well":
                    r = t.rectangle()
                    if r.width() > 0:
                        self._click_xy(r.left - 14, (r.top + r.bottom) // 2)
                        logger.info("Ticked 'Clear cache as well' in the Delete dialog.")
                        time.sleep(0.3)
                        return True
            except Exception:
                continue
        logger.debug("'Clear cache as well' label not found; proceeding without it.")
        return False

    def delete_profile_by_id(self, profile_id: str) -> dict:
        """Delete a profile via the GUI. A *running* profile cannot be deleted
        (AdsPower blocks it), so close it first, then select the row and click the
        toolbar trash, tick 'Clear cache as well', and confirm. Returns
        ``{'code': 0}`` on success."""
        profile_id = str(profile_id or "").strip()
        if not profile_id:
            raise AdsPowerUIError("delete_profile_by_id requires a profile id.")
        self._connect()
        self._goto_profiles()
        self._search_by(profile_id, field="Profile ID", operator="is")

        self._connect()
        if self._row_has_button(profile_id, "Close"):
            logger.info(f"Profile {profile_id} is running; closing before delete.")
            try:
                self._click_row_action(profile_id, "Close", template_name="close_btn")
                self._wait_row_button(profile_id, "Open", timeout=12)
            except Exception as exc:
                logger.warning(f"Could not close {profile_id} before delete: {exc}")
            self._search_by(profile_id, field="Profile ID", operator="is")

        if not self._select_row(profile_id):
            raise AdsPowerUIError(f"Could not select the row for {profile_id} to delete.")
        cx, cy = self._toolbar_trash_center()
        self._click_xy(cx, cy)
        time.sleep(1.0)
        self._connect()
        # The "Delete profile" dialog: tick 'Clear cache as well', then confirm.
        # AdsPower's confirm button is literally 'Confirm deletion' — the old
        # generic labels never matched, so the dialog was left open and the delete
        # silently did nothing.
        self._tick_clear_cache()
        if not self._maybe_confirm(
                ("Confirm deletion", "Confirm", "Delete", "OK", "Yes"), timeout=3.0):
            logger.warning(f"Delete-dialog confirm button not found for {profile_id}.")
        time.sleep(1.0)

        # verify the row is gone
        self._search_by(profile_id, field="Profile ID", operator="is")
        self._connect()
        if self._row_center_y(profile_id) is None:
            logger.info(f"Deleted AdsPower profile {profile_id} via GUI.")
            return {"code": 0, "deleted": True, "profile_id": profile_id}
        raise AdsPowerUIError(
            f"Delete requested for {profile_id} but the profile row is still present.")

    # ------------------------------------------------------------------
    # misc
    # ------------------------------------------------------------------

    def _visible_text_blob(self) -> str:
        parts = []
        try:
            for t in self._win.descendants(control_type="Text"):
                s = (t.window_text() or "").strip()
                if s:
                    parts.append(s)
        except Exception:
            pass
        return " | ".join(parts)


# ---------------------------------------------------------------------------
# CLI smoke test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="AdsPower UI automation smoke test")
    ap.add_argument("--name", default="Snapchat: Pending")
    ap.add_argument("--group", default="Snapchat20")
    ap.add_argument("--proxy", default="48.45.190.63:42438:hwwrghLD:j432NPbg")
    ap.add_argument("--open", default="", help="Just open this profile id (skip create)")
    args = ap.parse_args()

    ctrl = AdsPowerUIController()
    if args.open:
        print("Endpoint:", ctrl.open_profile_by_id(args.open))
    else:
        info = ctrl.create_profile(name=args.name, proxy=args.proxy, group=args.group)
        print("Created:", info)
        if info["profile_id"]:
            print("Opening...")
            print("Endpoint:", ctrl.open_profile_by_id(info["profile_id"]))
