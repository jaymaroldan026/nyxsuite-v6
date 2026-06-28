"""Shared UI assets for the Nyx Suite bridge.

Kept dependency-light on purpose: the bridge tray pulls this in, so it must
import cleanly on machines without tkinter (e.g. Homebrew Python on macoS).
Windows-only calls are guarded and import their native deps lazily.
"""

import os
import sys

try:
    from PIL import Image
except Exception:
    Image = None

from core.process_utils import ROOT_DIR


def set_windows_app_id(app_id):
    """Set the taskbar AppUserModelID on Windows; no-op on other platforms."""
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(str(app_id))
    except Exception:
        pass


def iter_icon_asset_paths(file_names=("icons8-origami-50.ico", "icons8-origami-50.png")):
    search_roots = []
    meipass_dir = getattr(sys, "_MEIPASS", None)
    if meipass_dir:
        search_roots.append(ROOT_DIR.__class__(meipass_dir))
    search_roots.extend([ROOT_DIR, ROOT_DIR / "_internal", ROOT_DIR.parent])

    seen = set()
    for base_dir in search_roots:
        if not base_dir:
            continue
        for file_name in file_names:
            candidate = base_dir / file_name
            key = str(candidate).lower()
            if key in seen:
                continue
            seen.add(key)
            yield candidate


def load_tray_image(file_names=("icons8-origami-50.ico", "icons8-origami-50.png")):
    if Image is None:
        return None

    for icon_path in iter_icon_asset_paths(file_names):
        if not icon_path.exists():
            continue
        try:
            tray_image = Image.open(str(icon_path))
            tray_image.load()
            return tray_image
        except Exception:
            continue

    return None


NYXIFY_ICON_FILE_NAMES = ("icons8-origami-50-gray.ico", "icons8-origami-50-gray.png")
