# -*- mode: python ; coding: utf-8 -*-
import os
import subprocess

from PyInstaller.utils.hooks import (
    collect_all,
    collect_data_files,
    collect_submodules,
    copy_metadata,
    collect_dynamic_libs,
)
from importlib.metadata import PackageNotFoundError
from modules.platformModules import win
from __version__ import __author__, __appname__, __version__

is_dev_build = any(char.isalpha() for char in __version__)

if is_dev_build:
    __appname__ = f"{__appname__} (Beta)"

block_cipher = None


def safe_copy_metadata(package_name):
    try:
        return copy_metadata(package_name)
    except PackageNotFoundError:
        return []


binaries = []

datas = [
    ("build_count.json", "."),
    # ("release_config.json", "."),
    ("theme/N8VENTURES.json", "./theme"),
]
datas += collect_data_files("certifi")
datas += collect_data_files("customtkinter")


datas += [
    ("assets/icons/win/icon.ico", "assets/icons/win"),
    ("assets/icons/win/icon.png", "assets/icons/win"),
]
if is_dev_build:
    datas += [
        ("assets/icons/win/icon-dev.ico", "assets/icons/win"),
        ("assets/icons/win/icon-dev.png", "assets/icons/win"),
    ]
    icon = "assets/icons/win/icon-dev.ico"
else:
    icon = "assets/icons/win/icon.ico"

a = Analysis(  # type: ignore
    ["mainGUI.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=[],
    hookspath=["./hooks"],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)  # type: ignore

exe = EXE(  # type: ignore
    pyz,
    a.scripts,
    a.binaries if win else [],
    a.datas if win else [],
    exclude_binaries=not win,
    name=f"{__appname__}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,  # signing handled post-build by devtools.py
    entitlements_file=None,  # avoids --timestamp failures with Apple Dev certs
    icon=icon,
    version="main.rc",
)
