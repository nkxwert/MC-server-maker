"""Create / upgrade servers, manage worlds and backups."""

import json
import re
import os
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
UPTIME_FILE = "bartizan-uptime.json"  # total running time; kept apart so meta saves can't overwrite it
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


# Friendlier than vanilla for a small server among friends.
NEW_SERVER_DEFAULTS = {
    "spawn-protection": 0,  # everyone can build at spawn
    "chat-spam-threshold-seconds": 0,  # don't kick for chatting fast (26.2+; older versions ignore it)
    "command-spam-threshold-seconds": 0,
}


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
    autosave_minutes: int = 0  # save the world every N minutes while running (0 = off)
    offline_session: bool = False  # online-mode was turned off for one run without internet; turn back on after
    auto_backup: bool = False  # back up the world each time the server stops
    auto_backup_keep: int = 5  # how many automatic backups to keep (the others are never deleted)
    folder: Path = field(default=None, compare=False)

    def save(self) -> None:
        data = asdict(self)
        data.pop("folder")
        path = self.folder / META_FILE
        tmp = path.with_name(META_FILE + ".tmp")  # never leave a half-written file after a crash
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, path)

    @classmethod
    def load(cls, folder: Path) -> "ServerMeta":
        data = json.loads((Path(folder) / META_FILE).read_text(encoding="utf-8"))
        known = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        for k, f in cls.__dataclass_fields__.items():  # a hand-edited "4096" instead of 4096
            if k in known and f.type in (int, "int") and not isinstance(known[k], int):
                try:
                    known[k] = int(known[k])
                except (TypeError, ValueError):
                    known.pop(k)
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


def is_builtin_level_type(value: Optional[str]) -> bool:
    """False for a mod's world type (e.g. "biomesoplenty:biomesoplenty"): those are left alone."""
    v = (value or "").lower().removeprefix("minecraft:")
    return v in dict(LEVEL_TYPES) or v in ("default", "largebiomes")


# --------------------------------------------------------- launch command


def resolve_java(meta: ServerMeta) -> str:
    if meta.java_path and (meta.java_path == "java" or Path(meta.java_path).exists()):
        return meta.java_path
    found = javamod.find_java(meta.java_major, strict=False)
    if not found:
        raise ServerError(t("Java {v} not found. Reinstall it in the World tab (Server version).", v=meta.java_major))
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
        # chcp 65001: cmd reads .bat files in the OEM code page, which garbles e.g. a Korean Java path
        f'@echo off\r\nchcp 65001 >nul\r\ncd /d "%~dp0"\r\n"{java}" {win_args}\r\npause\r\n', encoding="utf-8"
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
        for key, value in NEW_SERVER_DEFAULTS.items():
            props.set(key, value)
        props.save()

        if opts.world.mode == "import":
            task.log(t("Importing world..."))
            import_world(folder, Path(opts.world.import_path), "world", opts.software, task)

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


SPLIT_DIMENSIONS = ("paper", "purpur")  # keep the Nether/End in world_nether / world_the_end


def upgrade_server(
    meta: ServerMeta,
    new_version: str,
    auto_java: bool = True,
    backup_first: bool = True,
    task: Optional[Task] = None,
    new_software: Optional[str] = None,
) -> ServerMeta:
    """Update the server to another version, or switch it to another software (Paper -> Fabric...).

    The world, server.properties, OPs/whitelist and the app's settings stay.
    """
    task = task or Task()
    old_version = meta.mc_version
    software = new_software or meta.software
    switching = software != meta.software
    if backup_first:
        label = f"before-{software}-{new_version}" if switching else f"before-{new_version}"
        backup_server(meta, label, task=task)
    java = _java_for(software, new_version, auto_java, task)
    task.check()
    provider = get_provider(software)
    if switching:
        task.log(t("Switching {old} → {new} {v}...", old=meta.software_name, new=provider.name, v=new_version))
    else:
        task.log(t("Upgrading {name} {old} → {new}...", name=provider.name, old=old_version, new=new_version))

    old_launch = meta.launch or {}
    result = provider.install(meta.folder, new_version, java, task)
    new_launch = result["launch"]
    # remove an old launcher jar with a different name (old Forge jars etc.)
    if old_launch.get("type") == "jar" and old_launch != new_launch:
        old_jar = meta.folder / old_launch["jar"]
        if old_jar.name != new_launch.get("jar"):
            old_jar.unlink(missing_ok=True)

    # the new software is in place: record it right away, so a later step failing can't leave
    # settings that still launch the old (now removed) jar
    old_software = meta.software
    meta.software = software
    meta.mc_version = new_version
    meta.build = result.get("build", "")
    meta.launch = new_launch
    meta.java_major = java.major
    meta.java_path = java.path
    meta.save()
    write_start_scripts(meta)

    props = meta.properties()
    if is_builtin_level_type(props.get("level-type")):
        # level-type values changed format in 1.19
        props.set("level-type", level_type_value(parse_level_type(props.get("level-type")), new_version))
        props.save()

    if switching and old_software in SPLIT_DIMENSIONS and software not in SPLIT_DIMENSIONS:
        try:  # (vanilla -> Paper needs nothing: Paper splits them itself)
            _merge_dimensions(meta, task)
        except (OSError, ServerError) as e:
            task.log(t("Couldn't move the Nether/End into the world folder: {err}. "
                       "The backup has them; move them by hand before starting.", err=e))
    from mc_server_maker.core import plugins

    if plugins.bedrock_installed(meta) and plugins.supports_bedrock(meta):
        task.log(t("Updating Geyser/Floodgate for the new version..."))
        try:
            plugins.install_bedrock(meta, task)
        except Exception as e:  # noqa: BLE001 - the server itself is updated; Geyser can be retried
            task.log(t("Could not update Geyser: {err} (retry from Settings)", err=e))
    task.log(t("Done! {name} {v} starts with your world next time.", name=provider.name, v=new_version) if switching
             else t("Upgrade complete! The world is converted to the new version on next start."))
    return meta


def _merge_dimensions(meta: ServerMeta, task: Task) -> None:
    """Paper keeps the Nether and End in world_nether/DIM-1 and world_the_end/DIM1; vanilla
    and mod loaders expect them inside world/. Move them back so they aren't regenerated."""
    _merge_dimensions_in(meta.folder, level_name(meta), task)


def _merge_dimensions_in(base: Path, level: str, task: Task) -> None:
    world = base / level
    for folder, dim in ((f"{level}_nether", "DIM-1"), (f"{level}_the_end", "DIM1")):
        src = base / folder / dim
        if not src.is_dir():
            continue
        dest = world / dim
        if dest.exists() and any(dest.iterdir()):
            task.log(t("{dim} already exists in {world}; left {folder} as it is.", dim=dim, world=level, folder=folder))
            continue
        world.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.rmdir()
        shutil.move(str(src), str(dest))
        leftover = base / folder
        try:  # only Paper's bookkeeping files are left; the backup has them anyway
            shutil.rmtree(leftover)
        except OSError:
            pass
        task.log(t("Moved {folder} into {world}.", folder=folder, world=level))


def _split_dimensions_in(base: Path, level: str, task: Task) -> None:
    """The reverse, for Paper/Purpur: world/DIM-1 -> world_nether/DIM-1, world/DIM1 -> world_the_end/DIM1."""
    world = base / level
    for folder, dim in ((f"{level}_nether", "DIM-1"), (f"{level}_the_end", "DIM1")):
        src = world / dim
        if not src.is_dir():
            continue
        dest = base / folder / dim
        if dest.exists() and any(dest.iterdir()):
            task.log(t("{dim} already exists in {world}; left {folder} as it is.",
                       dim=dim, world=folder, folder=f"{level}/{dim}"))
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists():
            dest.rmdir()
        shutil.move(str(src), str(dest))
        # like Paper's own migration: the dimension world gets the seed etc. from level.dat
        if (world / "level.dat").is_file() and not (dest.parent / "level.dat").exists():
            shutil.copy2(world / "level.dat", dest.parent / "level.dat")
        task.log(t("Moved {folder} into {world}.", folder=f"{level}/{dim}", world=folder))


def _fit_dimensions(base: Path, level: str, software: str, task: Task) -> None:
    """Put an imported world's Nether/End where this server's software reads them."""
    if software in SPLIT_DIMENSIONS:
        _split_dimensions_in(base, level, task)
    else:
        _merge_dimensions_in(base, level, task)


def change_java(meta: ServerMeta, auto_java: bool, task: Optional[Task] = None) -> ServerMeta:
    task = task or Task()
    java = _java_for(meta.software, meta.mc_version, auto_java, task)
    meta.java_major = java.major
    meta.java_path = java.path
    meta.save()
    write_start_scripts(meta)
    return meta


# ----------------------------------------------------------------- backups


def level_name(meta: ServerMeta) -> str:
    """level-name from server.properties, refused if it points outside the world folder.

    It's free text (the full properties editor), and worlds get deleted by it: "." would be the
    server folder itself, ".." every server, an absolute path anywhere on the disk."""
    level = (meta.properties().get("level-name") or "world").strip() or "world"
    root = meta.folder.resolve()
    target = (meta.folder / level).resolve()
    bad = (Path(level).is_absolute() or ":" in level or target == root or not target.is_relative_to(root)
           or any(part in ("", ".", "..") for part in level.replace("\\", "/").split("/"))
           or target.name in (BACKUP_DIR, "plugins", "mods", "config", "libraries", "logs"))
    if bad:
        raise ServerError(t("The world folder name (level-name = '{name}') isn't a safe folder inside the server. "
                            "Change it in All server.properties, e.g. to 'world'.", name=level))
    return level


def world_dirs(meta: ServerMeta) -> List[Path]:
    level = level_name(meta)
    return [meta.folder / n for n in (level, f"{level}_nether", f"{level}_the_end")]


def backup_server(meta: ServerMeta, label: str = "", worlds_only: bool = False, task: Optional[Task] = None) -> Path:
    task = task or Task()
    backups = meta.folder / BACKUP_DIR
    backups.mkdir(exist_ok=True)
    for old in backups.glob("*.zip.part"):  # cut off earlier (PC shut down mid-backup): only clutter
        try:
            if time.time() - old.stat().st_mtime > 3600:
                old.unlink()
        except OSError:
            pass
    stamp = time.strftime("%Y%m%d-%H%M%S")
    safe_label = re.sub(r"[^\w.-]", "_", label)
    base = f"{stamp}{'-' + safe_label if safe_label else ''}"
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
    # two backups in the same second get -2, -3...: never overwrite one
    n = 1
    while True:
        dest = backups / f"{base}{'-' + str(n) if n > 1 else ''}.zip"
        part = dest.with_name(dest.name + ".part")  # renamed only when complete
        if not dest.exists():
            try:
                # strict_timestamps=False: a file dated before 1980 (from a jar, a wrong clock) mustn't stop the backup
                # "x": another backup writing this name right now keeps it
                zf = zipfile.ZipFile(part, "x", zipfile.ZIP_DEFLATED, strict_timestamps=False)
                break
            except FileExistsError:
                pass
        n += 1
    try:
        with zf as z:
            for i, f in enumerate(files):
                task.check()
                if f.name == "session.lock":
                    continue
                z.write(f, f.relative_to(meta.folder).as_posix())
                task.progress(i + 1, len(files))
        part.replace(dest)
    except BaseException:
        part.unlink(missing_ok=True)  # cancelled / unreadable file / disk full
        raise
    task.log(t("Backup saved: {path}", path=dest))
    return dest


def list_backups(meta: ServerMeta) -> List[Path]:
    d = meta.folder / BACKUP_DIR
    return sorted(d.glob("*.zip"), reverse=True) if d.exists() else []


# What made a backup is the label after the time stamp: "20250101-120000-auto.zip". Older
# backups have only a label too ("world", "before-1.21.4"), so they read right without changes.
AUTO_LABEL = "auto"  # when the server stopped (the only kind ever deleted automatically)
MANUAL_LABEL = "world"  # "Back up now"
RESTORE_LABEL = "before-restore"  # the world that a restore replaced
AUTO_BACKUP_KEEP_CHOICES = (3, 5, 10, 20)
_STAMP_RE = re.compile(r"^(\d{8}-\d{6})(?:-(.*))?$")
# labels written exactly like this, so a "-2" after them is the same-second counter
# (after "before-1.21" it could be part of a version)
_EXACT_LABELS = {"", AUTO_LABEL, MANUAL_LABEL, "manual", RESTORE_LABEL, "world-before-import", "world-before-reset"}


@dataclass
class BackupInfo:
    path: Path
    when: float  # seconds since the epoch (from the name; the file time for odd names)
    kind: str  # auto | manual | update | restore | other
    label: str  # "1.21.4" for an update, the raw label for other kinds, "" otherwise
    size: int
    seq: int = 1  # the same-second counter, to order backups made in one second


def parse_backup_name(name: str):
    """(time stamp or None, kind, label, counter) from a backup file name."""
    stem = name[:-4] if name.lower().endswith(".zip") else name
    m = _STAMP_RE.match(stem)
    if not m:
        return None, "other", stem, 1
    rest, seq = m.group(2) or "", 1
    counter = re.match(r"^(?:(.*)-)?(\d{1,3})$", rest)
    if counter and (counter.group(1) or "") in _EXACT_LABELS:
        rest, seq = counter.group(1) or "", int(counter.group(2))
    try:
        when = time.mktime(time.strptime(m.group(1), "%Y%m%d-%H%M%S"))
    except (ValueError, OverflowError):
        when = None
    if rest in ("", MANUAL_LABEL, "manual"):
        return when, "manual", "", seq
    if rest == AUTO_LABEL:
        return when, "auto", "", seq
    if rest == RESTORE_LABEL:
        return when, "restore", "", seq
    if rest.startswith("before-") and len(rest) > 7:
        return when, "update", rest[7:], seq  # "before-1.21.4", "before-paper-1.21.4"
    return when, "other", rest, seq


def backup_infos(meta: ServerMeta) -> List[BackupInfo]:
    """Every backup, newest first."""
    out = []
    for p in list_backups(meta):
        try:
            st = p.stat()
        except OSError:
            continue  # deleted meanwhile
        when, kind, label, seq = parse_backup_name(p.name)
        out.append(BackupInfo(p, when if when is not None else st.st_mtime, kind, label, st.st_size, seq))
    out.sort(key=lambda b: (b.when, b.seq), reverse=True)
    return out


def prune_auto_backups(meta: ServerMeta, keep: int, protect: Optional[Path] = None) -> List[Path]:
    """Delete automatic backups beyond the newest `keep`. Other kinds are never touched, nor
    `protect` (the one just made, even if the clock was set back and its name sorts older)."""
    def mtime(b):
        try:
            return b.path.stat().st_mtime
        except OSError:
            return 0
    autos = sorted((b for b in backup_infos(meta) if b.kind == "auto"
                    and not (protect and b.path.resolve() == Path(protect).resolve())), key=mtime, reverse=True)
    keep = max(1, keep) - (1 if protect else 0)
    removed = []
    for b in autos[max(0, keep):]:
        try:
            b.path.unlink()
            removed.append(b.path)
        except OSError:
            pass  # open in another program: deleted next time
    return removed


def backup_has_server_files(path: Path) -> bool:
    """A whole-server backup (made before an update) rather than just the world."""
    try:
        with zipfile.ZipFile(path) as z:
            return any(n in ("server.properties", META_FILE) for n in z.namelist())
    except (OSError, zipfile.BadZipFile):
        return False


def _zip_level_name(z: zipfile.ZipFile) -> str:
    """level-name from the server.properties inside a whole-server backup ("" if none)."""
    try:
        text = z.read("server.properties").decode("utf-8", "replace")
    except KeyError:
        return ""
    for line in text.splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() == "level-name":
            return value.strip()
    return ""


def _backup_world_prefix(z: zipfile.ZipFile, level: str) -> str:
    """The world folder inside a backup ("world", "worlds/main", "" for level.dat at the top).

    The level-name the backup was made with comes first (a server with several worlds has more
    than one level.dat), then this server's, then the shallowest one."""
    names = [n for n in z.namelist() if _safe_member(n)]
    worlds = {n[:-len("level.dat")].rstrip("/") for n in names if n == "level.dat" or n.endswith("/level.dat")}
    for wanted in (_zip_level_name(z), level):
        if wanted and wanted in worlds:
            return wanted
    worlds = {w for w in worlds if w.count("/") < WORLD_SEARCH_DEPTH}
    if not worlds:
        raise ServerError(t("The zip file has no level.dat."))
    return min(worlds, key=_world_rank)


# ------------------------------------------------------------------ worlds


WORLD_SEARCH_DEPTH = 8  # how deep to look for level.dat (a picked home folder mustn't be walked forever)


def _world_rank(rel: str):
    """Sort key for a folder holding level.dat: shallowest first, the overworld before
    world_nether / world_the_end (a backup holds all three), then by name."""
    parts = [p for p in rel.split("/") if p]
    return len(parts), bool(parts) and parts[-1].endswith(("_nether", "_the_end")), rel


def _safe_member(name: str) -> bool:
    parts = name.replace("\\", "/").split("/")
    return not (name.startswith(("/", "\\")) or ":" in name or ".." in parts)


def _find_world_dir(src: Path) -> Optional[Path]:
    """The shallowest folder under src (src included) that holds level.dat."""
    level = [src]
    for _ in range(WORLD_SEARCH_DEPTH + 1):
        hits = [d for d in level if (d / "level.dat").is_file()]
        if hits:
            return min(hits, key=lambda d: _world_rank(d.relative_to(src).as_posix() if d != src else ""))
        below = []
        for d in level:
            try:
                below.extend(s for s in d.iterdir() if s.is_dir() and not s.is_symlink())
            except OSError:
                pass  # unreadable folder
        level = below
    return None


def find_world_root(src: Path) -> Path:
    """Locate level.dat inside a folder or zip (returns the folder, or the zip path)."""
    if not str(src).strip():
        raise ServerError(t("Choose a world (folder or zip) to import."))
    src = Path(src)
    if not src.exists():
        raise ServerError(t("World path does not exist: {path}", path=src))
    if src.is_dir():
        found = _find_world_dir(src)
        if found:
            return found
        raise ServerError(t("No level.dat found in that folder. Choose a world folder."))
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            # any depth: a server with level-name "worlds/main" backs up worlds/main/level.dat
            if not any((n == "level.dat" or n.endswith("/level.dat")) and _safe_member(n)
                       and n.count("/") <= WORLD_SEARCH_DEPTH for n in z.namelist()):
                raise ServerError(t("The zip file has no level.dat."))
        return src
    raise ServerError(t("A world must be a folder or a .zip file."))


def import_world(server_dir: Path, src: Path, level_name: str = "world", software: str = "",
                 task: Optional[Task] = None) -> None:
    """Copy a world (folder or zip) in. With software, its Nether/End are moved to where that
    software reads them (Paper: world_nether/DIM-1, the others: world/DIM-1)."""
    task = task or Task()
    root = find_world_root(src)
    dest = Path(server_dir) / level_name
    if dest.exists():
        shutil.rmtree(dest)
    if root.is_dir():
        _copy_world(root, Path(server_dir), level_name, task)
    else:
        with tempfile.TemporaryDirectory(dir=server_dir) as tmp:
            tmp_path = Path(tmp).resolve()
            with zipfile.ZipFile(root) as z:
                for name in z.namelist():
                    if not (tmp_path / name).resolve().is_relative_to(tmp_path):
                        raise ServerError(t("The archive contains an invalid path."))
                for info in z.infolist():
                    task.check()
                    z.extract(info, tmp_path)
            _copy_world(find_world_root(tmp_path), Path(server_dir), level_name, task)
    if software:
        _fit_dimensions(Path(server_dir), level_name, software, task)


def _copy_world(root: Path, server_dir: Path, level_name: str, task: Optional[Task] = None) -> None:
    """Copy a world folder, plus "<name>_nether" / "<name>_the_end" next to it (Paper/Spigot layout)."""
    task = task or Task()
    ignore = shutil.ignore_patterns("session.lock")

    def copy(s, d):
        task.check()  # cancelled: stop between files
        return shutil.copy2(s, d)

    shutil.copytree(root, server_dir / level_name, ignore=ignore, copy_function=copy)
    for suffix in ("_nether", "_the_end"):
        extra = root.with_name(root.name + suffix)
        if extra.is_dir() and extra != root:
            target = server_dir / (level_name + suffix)
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(extra, target, ignore=ignore, copy_function=copy)


def _remove_worlds(meta: ServerMeta) -> None:
    for d in world_dirs(meta):
        if d.exists():
            shutil.rmtree(d)


def replace_world_with_import(meta: ServerMeta, src: Path, task: Optional[Task] = None) -> None:
    task = task or Task()
    root = find_world_root(src).resolve()
    current = [d.resolve() for d in world_dirs(meta)]
    if any(root == d or root.is_relative_to(d) for d in current):
        raise ServerError(t("That is this server's own world. Choose another world to import."))
    if any(d.exists() for d in world_dirs(meta)):
        backup_server(meta, "world-before-import", worlds_only=True, task=task)
    level = level_name(meta)
    task.log(t("Importing world..."))
    # copy/extract next to the server first; the current world is removed only once that worked
    with tempfile.TemporaryDirectory(dir=meta.folder, prefix=".import-") as tmp:
        staging = Path(tmp)
        import_world(staging, src, level, meta.software, task)
        _swap_in_world(meta, staging, level, task)
    task.log(t("World imported!"))


def _swap_in_world(meta: ServerMeta, staging: Path, level: str, task: Task) -> None:
    """Replace the world with the one ready in `staging`."""
    task.check()  # last chance to cancel: the old world is untouched until here
    # move the old folders aside first: a rename fails as a whole (a locked file on Windows), so
    # nothing is half deleted; they are removed only once the new world is in place
    stamp = time.strftime("%Y%m%d-%H%M%S")
    aside = []
    try:
        for d in world_dirs(meta):
            if d.exists():
                old = d.with_name(f".{d.name}.old-{stamp}")
                os.replace(d, old)
                aside.append((d, old))
        for name in (level, f"{level}_nether", f"{level}_the_end"):  # level-name may be "worlds/main"
            if (staging / name).exists():
                (meta.folder / name).parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(staging / name), str(meta.folder / name))
    except BaseException:
        for d, old in reversed(aside):  # put the old world back
            if d.exists():
                shutil.rmtree(d, ignore_errors=True)
            try:
                os.replace(old, d)
            except OSError:
                pass
        raise
    for _d, old in aside:
        shutil.rmtree(old, ignore_errors=True)


def restore_backup(meta: ServerMeta, path: Path, task: Optional[Task] = None) -> None:
    """Put the world from a backup back; the current world is backed up first ("before-restore").

    Only the world: a whole-server backup (made before an update) leaves the server's version,
    settings and plugins as they are now. Extracted next to the server first, like an import,
    so a cancel or an error keeps the current world."""
    task = task or Task()
    path = Path(path)
    level = level_name(meta)
    try:
        with zipfile.ZipFile(path) as z:
            if not all(_safe_member(n) for n in z.namelist()):
                raise ServerError(t("The archive contains an invalid path."))
            src = _backup_world_prefix(z, level)
    except (OSError, zipfile.BadZipFile) as e:
        raise ServerError(t("The backup can't be read: {err}", err=e)) from e
    # its folders, under this server's level-name (it may have been renamed since)
    folders = {src: level, f"{src}_nether": f"{level}_nether", f"{src}_the_end": f"{level}_the_end"} if src \
        else {"": level}
    if any(d.exists() for d in world_dirs(meta)):
        backup_server(meta, RESTORE_LABEL, worlds_only=True, task=task)
    task.log(t("Restoring the world from {name}...", name=path.name))
    with tempfile.TemporaryDirectory(dir=meta.folder, prefix=".restore-") as tmp:
        staging = Path(tmp).resolve()
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            for i, info in enumerate(infos):
                task.check()
                name = info.filename
                for prefix, target in folders.items():
                    if not prefix or name.startswith(prefix + "/"):
                        rel = name[len(prefix) + 1:] if prefix else name
                        break
                else:
                    continue  # not the world (the jar, plugins... of a whole-server backup)
                if not rel or rel.endswith("/") or rel.rsplit("/", 1)[-1] == "session.lock":
                    continue
                dest = (staging / target / rel).resolve()
                if not dest.is_relative_to(staging):
                    raise ServerError(t("The archive contains an invalid path."))
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as fin, open(dest, "wb") as fout:
                    shutil.copyfileobj(fin, fout)
                task.progress(i + 1, len(infos))
        if not (staging / level / "level.dat").is_file():
            raise ServerError(t("The zip file has no level.dat."))
        _fit_dimensions(staging, level, meta.software, task)
        _swap_in_world(meta, staging, level, task)
    task.log(t("World restored."))


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

DUPLICATE_SKIP = {BACKUP_DIR, "logs", "crash-reports", "cache", "session.lock", UPTIME_FILE}


def duplicate_server(meta: ServerMeta, new_name: str, task: Optional[Task] = None) -> ServerMeta:
    """Copy a whole server (world, settings, plugins/mods) under a new name."""
    task = task or Task()
    dest = folder_name_for(new_name)
    task.log(t("Copying to {path}...", path=dest))
    try:
        # skip backups, logs... only at the top: plugins keep their own "logs"/"cache" folders
        top = str(meta.folder)
        shutil.copytree(meta.folder, dest, ignore=lambda d, names: [
            n for n in names if (n in DUPLICATE_SKIP if os.path.normpath(d) == os.path.normpath(top) else n == "session.lock")])
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


def total_uptime(folder: Path) -> float:
    """Seconds this server has run in total (all runs so far)."""
    try:
        data = json.loads((Path(folder) / UPTIME_FILE).read_text(encoding="utf-8"))
        return max(0.0, float(data.get("total_seconds", 0)))
    except (OSError, ValueError, TypeError, AttributeError):
        return 0.0


def add_uptime(folder: Path, seconds: float) -> float:
    """Add a run's seconds to the total and return the new total."""
    total = total_uptime(folder) + max(0.0, seconds)
    try:
        path = Path(folder) / UPTIME_FILE
        tmp = path.with_name(UPTIME_FILE + ".tmp")
        tmp.write_text(json.dumps({"total_seconds": round(total)}), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass  # e.g. the folder was just moved to the Recycle Bin
    return total
