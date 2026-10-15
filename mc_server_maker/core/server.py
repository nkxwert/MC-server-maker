"""Create / upgrade servers, manage worlds and backups."""

import json
import re
import shutil
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional

from mc_server_maker.core import java as javamod
from mc_server_maker.core import paths, versions
from mc_server_maker.core.properties import Properties
from mc_server_maker.core.providers import get_provider
from mc_server_maker.core.tasks import Task
from mc_server_maker.i18n import t

META_FILE = "server-maker.json"
BACKUP_DIR = "backups"
# Excluded from backups (large and re-downloadable)
BACKUP_EXCLUDE = {BACKUP_DIR, "libraries", "cache", "logs", ".fabric", "versions", "crash-reports"}

GAMEMODES = [("survival", "Survival"), ("creative", "Creative"), ("adventure", "Adventure"), ("spectator", "Spectator")]
DIFFICULTIES = [("peaceful", "Peaceful"), ("easy", "Easy"), ("normal", "Normal"), ("hard", "Hard")]
LEVEL_TYPES = [
    ("normal", "Default"),
    ("flat", "Flat"),
    ("large_biomes", "Large biomes"),
    ("amplified", "Amplified"),
]
_LEGACY_LEVEL_TYPES = {"normal": "default", "flat": "flat", "large_biomes": "largeBiomes", "amplified": "amplified"}


class ServerError(Exception):
    pass


@dataclass
class ServerMeta:
    name: str
    software: str
    mc_version: str
    build: str = ""
    ram_mb: int = 2048
    java_major: int = 17
    java_path: str = "java"
    launch: dict = field(default_factory=dict)
    created: str = ""
    upnp: bool = False  # open router ports automatically on start
    tunnel: bool = False  # start the playit.gg tunnel together with the server
    memory_saver: bool = False  # shorter view/simulation distance, no spawn chunks, eager heap shrinking
    saved_distances: dict = field(default_factory=dict)  # distances before memory saver, to restore
    offline_session: bool = False  # online-mode was turned off for one run without internet; turn back on after
    folder: Path = field(default=None, compare=False)

    def save(self) -> None:
        data = asdict(self)
        data.pop("folder")
        (self.folder / META_FILE).write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def load(cls, folder: Path) -> "ServerMeta":
        data = json.loads((Path(folder) / META_FILE).read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**known, folder=Path(folder))

    @property
    def properties_path(self) -> Path:
        return self.folder / "server.properties"

    def properties(self) -> Properties:
        return Properties(self.properties_path)

    @property
    def software_name(self) -> str:
        try:
            return get_provider(self.software).name
        except Exception:
            return self.software


@dataclass
class WorldOptions:
    mode: str = "random"  # random | seed | import
    seed: str = ""
    import_path: str = ""
    level_type: str = "normal"


@dataclass
class CreateOptions:
    name: str
    software: str
    mc_version: str
    ram_mb: int = 2048
    auto_java: bool = True
    world: WorldOptions = field(default_factory=WorldOptions)
    motd: str = "A Minecraft Server"
    max_players: int = 20
    gamemode: str = "survival"
    difficulty: str = "easy"
    online_mode: bool = True
    pvp: bool = True
    port: int = 25565
    eula_accepted: bool = False
    bedrock: bool = False  # install Geyser + Floodgate (Paper/Purpur)


# ------------------------------------------------------------ server list


def list_servers() -> List[ServerMeta]:
    if not paths.SERVERS_DIR.exists():
        return []
    out = []
    for d in sorted(paths.SERVERS_DIR.iterdir()):
        if (d / META_FILE).is_file():
            try:
                out.append(ServerMeta.load(d))
            except (OSError, ValueError, TypeError):
                continue
    return out


def folder_name_for(name: str) -> Path:
    base = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .") or "server"
    candidate = paths.SERVERS_DIR / base
    i = 2
    while candidate.exists():
        candidate = paths.SERVERS_DIR / f"{base} ({i})"
        i += 1
    return candidate


# ------------------------------------------------- server.properties values


def _legacy_names(mc_version: str) -> bool:
    # Before 1.14 gamemode/difficulty are stored as numbers.
    return not versions.is_at_least(mc_version, "1.14")


def gamemode_value(mode: str, mc_version: str) -> str:
    if _legacy_names(mc_version):
        return str([g for g, _ in GAMEMODES].index(mode))
    return mode


def difficulty_value(diff: str, mc_version: str) -> str:
    if _legacy_names(mc_version):
        return str([d for d, _ in DIFFICULTIES].index(diff))
    return diff


def parse_choice(value: Optional[str], choices: list, default: str) -> str:
    """Both '1' and 'creative' mean 'creative'."""
    keys = [k for k, _ in choices]
    if value is None:
        return default
    value = value.strip().lower()
    if value.isdigit() and int(value) < len(keys):
        return keys[int(value)]
    return value if value in keys else default


def level_type_value(level_type: str, mc_version: str) -> str:
    if versions.is_at_least(mc_version, "1.19"):
        return f"minecraft:{level_type}"
    return _LEGACY_LEVEL_TYPES.get(level_type, "default")


def parse_level_type(value: Optional[str]) -> str:
    v = (value or "").lower().removeprefix("minecraft:")
    mapping = {"default": "normal", "largebiomes": "large_biomes"}
    v = mapping.get(v, v)
    return v if v in dict(LEVEL_TYPES) else "normal"


# --------------------------------------------------------- launch command


def resolve_java(meta: ServerMeta) -> str:
    if meta.java_path and (meta.java_path == "java" or Path(meta.java_path).exists()):
        return meta.java_path
    found = javamod.find_java(meta.java_major, strict=False)
    if not found:
        raise ServerError(t("Java {v} not found. Reinstall it from the Update tab.", v=meta.java_major))
    meta.java_path = found.path
    meta.save()
    return found.path


# Low-resource mode (app setting): start small and hand unused memory back to the OS.
LOW_RESOURCE = {"enabled": True}


def set_low_resource(enabled: bool) -> None:
    LOW_RESOURCE["enabled"] = bool(enabled)


def launch_args(meta: ServerMeta, windows: Optional[bool] = None) -> List[str]:
    """Launch arguments without the java executable."""
    windows = javamod.IS_WINDOWS if windows is None else windows
    low = LOW_RESOURCE["enabled"] or meta.memory_saver
    xms = min(meta.ram_mb, 256 if low else 1024)
    args = [f"-Xms{xms}M", f"-Xmx{meta.ram_mb}M"]
    if low and meta.java_major >= 17:
        # G1 returns unused heap to the OS when the server is idle (flag exists since Java 12)
        args += ["-XX:+UseG1GC", "-XX:G1PeriodicGCInterval=30000"]
    if meta.memory_saver:
        # keep less free heap around, so more memory goes back to the OS
        args += ["-XX:MinHeapFreeRatio=10", "-XX:MaxHeapFreeRatio=30"]
    args += ["-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8"]
    launch = meta.launch or {"type": "jar", "jar": "server.jar"}
    if launch["type"] == "args":
        args.append("@" + (launch["win"] if windows else launch["unix"]))
    else:
        args += ["-jar", launch["jar"]]
    args.append("nogui")
    return args


def launch_command(meta: ServerMeta) -> List[str]:
    return [resolve_java(meta)] + launch_args(meta)


def write_start_scripts(meta: ServerMeta) -> None:
    """Write start.bat / start.sh so the server can run without this app."""
    java = meta.java_path or "java"
    win_args = " ".join(launch_args(meta, windows=True))
    unix_args = " ".join(launch_args(meta, windows=False))
    (meta.folder / "start.bat").write_text(
        f'@echo off\r\ncd /d "%~dp0"\r\n"{java}" {win_args}\r\npause\r\n', encoding="utf-8"
    )
    sh = meta.folder / "start.sh"
    sh.write_text(f'#!/usr/bin/env sh\ncd "$(dirname "$0")"\nexec "{java}" {unix_args}\n', encoding="utf-8")
    sh.chmod(0o755)


# ------------------------------------------------------------------ Java


def _java_for(software: str, mc_version: str, auto_java: bool, task: Task) -> javamod.JavaInfo:
    required = versions.required_java(mc_version)
    hint = get_provider(software).java_hint(mc_version)
    if hint and hint > required:
        required = hint
    task.log(t("Minecraft {mc} needs Java {v}.", mc=mc_version, v=javamod.install_target(required)))
    return javamod.ensure_java(required, auto_java, task)


# ---------------------------------------------------------------- create


def create_server(opts: CreateOptions, task: Optional[Task] = None) -> ServerMeta:
    task = task or Task()
    if not opts.eula_accepted:
        raise ServerError(t("You must accept the Minecraft EULA to create a server."))
    if opts.world.mode == "import":
        find_world_root(Path(opts.world.import_path))  # fail early

    paths.ensure_dirs()
    folder = folder_name_for(opts.name)
    folder.mkdir(parents=True)
    task.log(t("Server folder: {path}", path=folder))
    try:
        provider = get_provider(opts.software)
        java = _java_for(opts.software, opts.mc_version, opts.auto_java, task)
        task.check()
        task.log(t("Installing {name} {v}...", name=provider.name, v=opts.mc_version))
        result = provider.install(folder, opts.mc_version, java, task)

        (folder / "eula.txt").write_text(
            "# https://aka.ms/MinecraftEULA (accepted in Bartizan)\neula=true\n", encoding="utf-8"
        )

        props = Properties(folder / "server.properties")
        v = opts.mc_version
        props.set("motd", opts.motd)
        props.set("max-players", opts.max_players)
        props.set("gamemode", gamemode_value(opts.gamemode, v))
        props.set("difficulty", difficulty_value(opts.difficulty, v))
        props.set("online-mode", opts.online_mode)
        props.set("pvp", opts.pvp)
        props.set("server-port", opts.port)
        props.set("level-name", "world")
        props.set("level-seed", opts.world.seed.strip() if opts.world.mode == "seed" else "")
        props.set("level-type", level_type_value(opts.world.level_type, v))
        props.save()

        if opts.world.mode == "import":
            task.log(t("Importing world..."))
            import_world(folder, Path(opts.world.import_path), "world")

        meta = ServerMeta(
            name=opts.name,
            software=opts.software,
            mc_version=opts.mc_version,
            build=result.get("build", ""),
            ram_mb=opts.ram_mb,
            java_major=java.major,
            java_path=java.path,
            launch=result["launch"],
            created=time.strftime("%Y-%m-%d %H:%M"),
            folder=folder,
        )
        meta.save()
        write_start_scripts(meta)
        if opts.bedrock:
            from mc_server_maker.core import plugins

            try:
                plugins.install_bedrock(meta, task)
            except Exception as e:  # noqa: BLE001 - the server itself is fine; Bedrock can be added later
                task.log(t("Could not install Bedrock support: {err} (you can retry in Settings)", err=e))
        task.log(t("Server created!"))
        return meta
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


# --------------------------------------------------------------- upgrade


def upgrade_server(
    meta: ServerMeta,
    new_version: str,
    auto_java: bool = True,
    backup_first: bool = True,
    task: Optional[Task] = None,
) -> ServerMeta:
    task = task or Task()
    old_version = meta.mc_version
    if backup_first:
        backup_server(meta, f"before-{new_version}", task=task)
    java = _java_for(meta.software, new_version, auto_java, task)
    task.check()
    provider = get_provider(meta.software)
    task.log(t("Upgrading {name} {old} → {new}...", name=provider.name, old=old_version, new=new_version))

    old_launch = meta.launch or {}
    result = provider.install(meta.folder, new_version, java, task)
    new_launch = result["launch"]
    # remove an old launcher jar with a different name (old Forge jars etc.)
    if old_launch.get("type") == "jar" and old_launch != new_launch:
        old_jar = meta.folder / old_launch["jar"]
        if old_jar.name != new_launch.get("jar"):
            old_jar.unlink(missing_ok=True)

    props = meta.properties()
    if props.get("level-type"):
        # level-type values changed format in 1.19
        props.set("level-type", level_type_value(parse_level_type(props.get("level-type")), new_version))
        props.save()

    meta.mc_version = new_version
    meta.build = result.get("build", "")
    meta.launch = new_launch
    meta.java_major = java.major
    meta.java_path = java.path
    meta.save()
    write_start_scripts(meta)
    from mc_server_maker.core import plugins

    if plugins.bedrock_installed(meta):
        task.log(t("Updating Geyser/Floodgate for the new version..."))
        try:
            plugins.install_bedrock(meta, task)
        except Exception as e:  # noqa: BLE001 - the server itself is updated; Geyser can be retried
            task.log(t("Could not update Geyser: {err} (retry from Settings)", err=e))
    task.log(t("Upgrade complete! The world is converted to the new version on next start."))
    return meta


def change_java(meta: ServerMeta, auto_java: bool, task: Optional[Task] = None) -> ServerMeta:
    task = task or Task()
    java = _java_for(meta.software, meta.mc_version, auto_java, task)
    meta.java_major = java.major
    meta.java_path = java.path
    meta.save()
    write_start_scripts(meta)
    return meta


# ----------------------------------------------------------------- backups


def world_dirs(meta: ServerMeta) -> List[Path]:
    level = meta.properties().get("level-name") or "world"
    return [meta.folder / n for n in (level, f"{level}_nether", f"{level}_the_end")]


def backup_server(meta: ServerMeta, label: str = "", worlds_only: bool = False, task: Optional[Task] = None) -> Path:
    task = task or Task()
    backups = meta.folder / BACKUP_DIR
    backups.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_label = re.sub(r"[^\w.-]", "_", label)
    dest = backups / f"{stamp}{'-' + safe_label if safe_label else ''}.zip"
    if worlds_only:
        roots = [d for d in world_dirs(meta) if d.exists()]
    else:
        roots = [p for p in meta.folder.iterdir() if p.name not in BACKUP_EXCLUDE]
    files = []
    for root in roots:
        if root.is_file():
            files.append(root)
        else:
            files.extend(p for p in root.rglob("*") if p.is_file())
    task.log(t("Backing up... ({n} files)", n=len(files)))
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for i, f in enumerate(files):
            task.check()
            if f.name == "session.lock":
                continue
            z.write(f, f.relative_to(meta.folder).as_posix())
            task.progress(i + 1, len(files))
    task.log(t("Backup saved: {path}", path=dest))
    return dest


def list_backups(meta: ServerMeta) -> List[Path]:
    d = meta.folder / BACKUP_DIR
    return sorted(d.glob("*.zip"), reverse=True) if d.exists() else []


# ------------------------------------------------------------------ worlds


def find_world_root(src: Path) -> Path:
    """Locate level.dat inside a folder or zip (returns the folder, or the zip path)."""
    if not str(src).strip():
        raise ServerError(t("Choose a world (folder or zip) to import."))
    src = Path(src)
    if not src.exists():
        raise ServerError(t("World path does not exist: {path}", path=src))
    if src.is_dir():
        if (src / "level.dat").exists():
            return src
        for sub in sorted(src.iterdir()):
            if sub.is_dir() and (sub / "level.dat").exists():
                return sub
        raise ServerError(t("No level.dat found in that folder. Choose a world folder."))
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            if not any(n.endswith("level.dat") and n.count("/") <= 1 for n in z.namelist()):
                raise ServerError(t("The zip file has no level.dat."))
        return src
    raise ServerError(t("A world must be a folder or a .zip file."))


def import_world(server_dir: Path, src: Path, level_name: str = "world") -> None:
    root = find_world_root(src)
    dest = Path(server_dir) / level_name
    if dest.exists():
        shutil.rmtree(dest)
    if root.is_dir():
        shutil.copytree(root, dest, ignore=shutil.ignore_patterns("session.lock"))
        return
    with tempfile.TemporaryDirectory(dir=server_dir) as tmp:
        tmp_path = Path(tmp).resolve()
        with zipfile.ZipFile(root) as z:
            for name in z.namelist():
                if not (tmp_path / name).resolve().is_relative_to(tmp_path):
                    raise ServerError(t("The archive contains an invalid path."))
            z.extractall(tmp_path)
        shutil.copytree(find_world_root(tmp_path), dest, ignore=shutil.ignore_patterns("session.lock"))


def _remove_worlds(meta: ServerMeta) -> None:
    for d in world_dirs(meta):
        if d.exists():
            shutil.rmtree(d)


def replace_world_with_import(meta: ServerMeta, src: Path, task: Optional[Task] = None) -> None:
    task = task or Task()
    find_world_root(src)
    if any(d.exists() for d in world_dirs(meta)):
        backup_server(meta, "world-before-import", worlds_only=True, task=task)
    _remove_worlds(meta)
    level = meta.properties().get("level-name") or "world"
    task.log(t("Importing world..."))
    import_world(meta.folder, src, level)
    task.log(t("World imported!"))


def regenerate_world(meta: ServerMeta, seed: str, level_type: str, task: Optional[Task] = None) -> None:
    """Back up and delete the world so a new one is generated on next start."""
    task = task or Task()
    if any(d.exists() for d in world_dirs(meta)):
        backup_server(meta, "world-before-reset", worlds_only=True, task=task)
    _remove_worlds(meta)
    props = meta.properties()
    props.set("level-seed", seed.strip())
    props.set("level-type", level_type_value(level_type, meta.mc_version))
    props.save()
    task.log(t("Old world removed. A new world is generated on next start."))


# ------------------------------------------------------------ memory saver

MEMORY_SAVER_DISTANCES = {"view-distance": 6, "simulation-distance": 4}


def spawn_chunk_command(meta: ServerMeta) -> Optional[str]:
    """Console command that stops spawn chunks from staying loaded (1.20.5 - 1.21.8 only).

    The gamerule was added in 1.20.5; 1.21.9 removed spawn chunks altogether.
    """
    v = versions.version_key(meta.mc_version)[0]
    if versions.version_key("1.20.5")[0] <= v < versions.version_key("1.21.9")[0]:
        return "gamerule spawnChunkRadius 0"
    return None


def set_memory_saver(meta: ServerMeta, on: bool) -> None:
    """Turn memory saver on/off, remembering and restoring the previous distances."""
    if on == meta.memory_saver:
        return
    props = meta.properties()
    if on:
        meta.saved_distances = {k: props.get(k, "10") for k in MEMORY_SAVER_DISTANCES}
        for k, v in MEMORY_SAVER_DISTANCES.items():
            props.set(k, v)
    else:
        for k in MEMORY_SAVER_DISTANCES:
            props.set(k, meta.saved_distances.get(k, "10"))
        meta.saved_distances = {}
    props.save()
    meta.memory_saver = on
    meta.save()
    write_start_scripts(meta)


# --------------------------------------------------------- copy / rename

DUPLICATE_SKIP = {BACKUP_DIR, "logs", "crash-reports", "cache", "session.lock"}


def duplicate_server(meta: ServerMeta, new_name: str, task: Optional[Task] = None) -> ServerMeta:
    """Copy a whole server (world, settings, plugins/mods) under a new name."""
    task = task or Task()
    dest = folder_name_for(new_name)
    task.log(t("Copying to {path}...", path=dest))
    try:
        shutil.copytree(meta.folder, dest, ignore=lambda _d, names: [n for n in names if n in DUPLICATE_SKIP])
        copy = ServerMeta.load(dest)
        copy.name = new_name
        copy.created = time.strftime("%Y-%m-%d %H:%M")
        copy.save()
        write_start_scripts(copy)
    except BaseException:
        shutil.rmtree(dest, ignore_errors=True)
        raise
    task.log(t("Done."))
    return copy


def begin_offline_session(meta: ServerMeta) -> None:
    """Let players join without Mojang sign-in for this run (no internet). Undone by end_offline_session."""
    props = meta.properties()
    props.set("online-mode", False)
    props.save()
    meta.offline_session = True
    meta.save()


def end_offline_session(meta: ServerMeta) -> bool:
    """Turn online mode back on after an offline run. Returns True if something was restored."""
    try:  # the saved file decides; this copy may be older or newer than it
        pending = ServerMeta.load(meta.folder).offline_session
    except (OSError, ValueError):
        pending = meta.offline_session
    if not pending:
        meta.offline_session = False
        return False
    props = meta.properties()
    props.set("online-mode", True)
    props.save()
    meta.offline_session = False
    meta.save()
    return True
