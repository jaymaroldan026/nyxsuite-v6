# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT = Path.cwd().resolve()
if not (ROOT / "core").exists() or not (ROOT / "packaging").exists():
    ROOT = Path(SPECPATH).resolve()
sys.path.insert(0, str(ROOT))
from core.version import NYX_VERSION_LABEL  # noqa: E402

RUNNER_NAME = f"NyxBot {NYX_VERSION_LABEL}"  # e.g. "NyxBot v6.0.0" — matches NyxController detection
block_cipher = None

hiddenimports = (
    collect_submodules("core")
    + collect_submodules("playwright")
    + collect_submodules("pywinauto")
    + collect_submodules("comtypes")
    + [
        "dotenv",
        "requests",
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
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
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
    name=RUNNER_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(ROOT / "icons8-origami-50.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=RUNNER_NAME,
)
