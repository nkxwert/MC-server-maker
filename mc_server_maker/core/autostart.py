"""Start Bartizan when Windows starts: a value in the current user's Run key (no administrator
prompt). The uninstaller removes it again."""

import os
import sys

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NAME = "Bartizan"
STARTUP_FLAG = "--startup"  # started by Windows: may start a server and stay in the tray
MINIMIZED_FLAG = "--minimized"


def supported() -> bool:
    """Only the built app: a Run entry pointing at python.exe + a script would break on any move."""
    return os.name == "nt" and bool(getattr(sys, "frozen", False))


def command(minimized: bool) -> str:
    return f'"{sys.executable}" {STARTUP_FLAG}' + (f" {MINIMIZED_FLAG}" if minimized else "")


def current() -> str:
    """The command Windows runs at sign-in, "" if none."""
    if os.name != "nt":
        return ""
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _kind = winreg.QueryValueEx(key, NAME)
            return str(value)
    except OSError:
        return ""


def enabled() -> bool:
    return bool(current())


def minimized() -> bool:
    return MINIMIZED_FLAG in current()


def set_enabled(on: bool, start_minimized: bool = False) -> None:
    """OSError when the registry can't be written."""
    if os.name != "nt":
        return
    import winreg

    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
        if on:
            winreg.SetValueEx(key, NAME, 0, winreg.REG_SZ, command(start_minimized))
        else:
            try:
                winreg.DeleteValue(key, NAME)
            except FileNotFoundError:
                pass


def refresh_path() -> None:
    """The app was moved or replaced (portable -> installed): point the entry at this copy."""
    if not supported():
        return
    cur = current()
    if cur and cur != command(MINIMIZED_FLAG in cur):
        try:
            set_enabled(True, MINIMIZED_FLAG in cur)
        except OSError:
            pass
