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
    notes: List[Tuple[str, str]] = field(default_factory=list)  # (version, body), newest first

    def notes_text(self, lang: str) -> str:
        return "\n\n".join(f"### v{v}\n{notes_for_language(body, lang)}" for v, body in self.notes)


def check(current: str = APP_VERSION) -> Optional[UpdateInfo]:
    """Newest release if it is newer than `current`, else None."""
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
        page_url=latest.get("html_url", RELEASES_PAGE),
        notes=[(r["tag_name"].lstrip("v"), r.get("body") or "") for r in newer],
    )


# --------------------------------------------------------------- download / swap


def can_self_update() -> bool:
    """Only the Windows EXE can replace itself; source installs use git."""
    return paths.FROZEN and os.name == "nt"


def download(info: UpdateInfo, task: Optional[Task] = None) -> Path:
    task = task or Task()
    if not info.exe_url:
        raise UpdateError(t("This release has no EXE to download."))
    expected = None
    if info.sha256_url:
        expected = net.get_text(info.sha256_url).split()[0].strip().lower()
    dest = Path(sys.executable).with_name(EXE_NAME + ".new")
    net.download(info.exe_url, dest, task, sha256=expected)
    if dest.stat().st_size < 1_000_000:
        dest.unlink(missing_ok=True)
        raise UpdateError(t("The downloaded file looks broken. Please try again."))
    return dest


def install_and_restart(new_exe: Path) -> None:
    """Swap the running EXE for the new one and start it. The caller quits right after.

    A running EXE can't be overwritten on Windows, but it can be renamed: rename it
    to .old, move the new one in, start it. The .old file is removed on next start.
    """
    exe = Path(sys.executable)
    old = exe.with_name(exe.name + ".old")
    old.unlink(missing_ok=True)
    os.replace(exe, old)
    try:
        os.replace(new_exe, exe)
    except OSError:
        os.replace(old, exe)  # put the original back
        raise
    flags = 0x00000008 | 0x00000200 if os.name == "nt" else 0  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    # a fresh start for the new EXE: otherwise PyInstaller's onefile bootloader thinks it is a child
    # of this process and reuses our temp folder, which is deleted when we quit
    env = dict(os.environ, PYINSTALLER_RESET_ENVIRONMENT="1", BARTIZAN_RESTART="1")
    subprocess.Popen([str(exe)], cwd=str(exe.parent), creationflags=flags, close_fds=True, env=env)


def cleanup_old() -> None:
    """Remove the previous EXE left behind by an update."""
    if paths.FROZEN:
        try:
            Path(sys.executable).with_name(Path(sys.executable).name + ".old").unlink(missing_ok=True)
        except OSError:
            pass  # still locked (old process closing, antivirus scan): try again next start


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
