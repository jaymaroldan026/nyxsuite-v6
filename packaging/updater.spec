# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


ROOT = Path.cwd().resolve()
if not (ROOT / "core").exists() or not (ROOT / "packaging").exists():
    ROOT = Path(SPECPATH).resolve()
block_cipher = None

a = Analysis(
    [str(ROOT / "packaging" / "updater.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "core",
        "core.update_backup",
        "core.process_utils",
        "core.release_updater",
    ],
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="Updater",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    icon=str(ROOT / "icons8-origami-50.ico"),
)
