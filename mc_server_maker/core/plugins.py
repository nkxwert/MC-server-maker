"""Bedrock (phone / console / Windows 10) players on Java servers: Geyser + Floodgate.

Geyser translates the Bedrock protocol; Floodgate lets Bedrock players join an
online-mode server without a Java account. Both are Paper/Purpur plugins.
"""

import re
from pathlib import Path
from typing import List, Optional

from mc_server_maker.core import net
from mc_server_maker.core.tasks import Task
from mc_server_maker.i18n import t

GEYSER_API = "https://download.geysermc.org/v2/projects/{project}/versions/latest/builds/latest"
PROJECTS = ("geyser", "floodgate")
PLATFORM = "spigot"  # Paper and Purpur load Spigot plugins
DEFAULT_BEDROCK_PORT = 19132
PLUGIN_SOFTWARE = ("paper", "purpur")


def supports_bedrock(meta) -> bool:
    return meta.software in PLUGIN_SOFTWARE


def _plugins_dir(meta) -> Path:
    return meta.folder / "plugins"


def _jars(meta) -> List[Path]:
    d = _plugins_dir(meta)
    if not d.exists():
        return []
    return [p for p in d.glob("*.jar") if _is_ours(p.name)]


def _is_ours(name: str, project: str = "geyser|floodgate") -> bool:
    """Geyser/Floodgate's own jars only, not add-ons like GeyserSkinManager."""
    return bool(re.fullmatch(rf"({project})[-_ ]?(spigot|paper|bukkit)\b.*\.jar", name, re.IGNORECASE))


def bedrock_installed(meta) -> bool:
    names = [p.name.lower() for p in _jars(meta)]
    return any(n.startswith("geyser") for n in names)


def install_bedrock(meta, task: Optional[Task] = None) -> None:
    """Download (or update) Geyser and Floodgate into plugins/."""
    task = task or Task()
    if not supports_bedrock(meta):
        raise ValueError(t("Bedrock support needs Paper or Purpur."))
    plugins = _plugins_dir(meta)
    plugins.mkdir(exist_ok=True)
    for project in PROJECTS:
        url = GEYSER_API.format(project=project)
        info = net.get_json(url)
        dl = info["downloads"][PLATFORM]
        name = Path(str(dl.get("name") or "")).name  # never a path from the server's answer
        if not name.lower().endswith(".jar"):
            name = f"{project}-{PLATFORM}.jar"
        task.log(t("Installing {name} (build {build})...", name=project.capitalize(), build=info.get("build", "?")))
        # download first: if it fails, the working old version stays
        net.download(f"{url}/downloads/{PLATFORM}", plugins / name, task, sha256=dl.get("sha256"))
        for old in plugins.glob("*.jar"):  # then remove other versions of the same plugin
            if _is_ours(old.name, project) and old.name != name:
                try:
                    old.unlink()
                except OSError as e:  # locked while the server runs (Windows)
                    task.log(t("Couldn't remove the old {file}: {err}", file=old.name, err=e))


def remove_bedrock(meta) -> None:
    for p in _jars(meta):
        p.unlink(missing_ok=True)


def bedrock_port(meta) -> int:
    """Read the Bedrock port from Geyser's config (created on first start)."""
    cfg = _plugins_dir(meta) / "Geyser-Spigot" / "config.yml"
    try:
        text = cfg.read_text(encoding="utf-8")
    except OSError:
        return DEFAULT_BEDROCK_PORT
    m = re.search(r"^bedrock:\s*\n(?:[ \t]+.*\n)*?[ \t]+port:\s*(\d+)", text, re.MULTILINE)
    return int(m.group(1)) if m else DEFAULT_BEDROCK_PORT


def udp_ports(meta) -> List[int]:
    """UDP ports that need forwarding for this server."""
    return [bedrock_port(meta)] if bedrock_installed(meta) else []
