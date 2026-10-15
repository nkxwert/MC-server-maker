"""OP / 화이트리스트 (서버가 꺼져 있을 때 ops.json, whitelist.json 직접 편집)."""

import hashlib
import json
import uuid
from pathlib import Path
from typing import List

from mc_server_maker.core import net

MOJANG_PROFILE = "https://api.mojang.com/users/profiles/minecraft/{}"


class PlayerError(Exception):
    pass


def offline_uuid(name: str) -> str:
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def lookup_uuid(name: str, online_mode: bool) -> tuple:
    """(정확한 이름, uuid)"""
    if not online_mode:
        return name, offline_uuid(name)
    try:
        data = net.get_json(MOJANG_PROFILE.format(name))
    except net.NetError as e:
        raise PlayerError(f"'{name}' 플레이어를 찾지 못했습니다. ({e})") from e
    if not data or "id" not in data:
        raise PlayerError(f"'{name}' 플레이어를 찾지 못했습니다.")
    return data["name"], str(uuid.UUID(data["id"]))


def _read(path: Path) -> List[dict]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8") or "[]")
        return data if isinstance(data, list) else []
    except ValueError:
        return []


def _write(path: Path, data: List[dict]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_names(server_dir: Path, kind: str) -> List[str]:
    return [e.get("name", "?") for e in _read(Path(server_dir) / f"{kind}.json")]


def add(server_dir: Path, kind: str, name: str, online_mode: bool) -> str:
    """kind: 'ops' 또는 'whitelist'."""
    path = Path(server_dir) / f"{kind}.json"
    data = _read(path)
    real_name, pid = lookup_uuid(name, online_mode)
    if any(e.get("uuid") == pid for e in data):
        return real_name
    entry = {"uuid": pid, "name": real_name}
    if kind == "ops":
        entry.update(level=4, bypassesPlayerLimit=False)
    data.append(entry)
    _write(path, data)
    return real_name


def remove(server_dir: Path, kind: str, name: str) -> None:
    path = Path(server_dir) / f"{kind}.json"
    data = [e for e in _read(path) if e.get("name", "").lower() != name.lower()]
    _write(path, data)
