"""Centralized pause/flush flag files for the Nyx and Nyxify runners.

These are the exact files the runner loops poll:

- Nyx pauses on ``PAUSE_FILE`` (default ``<logs>/bot.paused``) and flushes on
  ``RUN_REMAINING_FILE`` (default ``<logs>/run_remaining.flag``) — see ``main.py``.
- Nyxify pauses on ``NYXIFY_PAUSE_FILE`` (default ``<logs>/nyxify_runner.paused``)
  — see ``nyxify_runner.py``.

The bridge supervisor writes these via the helpers here and passes the same
paths into each runner's environment (see :func:`runner_env`), so a pause/flush
from the dashboard or tray reliably reaches the running process. The legacy
tkinter UIs keep their own inline copies; this module is the shared home for the
headless (bridge) path.
"""

import json
import os
from pathlib import Path

from core.process_utils import LOGS_DIR


def _resolve(env_name: str, default_name: str) -> Path:
    return Path(os.getenv(env_name, str(LOGS_DIR / default_name)))


NYX_PAUSE_FILE = _resolve("PAUSE_FILE", "bot.paused")
NYX_FLUSH_FILE = _resolve("RUN_REMAINING_FILE", "run_remaining.flag")
NYXIFY_PAUSE_FILE = _resolve("NYXIFY_PAUSE_FILE", "nyxify_runner.paused")
# Health flag written by the Nyx runner when an environment problem (AdsPower
# Local API permission / unreachable) blocks the whole queue. The bridge reads
# it to surface a banner; it is NOT the user pause flag, so it never fights a
# manual pause and clears automatically once AdsPower is healthy again.
NYX_HEALTH_FILE = _resolve("NYX_HEALTH_FILE", "nyx_health.json")


def _set_flag(path: Path, on: bool, body: str = "1") -> None:
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    if on:
        path.write_text(body, encoding="utf-8")
    elif path.exists():
        path.unlink()


# --- Nyx ---
def nyx_set_paused(paused: bool) -> None:
    _set_flag(NYX_PAUSE_FILE, bool(paused), "paused")


def nyx_is_paused() -> bool:
    return NYX_PAUSE_FILE.exists()


def nyx_request_flush() -> None:
    _set_flag(NYX_FLUSH_FILE, True, "flush")


def nyx_clear_flush() -> None:
    _set_flag(NYX_FLUSH_FILE, False)


def nyx_flush_requested() -> bool:
    return NYX_FLUSH_FILE.exists()


def nyx_set_health(payload: dict) -> None:
    """Record a runner health problem (e.g. AdsPower permission denied)."""
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        NYX_HEALTH_FILE.write_text(json.dumps(payload or {}), encoding="utf-8")
    except Exception:
        pass


def nyx_clear_health() -> None:
    try:
        if NYX_HEALTH_FILE.exists():
            NYX_HEALTH_FILE.unlink()
    except Exception:
        pass


def nyx_get_health():
    """Return the current health problem dict, or None when healthy."""
    try:
        if not NYX_HEALTH_FILE.exists():
            return None
        raw = NYX_HEALTH_FILE.read_text(encoding="utf-8") or ""
        data = json.loads(raw) if raw.strip() else None
        return data if isinstance(data, dict) and data else None
    except Exception:
        return None


# --- Nyxify ---
def nyxify_set_paused(paused: bool) -> None:
    _set_flag(NYXIFY_PAUSE_FILE, bool(paused), "paused")


def nyxify_is_paused() -> bool:
    return NYXIFY_PAUSE_FILE.exists()


def runner_env() -> dict:
    """Env vars to inject into spawned runners so they watch these exact paths."""
    return {
        "PAUSE_FILE": str(NYX_PAUSE_FILE),
        "RUN_REMAINING_FILE": str(NYX_FLUSH_FILE),
        "NYXIFY_PAUSE_FILE": str(NYXIFY_PAUSE_FILE),
        "NYX_HEALTH_FILE": str(NYX_HEALTH_FILE),
    }
