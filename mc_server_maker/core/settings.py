"""App preferences (theme, language) saved in settings.json."""

import json
import os
from dataclasses import asdict, dataclass

from mc_server_maker.core import paths


@dataclass
class AppSettings:
    theme: str = "dark"  # dark | light
    language: str = "en"  # en | ko
    low_resource: bool = True  # lower server priority, smaller memory footprint, quiet UI
    tunnel_address: str = ""  # last known playit.gg address
    last_update_check: str = ""  # YYYY-MM-DD of the last automatic check
    notified_version: str = ""  # newest version we already told the user about
    last_run_version: str = ""  # to show "What's new" once after an update

    @property
    def path(self):
        return paths.BASE_DIR / "settings.json"

    @classmethod
    def load(cls) -> "AppSettings":
        s = cls()
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
