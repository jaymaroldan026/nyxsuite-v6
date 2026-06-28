#!/usr/bin/env python3
"""macOS: relocate the install out of TCC-protected folders.

Why this exists
---------------
On modern macOS, a browser (Chrome / Edge / Brave / ...) cannot launch a
native-messaging host that lives inside ~/Documents, ~/Desktop, ~/Downloads or
iCloud Drive. macOS attributes the spawned process to the browser (the TCC
"responsible process"), and the browser has no access to those protected
folders — so every read of the host code (the venv's ``pyvenv.cfg``,
``host_main.py``, the ``core`` package) is denied with ``Operation not
permitted``. Python dies during interpreter start-up, the host exits before it
speaks the native-messaging protocol, and Chrome reports the generic
"Native host has exited". The extension's Connect button then fails no matter
how correctly the host is registered.

Moving only the launcher out of the protected folder (as earlier versions did)
is not enough: the launcher still reaches *back into* the protected folder for
Python and the host code. The only robust fix is to run the whole app from a
folder that is never TCC-protected.

What this helper does
---------------------
Invoked by ``portable_launch_nyx.sh`` at start-up (under the system Python,
before any venv exists — so it must stay standard-library only):

* no-op on non-macOS, or when the install already lives in a safe location
  (prints nothing, exits 0 → the launcher keeps running in place);
* otherwise copies the app's *code* — never the venv, caches, logs, per-install
  token, or (on upgrades) the user's data — into
  ``~/Library/Application Support/NyxSuite/app`` and prints that path to stdout,
  so the launcher can ``cd`` there and re-exec from the safe location.

Contract: ONLY the safe install path is ever written to stdout. All human
progress/notices go to stderr (which the launcher lets flow to the terminal).
"""

import os
import shutil
import sys
from pathlib import Path

# Destination for the real install: ~/Library/Application Support is never
# TCC-protected and is not iCloud-synced, so a browser can always launch the
# native host from here. Co-located with the host launcher + app-data namespace.
SAFE_SUBPATH = ("Library", "Application Support", "NyxSuite", "app")

# Top-level entries that must never travel from the (protected) source copy:
#   .venv/venv  - absolute paths baked in; rebuilt in place at the destination
#   logs        - runtime logs
#   local_update_backups - rollback snapshots created in place
#   agent_token.txt - per-install secret; the destination generates its own
#   VCS / OS / Python cruft
BASE_EXCLUDE = {
    ".venv", "venv", "logs", "local_update_backups",
    "agent_token.txt", ".git", ".DS_Store", "__pycache__",
}
# Inside data/ these are regenerable and should not travel even on first install.
DATA_EXCLUDE = {"cache", "logs", "updates", "__pycache__", ".DS_Store"}

_IGNORE = shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store")


def _home():
    return Path(os.path.expanduser("~")).resolve()


def safe_root():
    return _home().joinpath(*SAFE_SUBPATH)


def _protected_roots():
    home = _home()
    return [
        home / "Documents",
        home / "Desktop",
        home / "Downloads",
        # iCloud Drive, incl. the "Desktop & Documents Folders" sync container.
        home / "Library" / "Mobile Documents",
    ]


def is_protected(path):
    """True if ``path`` lives inside a TCC-protected folder."""
    resolved = Path(path).resolve()
    for root in _protected_roots():
        try:
            resolved.relative_to(root)
            return True
        except ValueError:
            continue
    return False


def _parse_version(text):
    """Parse "4.7.2" → (4, 7, 2) for an ordered, downgrade-proof comparison."""
    parts = []
    for chunk in (text or "").strip().split("."):
        digits = ""
        for char in chunk:
            if char.isdigit():
                digits += char
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts) or (0,)


def _read_version(root):
    try:
        return (root / "VERSION").read_text(encoding="utf-8-sig").strip()
    except Exception:
        return ""


def _copy_app(source, dest, first_install):
    """Copy code from ``source`` into ``dest``.

    On a first install we also bring the user's ``data/`` (config, task DBs,
    seed name lists, bitmoji catalog) and any ``.env`` across so the relocated
    app picks up exactly where the unzip left off. On an upgrade we leave the
    destination's ``data/`` and ``.env`` untouched so an in-place install's
    config and queues are never clobbered by a re-run of the unzip launcher.
    """
    dest.mkdir(parents=True, exist_ok=True)
    excludes = set(BASE_EXCLUDE)
    if not first_install:
        excludes |= {"data", ".env"}

    for item in sorted(source.iterdir()):
        if item.name in excludes:
            continue
        target = dest / item.name
        if item.name == "data" and item.is_dir():
            # Copy data/ but drop the regenerable subdirs.
            target.mkdir(parents=True, exist_ok=True)
            for sub in sorted(item.iterdir()):
                if sub.name in DATA_EXCLUDE:
                    continue
                sub_target = target / sub.name
                if sub.is_dir():
                    shutil.copytree(sub, sub_target, dirs_exist_ok=True, ignore=_IGNORE)
                else:
                    shutil.copy2(sub, sub_target)
        elif item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True, ignore=_IGNORE)
        else:
            shutil.copy2(item, target)


def _mark_executable(dest):
    for rel in (
        "run_nyx_suite.command", "run_nyx_suite.sh", "portable_launch_nyx.sh",
        "agent_host/host_main.sh", "agent_host/host_main.py",
    ):
        path = dest / rel
        try:
            if path.exists():
                path.chmod(path.stat().st_mode | 0o111)
        except Exception:
            pass


def main():
    if sys.platform != "darwin":
        return 0

    source = Path(__file__).resolve().parents[1]
    dest = safe_root()

    # Already running from a safe place (incl. the safe root itself): nothing to
    # do — stay in place. Printing nothing tells the launcher to proceed here.
    if source == dest or not is_protected(source):
        return 0

    have_install = (dest / "bridge_app.py").exists()
    first_install = not have_install

    # Refresh the code only on first install, or when the unzipped source is
    # NEWER than what's already installed (an installer-driven upgrade). Never
    # downgrade over a copy that an in-app update may have moved ahead.
    source_is_newer = _parse_version(_read_version(source)) > _parse_version(_read_version(dest))
    if first_install or source_is_newer:
        sys.stderr.write(
            "\nNyx Suite (macOS): this folder is in a protected location "
            "(Documents/Desktop/Downloads/iCloud)\n"
            "where browsers can't launch the app's helper. Installing to a "
            "safe location:\n"
            f"  {dest}\n\n"
        )
        sys.stderr.flush()
        try:
            _copy_app(source, dest, first_install)
        except Exception as exc:
            sys.stderr.write(
                f"Could not relocate automatically: {exc}\n"
                "Please move the Nyx Suite folder to ~/Applications and run again.\n"
            )
            return 1
        _mark_executable(dest)
        sys.stderr.write("Install complete — launching from the safe location...\n\n")
        sys.stderr.flush()

    print(str(dest))
    return 0


if __name__ == "__main__":
    sys.exit(main())
