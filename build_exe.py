"""PyInstaller로 실행 파일 만들기.

    pip install -r requirements.txt pyinstaller
    python build_exe.py

결과: dist/MC-Server-Maker.exe (Windows) / dist/MC-Server-Maker (macOS, Linux)
"""

import os
import sys

import PyInstaller.__main__

NAME = "MC-Server-Maker"

# 쓰지 않는 Qt 모듈은 빼서 파일 크기를 줄인다
EXCLUDES = [
    "PySide6.QtNetwork", "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtDBus", "PySide6.QtConcurrent", "PySide6.QtXml",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPrintSupport",
    "tkinter", "unittest",
]

args = [
    "launcher.py",
    "--name", NAME,
    "--onefile",
    "--windowed",
    "--noconfirm",
    "--clean",
    "--icon", os.path.join("assets", "icon.ico"),
    "--add-data", f"assets{os.pathsep}assets",
    "--add-data", f"CHANGELOG.md{os.pathsep}.",  # shown as "What's new"
]
for mod in EXCLUDES:
    args += ["--exclude-module", mod]
if sys.platform == "win32":
    args += ["--version-file", "version_info.txt"] if os.path.exists("version_info.txt") else []

PyInstaller.__main__.run(args)
