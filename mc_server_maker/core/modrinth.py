"""Find, install and update plugins/mods from Modrinth (https://modrinth.com).

Only versions made for this server's software and Minecraft version are offered.
Installed jars are recognized by their SHA-1 hash, so files added by hand that came
from Modrinth are recognized too.
"""

import hashlib
import json
import re
import urllib.parse
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from mc_server_maker.core import addons, net
from mc_server_maker.core.tasks import Task
from mc_server_maker.i18n import t

API = "https://api.modrinth.com/v2"
SITE = "https://modrinth.com"
PAGE_SIZE = 20

# server software -> Modrinth loaders that run on it (best first)
LOADERS = {
    "paper": ["paper", "spigot", "bukkit"],
    "purpur": ["purpur", "paper", "spigot", "bukkit"],
    "fabric": ["fabric"],
    "forge": ["forge"],
    "neoforge": ["neoforge"],
}
SORTS = (("relevance", "Relevance"), ("downloads", "Most downloads"), ("updated", "Recently updated"))


class ModrinthError(Exception):
    pass


@dataclass
class Hit:
    id: str
    slug: str
    title: str
    description: str
    author: str
    downloads: int
    icon_url: str
    client_side: str
    server_side: str

    @property
    def page_url(self) -> str:
        return f"{SITE}/project/{self.slug or self.id}"


@dataclass
class Update:
    path: Path  # the installed jar (may end in .disabled)
    title: str
    old_version: str
    new: dict  # Modrinth version object


def supported(meta) -> bool:
    return meta.software in LOADERS


def is_mods(meta) -> bool:
    return addons.kind_label(meta) == "Mods"


def _url(path: str, **params) -> str:
    query = {k: (json.dumps(v) if isinstance(v, (list, dict)) else v) for k, v in params.items() if v is not None}
    return API + path + ("?" + urllib.parse.urlencode(query) if query else "")


def _get(path: str, **params):
    try:
        return net.get_json(_url(path, **params))
    except net.NetError as e:
        raise ModrinthError(t("Couldn't reach Modrinth: {err}", err=e)) from e


def _post(path: str, payload):
    try:
        return net.post_json(_url(path), payload)
    except net.NetError as e:
        raise ModrinthError(t("Couldn't reach Modrinth: {err}", err=e)) from e


# ------------------------------------------------------------------ search


def search(meta, query: str = "", sort: str = "relevance", offset: int = 0) -> Tuple[List[Hit], int]:
    """One page of results that run on this server. Returns (hits, total)."""
    loaders = LOADERS[meta.software]
    facets = [[f"categories:{name}" for name in loaders], [f"versions:{meta.mc_version}"]]
    if is_mods(meta):
        facets.insert(0, ["project_type:mod"])  # not modpacks, which share loader tags
    data = _get("/search", query=query.strip() or None, facets=facets, index=sort,
                offset=offset, limit=PAGE_SIZE)
    hits = []
    for h in data.get("hits", []):
        if h.get("server_side") == "unsupported":
            continue  # client-only (minimaps, shaders...): does nothing on a server
        hits.append(Hit(
            id=h.get("project_id", ""), slug=h.get("slug", ""), title=h.get("title") or h.get("slug", "?"),
            description=h.get("description", ""), author=h.get("author", ""),
            downloads=int(h.get("downloads") or 0), icon_url=h.get("icon_url") or "",
            client_side=h.get("client_side", ""), server_side=h.get("server_side", ""),
        ))
    return hits, int(data.get("total_hits", len(hits)))


# ----------------------------------------------------------------- install


def best_version(meta, project_id: str) -> Optional[dict]:
    """Newest version for this server's loader + Minecraft version (releases first)."""
    versions = _get(f"/project/{project_id}/version", loaders=LOADERS[meta.software],
                    game_versions=[meta.mc_version])
    if not versions:
        return None
    releases = [v for v in versions if v.get("version_type") == "release"]
    return (releases or versions)[0]


def primary_file(version: dict) -> dict:
    files = [f for f in version.get("files", []) if str(f.get("filename", "")).lower().endswith(".jar")]
    if not files:
        raise ModrinthError(t("This version has no .jar file."))
    return next((f for f in files if f.get("primary")), files[0])


def _safe_name(name: str) -> str:
    name = Path(str(name).replace("\\", "/")).name  # never let the server pick a folder
    name = re.sub(r'[<>:"|?*\x00-\x1f]', "_", name)
    if not name.lower().endswith(".jar") or name in (".jar",):
        raise ModrinthError(t("This version has no .jar file."))
    return name


def sha1_of(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _jars(meta) -> List[Path]:
    d = addons.addon_dir(meta)
    if not d or not d.exists():
        return []
    return [p for p in d.iterdir() if p.is_file()
            and (p.name.endswith(".jar") or p.name.endswith(".jar" + addons.DISABLED_SUFFIX))]


def installed(meta) -> Dict[str, Path]:
    """Modrinth project id -> installed jar, for jars Modrinth knows."""
    by_hash = {sha1_of(p): p for p in _jars(meta)}
    if not by_hash:
        return {}
    found = _post("/version_files", {"hashes": list(by_hash), "algorithm": "sha1"})
    return {v["project_id"]: by_hash[h] for h, v in (found or {}).items() if h in by_hash and v.get("project_id")}


def _write_version(meta, version: dict, task: Task, replace: Optional[Path] = None) -> Path:
    f = primary_file(version)
    name = _safe_name(f["filename"])
    folder = addons.addon_dir(meta)
    folder.mkdir(parents=True, exist_ok=True)
    keep_off = bool(replace) and replace.name.endswith(addons.DISABLED_SUFFIX)
    dest = folder / name
    hashes = f.get("hashes") or {}
    in_use = t("{file} is in use by the running server. Stop the server, then try again.",
               file=(replace or dest).name)
    # A running server keeps its jars open on Windows. Move the old jar aside first: if that
    # fails nothing has changed yet (no duplicate old + new jar left behind).
    parked = None
    if replace and replace.exists():
        parked = replace.with_name(replace.name + ".bartizan-old")
        try:
            replace.rename(parked)
        except OSError as e:
            raise ModrinthError(in_use) from e
    try:
        net.download(f["url"], dest, task, sha512=hashes.get("sha512"), sha1=hashes.get("sha1"))
    except BaseException as e:
        if parked:
            parked.rename(replace)  # put the old version back
        if isinstance(e, OSError) and not isinstance(e, net.NetError):
            raise ModrinthError(in_use) from e
        raise
    if parked:
        parked.unlink(missing_ok=True)
    (folder / (name + addons.DISABLED_SUFFIX)).unlink(missing_ok=True)
    if keep_off:  # an update keeps a turned-off plugin off
        off = dest.with_name(dest.name + addons.DISABLED_SUFFIX)
        dest.rename(off)
        dest = off
    return dest


def install(meta, project_id: str, task: Optional[Task] = None) -> List[str]:
    """Install the best version of a project plus its required dependencies.

    Returns the installed file names. A project that is already installed is replaced
    by the new version (its old jar is removed).
    """
    task = task or Task()
    if not supported(meta):
        raise ModrinthError(t("{software} doesn't support plugins or mods.", software=meta.software_name))
    have = installed(meta)
    done: List[str] = []
    seen: Set[str] = set()

    def add(pid: str, version: Optional[dict], is_dependency: bool):
        if pid in seen:
            return
        seen.add(pid)
        if is_dependency and pid in have:
            return  # already there; leave the user's version alone
        version = version or best_version(meta, pid)
        if not version:
            if is_dependency:
                task.log(t("A required add-on has no version for this server; it may not work."))
                return
            raise ModrinthError(t("There's no version of this for {software} {v}.",
                                  software=meta.software_name, v=meta.mc_version))
        for dep in version.get("dependencies") or []:
            if dep.get("dependency_type") != "required":
                continue
            dep_pid, dep_version = dep.get("project_id"), None
            if dep.get("version_id"):
                dep_version = _get(f"/version/{dep['version_id']}")
                dep_pid = dep_pid or dep_version.get("project_id")
            if dep_pid:
                task.log(t("Also installing a required add-on..."))
                add(dep_pid, dep_version, True)
        task.check()
        path = _write_version(meta, version, task, replace=have.get(pid))
        have[pid] = path
        done.append(path.name)

    add(project_id, None, False)
    return done


# ----------------------------------------------------------------- updates


def check_updates(meta) -> Tuple[List[Update], int]:
    """Updates for installed jars from Modrinth. Returns (updates, jars not from Modrinth)."""
    jars = _jars(meta)
    by_hash = {sha1_of(p): p for p in jars}
    if not by_hash:
        return [], 0
    current = _post("/version_files", {"hashes": list(by_hash), "algorithm": "sha1"}) or {}
    latest = _post("/version_files/update", {
        "hashes": [h for h in by_hash if h in current], "algorithm": "sha1",
        "loaders": LOADERS[meta.software], "game_versions": [meta.mc_version],
    }) if current else {}
    updates = []
    for h, new in (latest or {}).items():
        old = current.get(h)
        if not old or not new or new.get("id") == old.get("id") or h not in by_hash:
            continue
        info = addons.read_info(by_hash[h])
        updates.append(Update(by_hash[h], info.name, old.get("version_number", ""), new))
    unknown = len(by_hash) - len(current)
    return sorted(updates, key=lambda u: u.title.lower()), unknown


def apply_update(meta, update: Update, task: Optional[Task] = None) -> Path:
    return _write_version(meta, update.new, task or Task(), replace=update.path)
