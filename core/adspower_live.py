"""No-API live AdsPower browser state for dashboard snapshots.

This intentionally uses the same CDP discovery path as the Playwright fallback:
AdsPower writes ``DevToolsActivePort`` files for open SunBrowser profiles, and
we liveness-check those localhost CDP endpoints. No AdsPower Local API calls are
made here.
"""

import os
import threading
import time

from core.adspower_cdp import list_open_profile_endpoints


def _float_env(name, default):
    try:
        return float(os.getenv(name, str(default)) or default)
    except (TypeError, ValueError):
        return float(default)


REFRESH_INTERVAL_SECONDS = max(0.25, _float_env("ADSPOWER_LIVE_REFRESH_INTERVAL_SECONDS", 0.75))


def _normalize(value):
    return str(value or "").strip()


class _OpenProfileCache:
    def __init__(self):
        self._lock = threading.Lock()
        self._open_ids = set()
        self._error = ""
        self._checked_at = 0.0
        self._refreshing = False

    def snapshot(self):
        now = time.monotonic()
        start_refresh = False
        with self._lock:
            stale = (now - self._checked_at) >= REFRESH_INTERVAL_SECONDS
            if stale and not self._refreshing:
                self._refreshing = True
                start_refresh = True
            payload = {
                "open_ids": set(self._open_ids),
                "error": self._error,
                "checked_at": self._checked_at,
                "refreshing": self._refreshing,
                "ready": self._checked_at > 0,
            }

        if start_refresh:
            threading.Thread(target=self._refresh, daemon=True).start()

        return payload

    def _refresh(self):
        open_ids = set()
        error = ""
        try:
            endpoints = list_open_profile_endpoints()
            open_ids = {
                profile_id
                for profile_id in (_normalize(key) for key in endpoints.keys())
                if profile_id
            }
        except Exception as exc:
            error = str(exc)

        with self._lock:
            if not error:
                self._open_ids = open_ids
            self._error = error
            self._checked_at = time.monotonic()
            self._refreshing = False


_OPEN_PROFILE_CACHE = _OpenProfileCache()


def open_profile_snapshot():
    return _OPEN_PROFILE_CACHE.snapshot()


def annotate_rows_with_open_state(rows, id_fields):
    snapshot = open_profile_snapshot()
    open_ids = snapshot.get("open_ids") or set()
    ready = bool(snapshot.get("ready"))

    for row in rows:
        profile_id = ""
        for field in id_fields:
            profile_id = _normalize(row.get(field))
            if profile_id:
                break
        row["adspower_open_profile_id"] = profile_id
        row["adspower_open"] = (profile_id in open_ids) if (ready and profile_id) else None

    return {
        "source": "cdp",
        "open": len(open_ids),
        "error": snapshot.get("error") or "",
        "refreshing": bool(snapshot.get("refreshing")),
        "ready": ready,
    }
