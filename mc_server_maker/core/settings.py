"""App preferences (theme, language) saved in settings.json."""

import json
import os
from dataclasses import asdict, dataclass

from mc_server_maker.core import paths


def system_language() -> str:
    """'ko' on a Korean system, else 'en'."""
    try:
        if os.name == "nt":
            import ctypes

            return "ko" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x12 else "en"
        import locale

        lang = locale.getlocale()[0] or os.environ.get("LANG", "")
        return "ko" if lang.lower().startswith("ko") else "en"
    except (AttributeError, OSError, ValueError):
        return "en"


@dataclass
class AppSettings:
    theme: str = "dark"  # dark | light
    language: str = "en"  # en | ko
    low_resource: bool = True  # lower server priority, smaller memory footprint, quiet UI
    tunnel_address: str = ""  # last known playit.gg address
    tunnel_address_manual: bool = False  # typed by the user: the API's address doesn't replace it
    last_update_check: str = ""  # YYYY-MM-DD of the last automatic check
    notified_version: str = ""  # newest version we already told the user about
    last_run_version: str = ""  # to show "What's new" once after an update
    install_offered: bool = False  # the portable EXE asked once to move to the installed app
    notes_seen_version: str = ""  # newest version whose "What's new" was shown (never again, never older)
    autostart_server: str = ""  # server folder to start when Windows starts the app
    old_exes_checked: bool = False  # the installed app looked once for old downloaded Bartizan EXEs

    @property
    def path(self):
        return paths.BASE_DIR / "settings.json"

    @classmethod
    def load(cls) -> "AppSettings":
        s = cls()
        if not s.path.exists():  # first run: speak the system's language
            s.language = system_language()
        try:
            data = json.loads(s.path.read_text(encoding="utf-8"))
            for k, default in asdict(cls()).items():
                if isinstance(data.get(k), type(default)):
                    setattr(s, k, data[k])
        except (OSError, ValueError):
            pass
        return s

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + ".tmp")  # a crash mid-write keeps the old settings
        tmp.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
        os.replace(tmp, self.path)
