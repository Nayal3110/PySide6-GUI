# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for TDAM Acquisition Tool."""

import sys
from pathlib import Path

block_cipher = None

ROOT = Path(SPECPATH)

a = Analysis(
    [str(ROOT / "tdam_launcher.py")],
    pathex=[str(ROOT), str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "config"), "config"),
        (str(ROOT / "src" / "tdam" / "ui" / "resources"), "src/tdam/ui/resources"),
    ],
    hiddenimports=[
        "PySide6.QtSvg",
        "numpy",
        "serial",
        "serial.tools",
        "serial.tools.list_ports",
        "sqlite3",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "pytest",
        "pytest_cov",
        "pyinstaller",
        "tkinter",
        "matplotlib",
    ],
    noarchive=False,
    cipher=block_cipher,
)

pyz = PYZ(a.pure, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="TDAM",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon=str(ROOT / "tdam.ico"),  # multi-size Windows .ico
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="TDAM",
)
