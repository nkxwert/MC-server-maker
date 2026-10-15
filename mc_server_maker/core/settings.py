"""App preferences (theme, language) saved in settings.json."""

import json
from dataclasses import asdict, dataclass

from mc_server_maker.core import paths


@dataclass
class AppSettings:
    theme: str = "dark"  # dark | light
    language: str = "en"  # en | ko
    low_resource: bool = True  # lower server priority, smaller memory footprint, quiet UI

    @property
    def path(self):
        return paths.BASE_DIR / "settings.json"

    @classmethod
    def load(cls) -> "AppSettings":
        s = cls()
        try:
            data = json.loads(s.path.read_text(encoding="utf-8"))
            for k in ("theme", "language"):
                if isinstance(data.get(k), str):
                    setattr(s, k, data[k])
            if isinstance(data.get("low_resource"), bool):
                s.low_resource = data["low_resource"]
        except (OSError, ValueError):
            pass
        return s

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(asdict(self), indent=2), encoding="utf-8")
