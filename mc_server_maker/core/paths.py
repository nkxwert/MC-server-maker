"""Data locations.

Everything lives in Documents/MC-Server-Maker-Files:
    servers/<server>/   one folder per server (its files + server-maker.json settings)
    runtime/            Java installed by the app
    settings.json       app settings
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List

FROZEN = getattr(sys, "frozen", False)  # running from a PyInstaller EXE
DATA_FOLDER_NAME = "MC-Server-Maker-Files"

if FROZEN:
    _APP_DIR = Path(sys.executable).resolve().parent
    _RESOURCE_BASE = Path(getattr(sys, "_MEIPASS", _APP_DIR))
else:
    _APP_DIR = Path(__file__).resolve().parents[2]
    _RESOURCE_BASE = _APP_DIR


def documents_dir() -> Path:
    """The user's Documents folder (follows OneDrive / localized folder names)."""
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes

            buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
            # CSIDL_PERSONAL = 5 (Documents), SHGFP_TYPE_CURRENT = 0
            if ctypes.windll.shell32.SHGetFolderPathW(None, 5, None, 0, buf) == 0 and buf.value:
                return Path(buf.value)
        except (AttributeError, OSError):
            pass
    elif sys.platform.startswith("linux"):
        try:
            out = subprocess.run(["xdg-user-dir", "DOCUMENTS"], capture_output=True, text=True, timeout=5)
            p = Path(out.stdout.strip())
            if out.returncode == 0 and p.is_dir() and p != Path.home():
                return p
        except (OSError, subprocess.TimeoutExpired):
            pass
    return Path.home() / "Documents"


# Override with the MCSM_HOME environment variable.
BASE_DIR = Path(os.environ.get("MCSM_HOME") or documents_dir() / DATA_FOLDER_NAME)
SERVERS_DIR = BASE_DIR / "servers"
RUNTIME_DIR = BASE_DIR / "runtime"

_LEGACY_ITEMS = ("servers", "runtime", "settings.json")


def ensure_dirs() -> None:
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def migrate_legacy_data(old_base: Path = None) -> List[str]:
    """Move data that older versions kept next to the EXE (e.g. on the Desktop).

    Only moves an item when the new location doesn't have it yet. Returns what was moved.
    """
    old_base = Path(old_base or _APP_DIR)
    if os.environ.get("MCSM_HOME") or old_base.resolve() == BASE_DIR.resolve():
        return []
    moved = []
    for name in _LEGACY_ITEMS:
        src, dst = old_base / name, BASE_DIR / name
        if not src.exists():
            continue
        if src.is_dir() and not any(src.iterdir()):
            src.rmdir()  # empty leftover folder
            continue
        if dst.exists() and not (dst.is_dir() and not any(dst.iterdir())):
            continue
        BASE_DIR.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            dst.rmdir()
        shutil.move(str(src), str(dst))
        moved.append(name)
    return moved


def resource_root() -> Path:
    """Folder with files shipped with the app (project root, or the unpacked EXE)."""
    return _RESOURCE_BASE


def resource(name: str) -> Path:
    """A file from assets/ (also inside the EXE)."""
    return _RESOURCE_BASE / "assets" / name
