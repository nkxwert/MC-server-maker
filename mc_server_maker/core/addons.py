"""Plugins (Paper/Purpur) and mods (Fabric/NeoForge/Forge): list, add, turn on/off, remove.

Turning one off renames `name.jar` to `name.jar.disabled`, which every loader ignores.
"""

import json
import re
import shutil
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple

from mc_server_maker.i18n import t

DISABLED_SUFFIX = ".disabled"

# software -> (folder, what it accepts)
FOLDERS = {
    "paper": ("plugins", {"plugin"}),
    "purpur": ("plugins", {"plugin"}),
    "fabric": ("mods", {"fabric"}),
    "forge": ("mods", {"forge"}),
    "neoforge": ("mods", {"neoforge", "forge"}),  # older NeoForge (1.20.1) still reads mods.toml
}
KIND_NAMES = {
    "plugin": "Bukkit/Paper plugin",
    "fabric": "Fabric mod",
    "quilt": "Quilt mod",
    "forge": "Forge mod",
    "neoforge": "NeoForge mod",
    "unknown": "Unknown",
}


@dataclass
class Addon:
    path: Path
    name: str
    version: str = ""
    authors: List[str] = field(default_factory=list)
    kind: str = "unknown"
    enabled: bool = True
    size: int = 0
    icon: str = ""  # picture inside the jar (mods name one), "" if none

    @property
    def file_name(self) -> str:
        return self.path.name[: -len(DISABLED_SUFFIX)] if not self.enabled else self.path.name


def kind_label(meta) -> str:
    """'Plugins', 'Mods' or '' (Vanilla)."""
    folder = FOLDERS.get(meta.software)
    if not folder:
        return ""
    return "Plugins" if folder[0] == "plugins" else "Mods"


def addon_dir(meta) -> Optional[Path]:
    folder = FOLDERS.get(meta.software)
    return meta.folder / folder[0] if folder else None


# ---------------------------------------------------------------- reading jars


def _yaml_value(text: str, key: str) -> str:
    m = re.search(rf"^{key}:\s*['\"]?([^'\"\n#]+?)['\"]?\s*(?:#.*)?$", text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _yaml_authors(text: str) -> List[str]:
    single = _yaml_value(text, "author")
    m = re.search(r"^authors:\s*\[(.*?)\]", text, re.MULTILINE)
    if m:
        return [a.strip(" '\"") for a in m.group(1).split(",") if a.strip(" '\"")]
    m = re.search(r"^authors:\s*\n((?:\s*-\s*.+\n?)+)", text, re.MULTILINE)
    if m:
        return [a.strip(" -'\"") for a in m.group(1).splitlines() if a.strip(" -'\"")]
    return [single] if single else []


def _toml_value(text: str, key: str) -> str:
    m = re.search(rf'^\s*{key}\s*=\s*"([^"]*)"', text, re.MULTILINE)
    return m.group(1).strip() if m else ""


def _manifest_version(z: zipfile.ZipFile) -> str:
    try:
        mf = z.read("META-INF/MANIFEST.MF").decode("utf-8", "replace")
    except KeyError:
        return ""
    m = re.search(r"^Implementation-Version:\s*(.+)$", mf, re.MULTILINE)
    return m.group(1).strip() if m else ""


def read_info(path: Path) -> Addon:
    path = Path(path)
    enabled = not path.name.endswith(DISABLED_SUFFIX)
    base = path.name[: -len(DISABLED_SUFFIX)] if not enabled else path.name
    info = Addon(path=path, name=base[:-4] if base.lower().endswith(".jar") else base, enabled=enabled)
    try:
        info.size = path.stat().st_size
        with zipfile.ZipFile(path) as z:
            names = set(z.namelist())
            if "fabric.mod.json" in names or "quilt.mod.json" in names:
                is_fabric = "fabric.mod.json" in names
                data = json.loads(z.read("fabric.mod.json" if is_fabric else "quilt.mod.json").decode("utf-8", "replace"))
                if not is_fabric:
                    ql = data.get("quilt_loader", {})
                    md = ql.get("metadata", {})
                    data = {"name": md.get("name"), "id": ql.get("id"), "version": ql.get("version", ""),
                            "authors": list(md.get("contributors", {}))}
                info.kind = "fabric" if is_fabric else "quilt"
                info.name = data.get("name") or data.get("id") or info.name
                info.version = str(data.get("version", ""))
                authors = data.get("authors") or data.get("contributors") or []
                if isinstance(authors, dict):
                    authors = list(authors)
                info.authors = [a["name"] if isinstance(a, dict) else str(a) for a in authors]
                icon = data.get("icon")
                if isinstance(icon, dict) and icon:  # sizes: take the biggest
                    icon = icon[max(icon, key=lambda k: int(k) if str(k).isdigit() else 0)]
                if isinstance(icon, str) and icon.lstrip("/") in names:
                    info.icon = icon.lstrip("/")
            elif "META-INF/neoforge.mods.toml" in names or "META-INF/mods.toml" in names:
                neo = "META-INF/neoforge.mods.toml" in names
                text = z.read("META-INF/neoforge.mods.toml" if neo else "META-INF/mods.toml").decode("utf-8", "replace")
                info.kind = "neoforge" if neo else "forge"
                info.name = _toml_value(text, "displayName") or _toml_value(text, "modId") or info.name
                version = _toml_value(text, "version")
                info.version = _manifest_version(z) if version.startswith("${") else version
                author = _toml_value(text, "authors")
                info.authors = [a.strip() for a in author.split(",") if a.strip()]
                logo = _toml_value(text, "logoFile").lstrip("/")
                if logo and logo in names:
                    info.icon = logo
            elif "plugin.yml" in names or "paper-plugin.yml" in names:
                text = z.read("paper-plugin.yml" if "paper-plugin.yml" in names else "plugin.yml").decode("utf-8", "replace")
                info.kind = "plugin"
                info.name = _yaml_value(text, "name") or info.name
                info.version = _yaml_value(text, "version")
                info.authors = _yaml_authors(text)
    except (OSError, zipfile.BadZipFile, ValueError, KeyError):
        pass
    return info


def icon_bytes(addon: Addon) -> bytes:
    """The picture inside the jar, b"" if it has none (plugins usually don't)."""
    if not addon.icon:
        return b""
    try:
        with zipfile.ZipFile(addon.path) as z:
            data = z.read(addon.icon)
        return data if len(data) < (2 << 20) else b""
    except (OSError, zipfile.BadZipFile, KeyError):
        return b""


# ------------------------------------------------------------------- manage


def list_addons(meta) -> List[Addon]:
    d = addon_dir(meta)
    if not d or not d.exists():
        return []
    files = [p for p in d.iterdir() if p.is_file() and (p.name.endswith(".jar") or p.name.endswith(".jar" + DISABLED_SUFFIX))]
    return sorted((read_info(p) for p in files), key=lambda a: a.name.lower())


def compatibility_warning(meta, addon: Addon) -> str:
    """'' if the jar fits this server, otherwise a short warning."""
    accepted = FOLDERS.get(meta.software, ("", set()))[1]
    if addon.kind in accepted:
        return ""
    if addon.kind == "unknown":
        return t("Not recognized as a plugin or mod.")
    return t("This is a {kind}; this server is {software}.", kind=t(KIND_NAMES[addon.kind]), software=meta.software_name)


def add_files(meta, files: List[Path]) -> List[Tuple[Addon, str]]:
    """Copy jars into the plugins/mods folder. Returns (addon, warning) per file.

    A jar with the same name (on or off) is replaced.
    """
    d = addon_dir(meta)
    if not d:
        raise ValueError(t("{software} doesn't support plugins or mods.", software=meta.software_name))
    d.mkdir(parents=True, exist_ok=True)
    results = []
    for src in files:
        src = Path(src)
        if not src.name.lower().endswith(".jar"):
            continue
        dest = d / src.name
        (d / (src.name + DISABLED_SUFFIX)).unlink(missing_ok=True)
        if src.resolve() != dest.resolve():
            shutil.copy2(src, dest)
        addon = read_info(dest)
        results.append((addon, compatibility_warning(meta, addon)))
    return results


def set_enabled(addon: Addon, enabled: bool) -> Addon:
    if addon.enabled == enabled:
        return addon
    p = addon.path
    target = p.with_name(p.name[: -len(DISABLED_SUFFIX)]) if enabled else p.with_name(p.name + DISABLED_SUFFIX)
    target.unlink(missing_ok=True)
    p.rename(target)
    addon.path, addon.enabled = target, enabled
    return addon


def remove(addon: Addon) -> None:
    addon.path.unlink(missing_ok=True)
