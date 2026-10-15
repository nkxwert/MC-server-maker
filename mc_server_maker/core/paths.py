"""Data locations."""

import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)  # running from a PyInstaller EXE

if FROZEN:
    # keep servers/ and runtime/ next to the EXE
    _DEFAULT_BASE = Path(sys.executable).resolve().parent
    _RESOURCE_BASE = Path(getattr(sys, "_MEIPASS", _DEFAULT_BASE))
else:
    # keep them inside the project folder
    _DEFAULT_BASE = Path(__file__).resolve().parents[2]
    _RESOURCE_BASE = _DEFAULT_BASE

# Override with the MCSM_HOME environment variable.
BASE_DIR = Path(os.environ.get("MCSM_HOME") or _DEFAULT_BASE)
SERVERS_DIR = BASE_DIR / "servers"
RUNTIME_DIR = BASE_DIR / "runtime"


def ensure_dirs() -> None:
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def resource(name: str) -> Path:
    """A file from assets/ (also inside the EXE)."""
    return _RESOURCE_BASE / "assets" / name
