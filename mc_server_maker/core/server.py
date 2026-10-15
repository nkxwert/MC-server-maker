"""서버 만들기 / 업그레이드 / 월드 관리."""

import json
import re
import shutil
import socket
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

META_FILE = "server-maker.json"
BACKUP_DIR = "backups"
# 백업에서 제외 (용량이 크고 다시 받을 수 있는 것들)
BACKUP_EXCLUDE = {BACKUP_DIR, "libraries", "cache", "logs", ".fabric", "versions", "crash-reports"}

GAMEMODES = [("survival", "서바이벌"), ("creative", "크리에이티브"), ("adventure", "모험"), ("spectator", "관전")]
DIFFICULTIES = [("peaceful", "평화로움"), ("easy", "쉬움"), ("normal", "보통"), ("hard", "어려움")]
LEVEL_TYPES = [
    ("normal", "기본"),
    ("flat", "평지"),
    ("large_biomes", "큰 생물 군계"),
    ("amplified", "확대"),
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


# ---------------------------------------------------------------- 서버 목록


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


# ------------------------------------------------------- server.properties 값


def _legacy_names(mc_version: str) -> bool:
    # 1.14 미만은 gamemode/difficulty를 숫자로 저장한다.
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
    """'1', 'creative' 둘 다 'creative'로 해석한다."""
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


# --------------------------------------------------------------- 실행 명령


def resolve_java(meta: ServerMeta) -> str:
    if meta.java_path and (meta.java_path == "java" or Path(meta.java_path).exists()):
        return meta.java_path
    found = javamod.find_java(meta.java_major, strict=False)
    if not found:
        raise ServerError(f"Java {meta.java_major}을(를) 찾지 못했습니다. 업그레이드 탭에서 Java를 다시 설치해 주세요.")
    meta.java_path = found.path
    meta.save()
    return found.path


def launch_args(meta: ServerMeta, windows: Optional[bool] = None) -> List[str]:
    """java 경로를 뺀 실행 인자."""
    windows = javamod.IS_WINDOWS if windows is None else windows
    xms = min(meta.ram_mb, 1024)
    args = [f"-Xms{xms}M", f"-Xmx{meta.ram_mb}M", "-Dfile.encoding=UTF-8", "-Dstdout.encoding=UTF-8"]
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
    """프로그램 없이도 서버를 켤 수 있게 start.bat / start.sh를 만든다."""
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
    task.log(f"마인크래프트 {mc_version}에는 Java {javamod.install_target(required)}이(가) 필요합니다.")
    return javamod.ensure_java(required, auto_java, task)


# --------------------------------------------------------------- 서버 생성


def create_server(opts: CreateOptions, task: Optional[Task] = None) -> ServerMeta:
    task = task or Task()
    if not opts.eula_accepted:
        raise ServerError("마인크래프트 EULA에 동의해야 서버를 만들 수 있습니다.")
    if opts.world.mode == "import":
        find_world_root(Path(opts.world.import_path))  # 먼저 검사해서 실패를 빨리 알린다

    paths.ensure_dirs()
    folder = folder_name_for(opts.name)
    folder.mkdir(parents=True)
    task.log(f"서버 폴더: {folder}")
    try:
        provider = get_provider(opts.software)
        java = _java_for(opts.software, opts.mc_version, opts.auto_java, task)
        task.check()
        task.log(f"{provider.name} {opts.mc_version} 설치 중...")
        result = provider.install(folder, opts.mc_version, java, task)

        (folder / "eula.txt").write_text(
            "# https://aka.ms/MinecraftEULA (MC Server Maker에서 동의함)\neula=true\n", encoding="utf-8"
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
            task.log("맵 불러오는 중...")
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
        task.log("서버 만들기 완료!")
        return meta
    except BaseException:
        shutil.rmtree(folder, ignore_errors=True)
        raise


# ------------------------------------------------------------- 업그레이드


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
    task.log(f"{provider.name} {old_version} → {new_version} 업그레이드 중...")

    old_launch = meta.launch or {}
    result = provider.install(meta.folder, new_version, java, task)
    new_launch = result["launch"]
    # 이름이 다른 예전 실행 파일(Forge 구버전 jar 등) 정리
    if old_launch.get("type") == "jar" and old_launch != new_launch:
        old_jar = meta.folder / old_launch["jar"]
        if old_jar.name != new_launch.get("jar"):
            old_jar.unlink(missing_ok=True)

    props = meta.properties()
    if props.get("level-type"):
        # 1.19부터 level-type 값 형식이 바뀌었다
        props.set("level-type", level_type_value(parse_level_type(props.get("level-type")), new_version))
        props.save()

    meta.mc_version = new_version
    meta.build = result.get("build", "")
    meta.launch = new_launch
    meta.java_major = java.major
    meta.java_path = java.path
    meta.save()
    write_start_scripts(meta)
    task.log("업그레이드 완료! 서버를 켜면 월드가 새 버전으로 변환됩니다.")
    return meta


def change_java(meta: ServerMeta, auto_java: bool, task: Optional[Task] = None) -> ServerMeta:
    task = task or Task()
    java = _java_for(meta.software, meta.mc_version, auto_java, task)
    meta.java_major = java.major
    meta.java_path = java.path
    meta.save()
    write_start_scripts(meta)
    return meta


# ------------------------------------------------------------------ 백업


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
    task.log(f"백업 중... ({len(files)}개 파일)")
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        for i, f in enumerate(files):
            task.check()
            if f.name == "session.lock":
                continue
            z.write(f, f.relative_to(meta.folder).as_posix())
            task.progress(i + 1, len(files))
    task.log(f"백업 저장: {dest}")
    return dest


def list_backups(meta: ServerMeta) -> List[Path]:
    d = meta.folder / BACKUP_DIR
    return sorted(d.glob("*.zip"), reverse=True) if d.exists() else []


# ------------------------------------------------------------------ 월드


def find_world_root(src: Path) -> Path:
    """폴더/zip 안에서 level.dat 이 있는 위치를 찾는다 (폴더면 경로, zip이면 zip 경로)."""
    if not str(src).strip():
        raise ServerError("불러올 맵(폴더 또는 zip)을 선택해 주세요.")
    src = Path(src)
    if not src.exists():
        raise ServerError(f"맵 경로가 없습니다: {src}")
    if src.is_dir():
        if (src / "level.dat").exists():
            return src
        for sub in sorted(src.iterdir()):
            if sub.is_dir() and (sub / "level.dat").exists():
                return sub
        raise ServerError("선택한 폴더에서 level.dat 을 찾지 못했습니다. 맵(월드) 폴더를 골라 주세요.")
    if zipfile.is_zipfile(src):
        with zipfile.ZipFile(src) as z:
            if not any(n.endswith("level.dat") and n.count("/") <= 1 for n in z.namelist()):
                raise ServerError("zip 파일 안에 level.dat 이 없습니다.")
        return src
    raise ServerError("맵은 폴더 또는 .zip 파일이어야 합니다.")


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
                    raise ServerError("zip 파일 경로가 올바르지 않습니다.")
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
    task.log("맵 불러오는 중...")
    import_world(meta.folder, src, level)
    task.log("맵 불러오기 완료!")


def regenerate_world(meta: ServerMeta, seed: str, level_type: str, task: Optional[Task] = None) -> None:
    """기존 맵을 백업 후 지우고, 다음 실행 때 새 맵이 만들어지게 한다."""
    task = task or Task()
    if any(d.exists() for d in world_dirs(meta)):
        backup_server(meta, "world-before-reset", worlds_only=True, task=task)
    _remove_worlds(meta)
    props = meta.properties()
    props.set("level-seed", seed.strip())
    props.set("level-type", level_type_value(level_type, meta.mc_version))
    props.save()
    task.log("기존 맵을 지웠습니다. 서버를 켜면 새 맵이 만들어집니다.")


# ------------------------------------------------------------------ 기타


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # 실제로 패킷을 보내지 않음
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
