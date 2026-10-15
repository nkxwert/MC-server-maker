"""OPs / whitelist (edits ops.json and whitelist.json while the server is stopped)."""

import hashlib
import json
import uuid
from pathlib import Path
from typing import List

from mc_server_maker.core import net
from mc_server_maker.i18n import t

MOJANG_PROFILE = "https://api.mojang.com/users/profiles/minecraft/{}"


class PlayerError(Exception):
    pass


def offline_uuid(name: str) -> str:
    digest = bytearray(hashlib.md5(f"OfflinePlayer:{name}".encode("utf-8")).digest())
    digest[6] = (digest[6] & 0x0F) | 0x30
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


def lookup_uuid(name: str, online_mode: bool) -> tuple:
    """(exact name, uuid)"""
    if not online_mode:
        return name, offline_uuid(name)
    try:
        data = net.get_json(MOJANG_PROFILE.format(name))
    except net.NetError as e:
        raise PlayerError(t("Player '{name}' not found. ({err})", name=name, err=e)) from e
    if not data or "id" not in data:
        raise PlayerError(t("Player '{name}' not found.", name=name))
    return data["name"], str(uuid.UUID(data["id"]))


def _read(path: Path, strict: bool = False) -> List[dict]:
    """The list in ops.json / whitelist.json. strict: raise on a broken file instead of
    treating it as empty, so adding/removing never overwrites entries we couldn't read."""
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig").strip() or "[]")  # -sig: tolerate a BOM
        if not isinstance(data, list):
            raise ValueError("not a list")
        return [e for e in data if isinstance(e, dict)]
    except (ValueError, OSError) as e:
        if strict:
            raise PlayerError(t("{file} can't be read ({err}). Fix or delete it, then try again.",
                                file=path.name, err=e)) from e
        return []


def _write(path: Path, data: List[dict]) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def list_names(server_dir: Path, kind: str) -> List[str]:
    return [e.get("name", "?") for e in _read(Path(server_dir) / f"{kind}.json")]


def add(server_dir: Path, kind: str, name: str, online_mode: bool) -> str:
    """kind: 'ops' or 'whitelist'."""
    path = Path(server_dir) / f"{kind}.json"
    data = _read(path, strict=True)
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
    data = [e for e in _read(path, strict=True) if str(e.get("name", "")).lower() != name.lower()]
    _write(path, data)
