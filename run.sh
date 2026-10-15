#!/usr/bin/env sh
# MC Server Maker 실행 (macOS / Linux)
cd "$(dirname "$0")" || exit 1
if [ ! -d .venv ]; then
  echo "처음 실행: 필요한 파일을 설치합니다..."
  python3 -m venv .venv || { echo "Python 3.10 이상을 설치해 주세요: https://www.python.org/downloads/"; exit 1; }
fi
.venv/bin/python -m pip install -q --disable-pip-version-check -r requirements.txt || exit 1
exec .venv/bin/python -m mc_server_maker
