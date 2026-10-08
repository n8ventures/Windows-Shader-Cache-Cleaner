"""
shader_cache_core.py — cache discovery, Steam auto-detection, sizing,
and deletion for N8's Shader Cache Cleaner.

No UI code lives here. mainGUI.py drives everything in this module from
a background thread and reports progress back via plain callbacks, same
split as media_core.py / mainGUI.py in the other apps.

Windows-only: every cache path below is a Windows env-var location, and
Steam detection goes through the Windows registry. Importing this on
another platform won't crash (winreg import is guarded), but every path
will simply resolve to "missing".
"""

import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from modules.configModule import get_setting, set_setting
from modules.platformModules import config_dir

try:
    import winreg

    HAVE_WINREG = True
except ImportError:  # not on Windows
    HAVE_WINREG = False

try:
    import ctypes
except ImportError:
    ctypes = None


# --------------------------------------------------------------------------
# Custom Steam paths persist through modules/configModule.py — the same
# config.json every other setting in the app already lives in (anchored
# to platformModules.config_dir, which is keyed off __appname__). This
# used to keep its own separate config.json in a hardcoded
# "N8 Ventures/ShaderCacheCleaner" folder that had nothing to do with
# __appname__ — two config files for one app, drifting apart the moment
# __appname__ ever changes. Not anymore.
# --------------------------------------------------------------------------
def load_custom_steam_paths() -> list:
    return get_setting("custom_steam_paths", [])


def add_custom_steam_path(path: str):
    paths = load_custom_steam_paths()
    if path not in paths:
        paths.append(path)
    set_setting("custom_steam_paths", paths)


def remove_custom_steam_path(path: str):
    set_setting("custom_steam_paths", [p for p in load_custom_steam_paths() if p != path])


# --------------------------------------------------------------------------
# Cache entry model
# --------------------------------------------------------------------------
VENDORS = ["WIN", "AMD", "NVIDIA", "INTEL", "STEAM"]
VENDOR_LABELS = {
    "WIN": "Windows / DirectX",
    "AMD": "AMD",
    "NVIDIA": "NVIDIA",
    "INTEL": "Intel",
    "STEAM": "Steam",
}


@dataclass
class CacheEntry:
    name: str
    path: Path
    vendor: str  # one of VENDORS
    size_bytes: Optional[int] = None  # None until scanned
    status: str = "unknown"  # unknown | ok | missing | locked


# --------------------------------------------------------------------------
# Steam auto-detection
# --------------------------------------------------------------------------
def _steam_install_path() -> Optional[Path]:
    """HKCU first (no admin needed, present once Steam has ever run for
    this user), then the 32-bit view of HKLM as a fallback."""
    if not HAVE_WINREG:
        return None
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam") as key:
            val, _ = winreg.QueryValueEx(key, "SteamPath")
            return Path(val)
    except OSError:
        pass
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam") as key:
            val, _ = winreg.QueryValueEx(key, "InstallPath")
            return Path(val)
    except OSError:
        return None


def _steam_library_paths(steam_install: Path) -> list:
    """Every registered Steam library (main install included), parsed out
    of libraryfolders.vdf. Regex over the file rather than a real VDF
    parser — the format is simple enough and this avoids a dependency —
    but it's still far more reliable than the batch-script equivalent.
    Falls back to just the main install dir if the vdf is missing, unreadable,
    or has nothing library-shaped in it.
    """
    libraries = [steam_install]
    vdf = steam_install / "steamapps" / "libraryfolders.vdf"
    if not vdf.exists():
        return libraries
    try:
        text = vdf.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return libraries
    for match in re.finditer(r'"path"\s*"([^"]+)"', text):
        raw = match.group(1).replace("\\\\", "\\")
        p = Path(raw)
        if p not in libraries and p.exists():
            libraries.append(p)
    return libraries


def discover_steam_caches(custom_paths: list) -> list:
    entries = []
    steam_install = _steam_install_path()
    if steam_install:
        libraries = _steam_library_paths(steam_install)
        for i, lib in enumerate(libraries):
            label = "main library" if i == 0 else f"library {i + 1}"
            entries.append(
                CacheEntry(
                    name=f"Steam Shader Cache ({label})",
                    path=lib / "steamapps" / "shadercache",
                    vendor="STEAM",
                )
            )
    else:
        # Registry lookup failed outright (Steam never installed for this
        # user, or a non-standard setup) — fall back to the conventional
        # default so there's still something to show, even if it just
        # reports "not found".
        default_root = Path(os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"))
        entries.append(
            CacheEntry(
                name="Steam Shader Cache (default library)",
                path=default_root / "Steam" / "steamapps" / "shadercache",
                vendor="STEAM",
            )
        )
    for i, custom in enumerate(custom_paths, start=1):
        entries.append(
            CacheEntry(
                name=f"Steam Shader Cache (custom path {i})",
                path=Path(custom),
                vendor="STEAM",
            )
        )
    return entries


# --------------------------------------------------------------------------
# Full cache list
# --------------------------------------------------------------------------
def build_cache_list() -> list:
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    roaming = Path(os.environ.get("APPDATA", ""))

    entries = [
        CacheEntry("Windows DirectX Shader Cache", local / "D3DSCache", "WIN"),
        CacheEntry("DX12 Pipeline Cache", local / "Temp" / "DXCache", "WIN"),
        CacheEntry("Windows DirectX Alt Cache", local / "Microsoft" / "DirectX Shader Cache", "WIN"),
        CacheEntry("Direct3D Pipeline Cache", local / "Temp" / "D3DCache", "WIN"),
        CacheEntry("AMD DX Cache", local / "AMD" / "DXCache", "AMD"),
        CacheEntry("AMD DirectX Shader Compiler Cache", local / "AMD" / "DxcCache", "AMD"),
        CacheEntry("AMD DX9 Cache", local / "AMD" / "DX9Cache", "AMD"),
        CacheEntry("AMD OpenGL Cache", local / "AMD" / "GLCache", "AMD"),
        CacheEntry("AMD OpenGL Legacy Cache", local / "AMD" / "OglCache", "AMD"),
        CacheEntry("AMD Vulkan Cache", local / "AMD" / "VkCache", "AMD"),
        CacheEntry("AMD OpenCL Cache", local / "AMD" / "cl.cache", "AMD"),
        CacheEntry("NVIDIA Pipeline Cache", local / "Temp" / "NVIDIA Corporation" / "NV_Cache", "NVIDIA"),
        CacheEntry("NVIDIA DX Cache", local / "NVIDIA" / "DXCache", "NVIDIA"),
        CacheEntry("NVIDIA OpenGL Cache", local / "NVIDIA" / "GLCache", "NVIDIA"),
        CacheEntry("NVIDIA Vulkan Cache", local / "NVIDIA" / "VkCache", "NVIDIA"),
        CacheEntry("NVIDIA Compute Cache", roaming / "NVIDIA" / "ComputeCache", "NVIDIA"),
        CacheEntry("NVIDIA App DX Cache", local / "NVIDIA App" / "DXCache", "NVIDIA"),
        CacheEntry("NVIDIA App OpenGL Cache", local / "NVIDIA App" / "GLCache", "NVIDIA"),
        CacheEntry("NVIDIA App Vulkan Cache", local / "NVIDIA App" / "VkCache", "NVIDIA"),
        CacheEntry("Intel Shader Cache", local / "Intel" / "ShaderCache", "INTEL"),
    ]

    config = load_custom_steam_paths()
    entries.extend(discover_steam_caches(config))
    return entries


# --------------------------------------------------------------------------
# Size + clear operations — meant to be called off the UI thread; each
# takes an optional per-entry callback so the GUI can update live.
# --------------------------------------------------------------------------
def folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += (Path(root) / f).stat().st_size
            except OSError:
                pass
    return total


def scan_all(entries: list, on_each: Optional[Callable[[CacheEntry], None]] = None) -> None:
    """Fills in size_bytes/status for each entry, in place."""
    for entry in entries:
        if entry.path.exists():
            entry.size_bytes = folder_size(entry.path)
            entry.status = "ok"
        else:
            entry.size_bytes = 0
            entry.status = "missing"
        if on_each:
            on_each(entry)


def clear_entry(entry: CacheEntry) -> int:
    """Deletes and recreates one cache folder or file. Returns bytes freed.
    Sets entry.status to 'ok' (cleared), 'missing' (nothing there), or
    'locked' (something's holding a file open — matches the batch
    script's behavior of leaving it and moving on rather than failing
    the whole run)."""
    if not entry.path.exists():
        entry.status = "missing"
        entry.size_bytes = 0
        return 0

    freed = entry.size_bytes if entry.size_bytes is not None else folder_size(entry.path)
    try:
        if entry.path.is_dir():
            shutil.rmtree(entry.path, ignore_errors=True)
        else:
            entry.path.unlink(missing_ok=True)
    except OSError:
        pass

    if entry.path.exists():
        entry.status = "locked"
        log_event(f"[LOCKED] {entry.name} ({entry.path}) - could not fully clear")
        return 0

    try:
        if entry.path.suffix:
            # file-like cache entries are removed and left absent; keep a single
            # file entry from reappearing as a folder when the cache was never a dir.
            pass
        else:
            entry.path.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    entry.status = "ok"
    log_event(f"[OK] {entry.name} ({entry.path}) - freed {human_size(freed)}")
    entry.size_bytes = 0
    return freed


def clear_all(entries: list, on_each: Optional[Callable[[CacheEntry, int], None]] = None) -> int:
    """Clears every given entry, returns total bytes freed. on_each fires
    after each entry with (entry, bytes_freed_for_that_entry)."""
    total_freed = 0
    for entry in entries:
        freed = clear_entry(entry)
        total_freed += freed
        if on_each:
            on_each(entry, freed)
    return total_freed


# --------------------------------------------------------------------------
# Untracked-folder audit — flags anything sitting next to a known cache
# that isn't itself tracked, e.g. a vendor adding a new cache folder name
# in a driver update. This is exactly how AMD's "DxcCache" (DirectX Shader
# Compiler cache — distinct from the older "DxCache") went unmanaged for a
# while: same parent folder, different name, silently skipped every run.
# Doesn't touch anything, just surfaces it.
# --------------------------------------------------------------------------
VENDOR_ROOTS = {
    "AMD": ["AMD"],
    "NVIDIA": ["NVIDIA", "NVIDIA App"],
    "INTEL": ["Intel"],
}


def find_untracked_siblings(entries: list) -> list:
    """Returns CacheEntry-like objects (vendor='UNKNOWN') for every
    subfolder of a known vendor root that isn't already one of `entries`."""
    local = Path(os.environ.get("LOCALAPPDATA", ""))
    known_paths = {e.path.resolve() for e in entries if e.vendor != "STEAM"}
    found = []
    for vendor, subdirs in VENDOR_ROOTS.items():
        for subdir in subdirs:
            root = local / subdir
            if not root.is_dir():
                continue
            try:
                children = [c for c in root.iterdir() if c.is_dir() or c.is_file()]
            except OSError:
                continue
            for child in children:
                if child.resolve() not in known_paths:
                    found.append(
                        CacheEntry(name=f"Untracked: {vendor}\\{subdir}\\{child.name}", path=child, vendor="UNKNOWN")
                    )
    return found


# --------------------------------------------------------------------------
# Lightweight file logging — one line per notable event, timestamped.
# Anchored to the same config_dir every other app-level file lives in
# (see the custom-Steam-paths note above for why that matters).
# --------------------------------------------------------------------------
LOG_FILE = Path(config_dir) / "ShaderCacheCleanup.log"


def log_event(message: str):
    from datetime import datetime

    line = f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n"
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError:
        pass


# --------------------------------------------------------------------------
# Misc helpers
# --------------------------------------------------------------------------
def is_admin() -> bool:
    if not (HAVE_WINREG and ctypes):
        return False
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin():
    """Re-launches this script elevated via UAC, and exits the current
    process. Caller is responsible for confirming with the user first."""
    import sys

    ctypes.windll.shell32.ShellExecuteW(None, "runas", sys.executable, " ".join(sys.argv), None, 1)
    sys.exit(0)


def human_size(num_bytes: int) -> str:
    if num_bytes >= 1024**3:
        return f"{num_bytes / 1024**3:.2f} GB"
    if num_bytes >= 1024**2:
        return f"{num_bytes / 1024**2:.1f} MB"
    if num_bytes >= 1024:
        return f"{num_bytes / 1024:.0f} KB"
    return f"{num_bytes} bytes"
