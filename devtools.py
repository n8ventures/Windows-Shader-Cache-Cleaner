#!/usr/bin/env python3
"""
devtools.py — N8's Media Sniffer build tool
----------------------------------------
Usage:
    python devtools.py          # build with auto-incremented count
    python devtools.py --dry    # preview version string, don't build
    python devtools.py --reset  # reset build counter to 0
    python devtools.py --dmg    # build DMG after building the app
"""

import subprocess
import sys
import os
import re
import json
import argparse
import shutil
from datetime import datetime
from pathlib import Path

from modules.platformModules import win


from __version__ import __version__ as __version__script, __author__, __appname__

is_dev_build = any(char.isalpha() for char in __version__script)

import platform

PLATFORM = platform.system()
ARCH = platform.machine().lower()

# ── Config ────────────────────────────────────────────────────────────────────

SPEC_FILE = "ShaderCacheCleaner.spec"
VERSION_FILE = Path("__version__.py")
BUILD_FILE = Path("build_count.json")  # readable by the GUI too
DIST_DIR = Path("dist")
ROOT_DIR = Path(".")
APP = __appname__
EXT = ".exe"


# ── Build Icons ───────────────────────────────────────────────────────────────────
def build_icons():
    from tools.icnsBuilder import pngtoicns, pngtoico

    if win:
        ICONS_DIR = "./assets/icons/win/"
        pngtoico(f"{ICONS_DIR}icon.png", ICONS_DIR)
        # pngtoico(f"{ICONS_DIR}icon-dev.png", ICONS_DIR)

        print("  ✓ Windows Icons built using tools/icnsBuilder.py - pngtoico")


# ── Build JSON ────────────────────────────────────────────────────────────────


def read_build_file() -> dict:
    if BUILD_FILE.exists():
        try:
            return json.loads(BUILD_FILE.read_text())
        except (json.JSONDecodeError, KeyError):
            pass
    return {"build_count": 0}


def write_build_file(data: dict):
    BUILD_FILE.write_text(json.dumps(data, indent=4))


def bump_build_count() -> int:
    data = read_build_file()
    data["build_count"] = data.get("build_count", 0) + 1
    write_build_file(data)
    return data["build_count"]


def save_build_info(count: int, base_version: str, label: str, now: datetime):
    """
    Writes the full build record to build_count.json.
    The GUI reads this file directly — no string parsing needed.
    """
    data = {
        "build_count": count,
        "build_label": label,
        "base_version": base_version,
        "date": now.strftime("%Y-%m-%d"),
        "time": now.strftime("%H:%M"),
    }
    write_build_file(data)


# ── Version helpers ───────────────────────────────────────────────────────────


def read_base_version() -> str:
    """Reads __version__ from __version__.py without importing it."""
    text = VERSION_FILE.read_text()
    match = re.search(r'^__version__\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    if not match:
        raise ValueError(f"Could not parse __version__ from {VERSION_FILE}")
    return match.group(1)


def make_build_label(base_version: str, count: int, now: datetime) -> str:
    """
    Produces a label like:  0.0.4a-B47.202606041423
    Format: {base_version}-B{count}.{YYYYMMDD}{HHMM}
    """
    date_part = now.strftime("%Y%m%d")
    time_part = now.strftime("%H%M")
    return f"{base_version}-B{count}.{date_part}{time_part}"


# ── Pre-build checks ──────────────────────────────────────────────────────────


def check_prerequisites():
    errors = []

    if not Path(SPEC_FILE).exists():
        errors.append(f"Spec file not found: {SPEC_FILE}")

    if not VERSION_FILE.exists():
        errors.append(f"Version file not found: {VERSION_FILE}")

    if shutil.which("pyinstaller") is None:
        errors.append("pyinstaller not found in PATH — is your venv active?")

    if errors:
        for e in errors:
            print(f"  ✗ {e}")
        sys.exit(1)


# ── Build ─────────────────────────────────────────────────────────────────────


def run_pyinstaller(build_label: str) -> int:
    env = os.environ.copy()
    env["BUILD_VERSION"] = build_label  # spec reads via os.environ.get()

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--clean",
        "--noconfirm",
        SPEC_FILE,
    ]

    print(f"\n  Running: {' '.join(cmd)}")
    print(f"  BUILD_VERSION = {build_label}\n")
    print("─" * 60)

    result = subprocess.run(cmd, env=env)
    return result.returncode


# ── Post-build ────────────────────────────────────────────────────────────────


def post_build_summary(build_label: str, count: int, success: bool, app_path: Path = None):
    app_path = Path(app_path).resolve()
    print("\n" + "─" * 60)

    if success:
        if app_path.is_dir():
            size_mb = sum(f.stat().st_size for f in app_path.rglob("*") if f.is_file()) / 1_048_576
        elif app_path.is_file():
            size_mb = app_path.stat().st_size / 1_048_576
        else:
            size_mb = 0

        print(f"  ✓ Build complete")
        print(f"    Label        : {build_label}")
        print(f"    Count        : {count}")
        print(f"    Platform     : {PLATFORM}")
        print(f"    Architecture : {ARCH}")
        print(f"    Output       : {app_path}")
        print(f"    Size         : {size_mb:.1f} MB")
    else:
        print(f"  ✗ Build FAILED  (label: {build_label})")
        print(f"    build_count.json was already updated — decrement manually if needed")


# ── Post-build signing ────────────────────────────────────────────────────────
def sign_executable(exe_path: Path):
    exe_path = Path(exe_path).resolve()
    script_directory = os.path.dirname(os.path.realpath(__file__))

    def cert_pass():
        while True:
            if win:
                response = input(f"Enter certificate password:")
            if response:
                return response
            else:
                print("No input. Please enter the password: ")

    # Sign the executable using signtool
    where_command = 'where /R "C:\\Program Files (x86)" signtool.*'
    where_result = subprocess.run(where_command, capture_output=True, shell=True)
    output_str = where_result.stdout.decode("utf-8")
    output_lines = output_str.split("\r\n")

    sdk_signtool = Path(r"C:\Program Files (x86)\Windows Kits\10\bin\10.0.19041.0\x64\signtool.exe")
    if sdk_signtool.is_file():
        signtool_exe = str(sdk_signtool)
    else:
        signtool_exe = output_lines[0].strip()

    # Construct the sign_command
    try:
        password = cert_pass()
        main_sign_command = f'"{signtool_exe}" sign /f "{script_directory}\\cert\\certificate.pfx" /p {password} /tr http://timestamp.digicert.com /td sha256 /v "{exe_path}"'
        print(f"Signing {exe_path}...")
        subprocess.run(main_sign_command, shell=True)
        print(f"{exe_path} signed!")

    except Exception as e:
        print("An error occurred while signing:", e)


# ── CLI ───────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(description="N8VENTURES build tool - Media Sniffer Edition.")
    parser.add_argument("--dry", action="store_true", help="Preview version, skip build")
    parser.add_argument("--reset", action="store_true", help="Reset build counter to 0")
    parser.add_argument("--count", type=int, help="Override build count (doesn't save)")
    args = parser.parse_args()

    build_icons()

    # ── Reset
    if args.reset:
        write_build_file({"build_count": 0})
        print(f"  ✓ Build counter reset to 0")
        return

    check_prerequisites()

    base_version = read_base_version()
    now = datetime.now()

    # ── Dry run
    if args.dry:
        next_count = read_build_file().get("build_count", 0) + 1
        label = make_build_label(base_version, next_count, now)
        print(f"\n  Dry run — next build would be:")
        print(f"    Base version : {base_version}")
        print(f"    Build count  : {next_count}")
        print(f"    Full label   : {label}")
        print(f"    Date / Time  : {now.strftime('%Y-%m-%d')} {now.strftime('%H:%M')}")
        print(f"\n  (build_count.json not modified)\n")
        return

    # ── Real build
    if args.count is not None:
        count = args.count
    else:
        count = bump_build_count()

    # If version is bumped, reset Build count.
    if base_version != read_build_file().get("base_version", ""):
        count = 1

    label = make_build_label(base_version, count, now)

    # Write the full record now — GUI can read this even from inside the app
    save_build_info(count, base_version, label, now)

    print(f"\n {APP} — {label}")
    print("─" * 60)
    if win:
        from tools.generateRC import genMainRC
        from __version__ import __version__

        genMainRC(__version__, APP)
        print(f"  ✓ .rc built!")

    returncode = run_pyinstaller(label)

    if returncode == 0:
        app_path = (DIST_DIR / f"{APP}{EXT}").resolve()

        renamed_app_path = (DIST_DIR / f"{APP.replace(" ", "").replace("'","") if win else APP}{EXT}").resolve()
        renamed_app_path.unlink(missing_ok=True)
        app_path.rename(renamed_app_path)
        sign_executable(renamed_app_path)

    post_build_summary(label, count, success=(returncode == 0), app_path=renamed_app_path)
    sys.exit(returncode)


if __name__ == "__main__":
    main()
