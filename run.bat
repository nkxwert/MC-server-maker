@echo off
rem Bartizan 실행 (Windows)
chcp 65001 >nul
cd /d "%~dp0"
if not exist .venv (
  echo 처음 실행: 필요한 파일을 설치합니다...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if errorlevel 1 (
    echo Python 3.10 이상을 설치해 주세요: https://www.python.org/downloads/
    pause
    exit /b 1
  )
)
.venv\Scripts\python -m pip install -q --disable-pip-version-check -r requirements.txt
if errorlevel 1 (
  pause
  exit /b 1
)
start "" .venv\Scripts\pythonw -m mc_server_maker
