"""Build the Windows app with PyInstaller.

    pip install -r requirements.txt pyinstaller
    python build_exe.py            # dist/Bartizan/ (folder; packed into Bartizan-Setup.exe by Inno Setup)
    python build_exe.py --onefile  # dist/Bartizan.exe (single portable file)

The folder build is what the installer ships: it starts without unpacking itself to a temp
folder first, which antivirus programs (e.g. V3) often flag in single-file builds. Both builds
carry Windows file details (product name, version, publisher) from version_info().
"""

import os
import sys
from pathlib import Path

import PyInstaller.__main__

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from mc_server_maker import APP_NAME, APP_VERSION  # noqa: E402

NAME = "Bartizan"

# Qt parts the app doesn't use are left out to keep it small.
EXCLUDES = [
    # (QtNetwork stays: QLocalServer keeps the app to a single running copy)
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets",
    "PySide6.QtPdf", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtOpenGL",
    "PySide6.QtOpenGLWidgets", "PySide6.QtDBus", "PySide6.QtConcurrent", "PySide6.QtXml",
    "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtPrintSupport",
    "tkinter", "unittest",
]


def version_info() -> str:
    """A Windows version resource: shown in the file's Properties → Details."""
    nums = [int(x) for x in APP_VERSION.split(".")[:3]] + [0]
    while len(nums) < 4:
        nums.append(0)
    v = tuple(nums[:4])
    strings = {
        "CompanyName": "Bartizan",
        "FileDescription": f"{APP_NAME} - Minecraft server maker",
        "FileVersion": APP_VERSION,
        "InternalName": NAME,
        "LegalCopyright": "Copyright (c) Bartizan contributors",
        "OriginalFilename": f"{NAME}.exe",
        "ProductName": APP_NAME,
        "ProductVersion": APP_VERSION,
    }
    entries = ",\n".join(f"          StringStruct({k!r}, {val!r})" for k, val in strings.items())
    return f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={v}, prodvers={v}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([
      StringTable('040904B0', [
{entries}
      ])
    ]),
    VarFileInfo([VarStruct('Translation', [0x0409, 1200])])
  ]
)
"""


def main() -> None:
    onefile = "--onefile" in sys.argv[1:]
    vi = ROOT / "build" / "version_info.txt"
    vi.parent.mkdir(parents=True, exist_ok=True)
    vi.write_text(version_info(), encoding="utf-8")
    args = [
        str(ROOT / "launcher.py"),
        "--name", NAME,
        "--onefile" if onefile else "--onedir",
        "--windowed",
        "--noconfirm",
        "--clean",
        "--noupx",  # packed files look suspicious to antivirus programs
        "--icon", str(ROOT / "assets" / "icon.ico"),
        "--add-data", f"{ROOT / 'assets'}{os.pathsep}assets",
        "--add-data", f"{ROOT / 'CHANGELOG.md'}{os.pathsep}.",  # shown as "What's new"
    ]
    for mod in EXCLUDES:
        args += ["--exclude-module", mod]
    if sys.platform == "win32":
        args += ["--version-file", str(vi)]
    PyInstaller.__main__.run(args)


if __name__ == "__main__":
    main()
