# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for the Nyx Suite bridge (tray app + dashboard + product APIs).
# Produces "NyxSuite <version>" and bundles the offline webui/ SPA.

import sys
from pathlib import Path

from PyInstaller.building.datastruct import Tree
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path.cwd().resolve()
if not (ROOT / "core").exists() or not (ROOT / "packaging").exists():
    ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT))
from core.version import NYX_VERSION_LABEL  # noqa: E402

APP_NAME = f"NyxSuite {NYX_VERSION_LABEL}"
block_cipher = None

hiddenimports = (
    collect_submodules("core")
    + collect_submodules("pystray")
    + collect_submodules("playwright")
    + collect_submodules("PIL")
    + collect_submodules("pywinauto")
    + collect_submodules("comtypes")
    + [
        "dotenv",
        "pystray",
        "pystray._win32",
        "PIL",
        "requests",
        "certifi",
        "cv2",
        "numpy",
        "pyautogui",
        "pyperclip",
        "win32api",
        "win32clipboard",
        "win32con",
        "win32event",
        "win32gui",
        "win32process",
    ]
)

a = Analysis(
    [str(ROOT / "bridge_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        (str(ROOT / "icons8-origami-50.ico"), "."),
        (str(ROOT / "icons8-origami-50.png"), "."),
    ] + collect_data_files("certifi"),
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "icons8-origami-50.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    Tree(str(ROOT / "webui"), prefix="webui"),
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
