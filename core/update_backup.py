"""Auto-backup, one-click rollback, and a post-update launch watchdog.

Design (frozen builds):
  * Before the sidecar swaps in a new release, it snapshots the current install
    to ``local_update_backups/<version>/`` (skipping data/logs/.env and the
    backups dir itself) and writes ``.pending_verify``.
  * On the next launch the app calls :func:`confirm_or_rollback`. If the new
    build keeps crash-looping (``attempts`` exceeds ``max``), it rolls back to
    the previous version; otherwise it arms a short timer that clears
    ``.pending_verify`` once the app has stayed alive.
  * Rollback reuses the EXISTING sidecar swap — a backup folder *is* a valid
    staging folder — so there is no second swap implementation.

Tk-free and import-light so the sidecar (``packaging/updater.py``) and the
bridge can both import it. Rollback only does real work in a frozen install
(where ``Updater.exe`` exists); in source mode it raises and the caller handles it.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import sys
import threading
import time
from pathlib import Path

BACKUPS_DIRNAME = "local_update_backups"
PENDING_VERIFY_NAME = ".pending_verify"
KEEP_BACKUPS = 2
DEFAULT_SKIP = ["data", "logs", ".env", BACKUPS_DIRNAME]


def _install_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    from core.process_utils import ROOT_DIR

    return ROOT_DIR


def _root(install_root=None) -> Path:
    return Path(install_root).resolve() if install_root else _install_root()


def backups_dir(install_root=None) -> Path:
    d = _root(install_root) / BACKUPS_DIRNAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def read_version(install_root=None) -> str:
    vf = _root(install_root) / "VERSION"
    if vf.exists():
        try:
            return vf.read_text(encoding="utf-8-sig").strip()
        except Exception:
            return ""
    return ""


def _safe(name: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(name or "").strip()) or "unknown"


def _should_skip(rel: Path, skips) -> bool:
    rel_str = str(rel).replace("\\", "/")
    for skip in skips:
        clean = str(skip).replace("\\", "/").strip("/")
        if not clean:
            continue
        if rel_str == clean or rel_str.startswith(clean + "/"):
            return True
    return False


def snapshot_install(install_root=None, skip_paths=None) -> Path:
    """Copy the current install (minus user data + extensions + backups) to
    ``local_update_backups/<version>/`` and return that folder.

    In the new release structure the ZIP only carries extensions + data.
    Exes are installed separately and never replaced, so the snapshot only
    needs to capture the VERSION file, update_config.json, and any other
    non-exe, non-data files for rollback purposes.
    """
    root = _root(install_root)
    skips = list(skip_paths or DEFAULT_SKIP)
    if BACKUPS_DIRNAME not in [str(s).strip("/").replace("\\", "/") for s in skips]:
        skips.append(BACKUPS_DIRNAME)

    version = read_version(root) or "unknown"
    dest_root = backups_dir(root) / _safe(version)
    if dest_root.exists():
        shutil.rmtree(dest_root, ignore_errors=True)
    dest_root.mkdir(parents=True, exist_ok=True)

    for dirpath, _dirnames, filenames in os.walk(root):
        for filename in filenames:
            src = Path(dirpath) / filename
            try:
                rel = src.relative_to(root)
            except ValueError:
                continue
            if _should_skip(rel, skips):
                continue
            dest = dest_root / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.copy2(src, dest)
            except Exception:
                pass
    _prune(root, KEEP_BACKUPS)
    return dest_root


def list_backups(install_root=None):
    """Return backup version names, newest first."""
    d = backups_dir(install_root)
    dirs = [p for p in d.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return [p.name for p in dirs]


def _prune(install_root, keep: int) -> None:
    d = backups_dir(install_root)
    dirs = [p for p in d.iterdir() if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    for old in dirs[max(0, int(keep)):]:
        shutil.rmtree(old, ignore_errors=True)


def rollback_to(version: str, install_root=None) -> int:
    """Restore a previous version by pointing the sidecar at its backup folder.
    Returns the spawned updater PID. Frozen-only (needs Updater.exe)."""
    root = _root(install_root)
    backup = backups_dir(root) / _safe(version)
    if not backup.is_dir():
        raise FileNotFoundError(f"No backup found for version {version!r} at {backup}")
    from core.release_updater import apply_update_via_sidecar

    return apply_update_via_sidecar(backup, root)


# ----------------------------------------------------------------- watchdog
def _pending_path(install_root=None) -> Path:
    return backups_dir(install_root) / PENDING_VERIFY_NAME


def write_pending_verify(new: str, prev: str, install_root=None, max_attempts: int = 3) -> None:
    payload = {"new": str(new or ""), "prev": str(prev or ""), "attempts": 0, "max": int(max_attempts)}
    try:
        _pending_path(install_root).write_text(json.dumps(payload), encoding="utf-8")
    except Exception:
        pass


def mark_update_verified(install_root=None) -> None:
    try:
        _pending_path(install_root).unlink(missing_ok=True)
    except Exception:
        pass


def confirm_or_rollback(install_root=None, verify_after: float = 30.0):
    """Call once on startup. Returns a tuple describing the action taken:
      * None                      — no pending update to verify
      * ("pending", attempts)     — armed a timer to mark verified if we survive
      * ("rollback", pid)         — crash-loop detected; rolled back to prev
      * ("giveup", None)          — crash-loop but no usable backup
    """
    pf = _pending_path(install_root)
    if not pf.exists():
        return None
    try:
        data = json.loads(pf.read_text(encoding="utf-8-sig") or "{}")
    except Exception:
        mark_update_verified(install_root)
        return None

    attempts = int(data.get("attempts", 0)) + 1
    max_attempts = int(data.get("max", 3))
    prev = str(data.get("prev") or "")

    if attempts > max_attempts:
        mark_update_verified(install_root)
        if prev:
            try:
                return ("rollback", rollback_to(prev, install_root))
            except Exception:
                return ("giveup", None)
        return ("giveup", None)

    data["attempts"] = attempts
    try:
        pf.write_text(json.dumps(data), encoding="utf-8")
    except Exception:
        pass

    timer = threading.Timer(float(verify_after), mark_update_verified, args=(install_root,))
    timer.daemon = True
    timer.start()
    return ("pending", attempts)
