"""프로그램 데이터 경로."""

import os
from pathlib import Path

# 기본적으로 저장소(프로그램) 폴더 안에 servers/, runtime/ 을 만든다.
# MCSM_HOME 환경 변수로 위치를 바꿀 수 있다.
BASE_DIR = Path(os.environ.get("MCSM_HOME") or Path(__file__).resolve().parents[2])
SERVERS_DIR = BASE_DIR / "servers"
RUNTIME_DIR = BASE_DIR / "runtime"


def ensure_dirs() -> None:
    SERVERS_DIR.mkdir(parents=True, exist_ok=True)
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
