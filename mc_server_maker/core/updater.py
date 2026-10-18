"""App self-update from GitHub Releases, and changelog parsing.

Releases are created by the build workflow whenever APP_VERSION changes. Each release
has the EXE, its .sha256 file, and notes with an English and a Korean part:

    <!-- lang:en -->
    - ...
    <!-- lang:ko -->
    - ...
"""

import hashlib
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from mc_server_maker import APP_VERSION
from mc_server_maker.core import net, paths
from mc_server_maker.core.tasks import Task
from mc_server_maker.i18n import t

REPO = "nkxwert/MC-server-maker"
RELEASES_API = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
RELEASES_PAGE = f"https://github.com/{REPO}/releases"
EXE_NAME = "Bartizan.exe"
SETUP_NAME = "Bartizan-Setup.exe"


class UpdateError(Exception):
    pass


def parse_version(v: str) -> Tuple[int, ...]:
    nums = re.findall(r"\d+", v or "")
    return tuple(int(n) for n in nums[:3]) if nums else (0,)


# ----------------------------------------------------------------- changelog


def parse_changelog(text: str) -> Dict[str, Dict[str, str]]:
    """{'1.6.0': {'en': '- ...', 'ko': '- ...'}, ...} from CHANGELOG.md."""
    out: Dict[str, Dict[str, str]] = {}
    version = lang = None
    for line in text.splitlines():
        m = re.match(r"^##\s+v?(\d+(?:\.\d+)*)\s*$", line)
        if m:
            version, lang = m.group(1), None
            out[version] = {}
            continue
        m = re.match(r"^###\s+(\w+)\s*$", line)
        if m and version:
            lang = m.group(1).lower()
            out[version][lang] = ""
            continue
        if version and lang:
            out[version][lang] += line + "\n"
    return {v: {k: s.strip() for k, s in langs.items()} for v, langs in out.items()}


def release_body(changelog: str, version: str) -> str:
    """Release notes for one version (both languages, marked so the app can pick one)."""
    langs = parse_changelog(changelog).get(version)
    if not langs:
        raise UpdateError(f"CHANGELOG.md has no section for {version}")
    return "\n\n".join(f"<!-- lang:{k} -->\n{v}" for k, v in langs.items())


def notes_for_language(body: str, lang: str) -> str:
    """Pick one language from release notes (falls back to English, then the whole text)."""
    parts = re.split(r"<!--\s*lang:(\w+)\s*-->", body or "")
    if len(parts) < 3:
        return (body or "").strip()
    by_lang = {parts[i].lower(): parts[i + 1].strip() for i in range(1, len(parts) - 1, 2)}
    return by_lang.get(lang) or by_lang.get("en") or (body or "").strip()


def bundled_notes(version: str, lang: str) -> str:
    """Notes for a version from the CHANGELOG.md shipped with the app."""
    try:
        text = paths.resource_root().joinpath("CHANGELOG.md").read_text(encoding="utf-8")
    except OSError:
        return ""
    langs = parse_changelog(text).get(version, {})
    return langs.get(lang) or langs.get("en", "")


# -------------------------------------------------------------------- check


@dataclass
class UpdateInfo:
    version: str
    exe_url: str
    sha256_url: str = ""
    page_url: str = RELEASES_PAGE
    setup_url: str = ""  # Bartizan-Setup.exe (installed app); exe_url is the portable single file
    setup_sha256_url: str = ""
    notes: List[Tuple[str, str]] = field(default_factory=list)  # (version, body), newest first

    def notes_text(self, lang: str) -> str:
        return "\n\n".join(f"### v{v}\n{notes_for_language(body, lang)}" for v, body in self.notes)


def check(current: str = APP_VERSION) -> Optional[UpdateInfo]:
    """Newest release if it is newer than `current`, else None (current="0": the newest release)."""
    releases = [r for r in net.get_json(RELEASES_API) if not r.get("draft") and not r.get("prerelease")]
    newer = [r for r in releases if parse_version(r.get("tag_name", "")) > parse_version(current)]
    if not newer:
        return None
    newer.sort(key=lambda r: parse_version(r["tag_name"]), reverse=True)
    latest = newer[0]
    assets = {a["name"]: a["browser_download_url"] for a in latest.get("assets", [])}
    exe = assets.get(EXE_NAME) or next((u for n, u in assets.items() if n.lower().endswith(".exe")), "")
    return UpdateInfo(
        version=latest["tag_name"].lstrip("v"),
        exe_url=exe,
        sha256_url=assets.get(EXE_NAME + ".sha256", ""),
        setup_url=assets.get(SETUP_NAME, ""),
        setup_sha256_url=assets.get(SETUP_NAME + ".sha256", ""),
        page_url=latest.get("html_url", RELEASES_PAGE),
        notes=[(r["tag_name"].lstrip("v"), r.get("body") or "") for r in newer],
    )


# --------------------------------------------------------------- download / swap


def can_self_update() -> bool:
    """Only the Windows EXE can replace itself; source installs use git."""
    return paths.FROZEN and os.name == "nt"


def is_installed() -> bool:
    """Running from the installed app (Bartizan-Setup.exe put an uninstaller next to it),
    not from the portable single-file EXE."""
    return paths.FROZEN and any(Path(sys.executable).parent.glob("unins*.exe"))


def _expected_sha256(url: str) -> Optional[str]:
    if not url:
        return None
    parts = net.get_text(url).split()
    expected = parts[0].strip().lower() if parts else ""
    if not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UpdateError(t("The update's checksum file is broken. Please try again later."))
    return expected


def download(info: UpdateInfo, task: Optional[Task] = None) -> Path:
    """Download the update into a temp folder: the installer when the release has one (the
    installed app updates through it, and a portable EXE moves to it), else the portable EXE."""
    task = task or Task()
    use_setup = bool(info.setup_url) and os.name == "nt"
    url = info.setup_url if use_setup else info.exe_url
    if not url:
        raise UpdateError(t("This release has no EXE to download."))
    expected = _expected_sha256(info.setup_sha256_url if use_setup else info.sha256_url)
    dest = update_dir() / (SETUP_NAME if use_setup else EXE_NAME)  # not next to the app
    dest.parent.mkdir(parents=True, exist_ok=True)
    net.download(url, dest, task, sha256=expected)
    if dest.stat().st_size < 1_000_000:
        dest.unlink(missing_ok=True)
        raise UpdateError(t("The downloaded file looks broken. Please try again."))
    return dest


INSTALL_ARG = "--bartizan-install"


def update_dir() -> Path:
    import tempfile

    return Path(tempfile.gettempdir()) / "Bartizan-update"


def install_and_restart(new_exe: Path) -> None:
    """Start the downloaded update; the caller quits right after.

    Bartizan-Setup.exe runs silently, replaces the installed app and starts it again (moving a
    portable EXE to the installed app on the way: /OLDEXE removes the old file).

    The portable EXE (older releases or no installer):

    A running EXE can't be overwritten on Windows. So the new version (in a temp folder)
    waits until this one has closed, copies itself over Bartizan.exe and starts it:
    the app stays one EXE, with no .new/.old files next to it.
    """
    exe = Path(sys.executable)
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    # a fresh start for the new EXE: otherwise PyInstaller's onefile bootloader thinks it is a child
    # of this process and reuses our temp folder, which is deleted when we quit
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1")
    if new_exe.name == SETUP_NAME:
        args = [str(new_exe), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"]
        if not is_installed():
            args.append(f"/OLDEXE={exe}")  # the portable EXE that the installed app replaces
        subprocess.Popen(args, cwd=str(new_exe.parent), creationflags=flags, close_fds=True, env=env)
        return
    subprocess.Popen([str(new_exe), INSTALL_ARG, str(exe), str(os.getpid())],
                     cwd=str(new_exe.parent), creationflags=flags, close_fds=True, env=env)


def _wait_for_exit(pid: int, timeout: float) -> None:
    try:
        import psutil

        psutil.Process(pid).wait(timeout=timeout)
    except Exception:  # noqa: BLE001 - already gone, or psutil can't tell: the copy loop retries anyway
        pass


def run_installer(argv: List[str]) -> bool:
    """When started as "<new exe> --bartizan-install <target> <pid>": replace the target EXE with
    this one, start it, and return True (the caller exits). Otherwise return False."""
    if len(argv) < 4 or argv[1] != INSTALL_ARG:
        return False
    import shutil
    import time

    target, pid = Path(argv[2]), int(argv[3]) if argv[3].isdigit() else 0
    if pid:
        _wait_for_exit(pid, 60)
    me = Path(sys.executable)
    copied = False
    for _ in range(60):  # the old EXE can stay locked a moment (antivirus, the closing process)
        try:
            tmp = target.with_name(target.name + ".tmp")
            shutil.copyfile(me, tmp)
            os.replace(tmp, target)
            copied = True
            break
        except OSError:
            time.sleep(0.5)
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1", BARTIZAN_RESTART="1")
    if not copied:
        env["BARTIZAN_UPDATE_FAILED"] = "1"  # the old version starts and says so
    try:
        subprocess.Popen([str(target)], cwd=str(target.parent), creationflags=flags, close_fds=True, env=env)
    except OSError:
        pass
    return True


def cleanup_old() -> None:
    """Remove what an update left behind: the downloaded installer (and .old files from
    versions before 1.20, which renamed the running EXE)."""
    if paths.FROZEN:
        exe = Path(sys.executable)
        for leftover in (exe.with_name(exe.name + ".old"), exe.with_name(exe.name + ".tmp")):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                pass  # still locked (old process closing, antivirus scan): try again next start
    import shutil

    shutil.rmtree(update_dir(), ignore_errors=True)


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
