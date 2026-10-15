"""프로그램 데이터 경로."""

import os
import sys
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)  # PyInstaller로 만든 EXE에서 실행 중인지

if FROZEN:
    # EXE 옆에 servers/, runtime/ 을 만든다
    _DEFAULT_BASE = Path(sys.executable).resolve().parent
    _RESOURCE_BASE = Path(getattr(sys, "_MEIPASS", _DEFAULT_BASE))
else:
    # 저장소(프로그램) 폴더 안에 만든다
    _DEFAULT_BASE = Path(__file__).resolve().parents[2]
    _RESOURCE_BASE = _DEFAULT_BASE

# MCSM_HOME 환경 변수로 위치를 바꿀 수 있다.
BASE_DIR = Path(os.environ.get("MCSM_HOME") or _DEFAULT_BASE)
SERVERS_DIR = BASE_DIR / "servers"
RUNTIME_DIR = BASE_DIR / "runtime"


def ensure_dirs() -> None:
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)


def resource(name: str) -> Path:
    """assets 폴더의 파일 (EXE 안에 포함된 파일 포함)."""
    return _RESOURCE_BASE / "assets" / name
