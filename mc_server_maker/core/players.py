"""OPs / whitelist / bans (edits ops.json, whitelist.json and banned-players.json while the server is stopped)."""

import hashlib
import json
import os
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional

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
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def list_names(server_dir: Path, kind: str) -> List[str]:
    return [e.get("name", "?") for e in _read(Path(server_dir) / f"{kind}.json")]


def add(server_dir: Path, kind: str, name: str, online_mode: bool) -> str:
    """kind: 'ops' or 'whitelist'."""
    path = Path(server_dir) / f"{kind}.json"
    data = _read(path, strict=True)
    real_name, pid = _resolve(server_dir, name, online_mode)
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


# ---------------------------------------------------- everyone, for the player manager

BANNED = "banned-players"
RECENT_LIMIT = 20  # players from usercache.json shown besides the ones on a list


@dataclass
class Player:
    name: str
    uuid: str = ""
    online: bool = False
    op: bool = False
    whitelisted: bool = False
    banned: bool = False
    ban_reason: str = ""


def known_uuid(server_dir: Path, name: str) -> Optional[tuple]:
    """(exact name, uuid) of a player this server already knows (a list or usercache.json),
    so giving OP to someone who played here needs no lookup."""
    for kind in ("whitelist", "ops", BANNED, "usercache"):
        for e in _read(Path(server_dir) / f"{kind}.json"):
            if str(e.get("name", "")).lower() == name.lower() and e.get("uuid"):
                return e["name"], e["uuid"]
    return None


def _resolve(server_dir: Path, name: str, online_mode: bool) -> tuple:
    if not online_mode:  # computed from the name, nothing to look up
        return lookup_uuid(name, False)
    known = known_uuid(server_dir, name)
    if known and _offline_id(known[1]):
        known = None  # left from an offline run: the real account has another UUID
    return known or lookup_uuid(name, True)


def _offline_id(pid: str) -> bool:
    """A name-based (version 3) UUID: what offline mode gives, never a real Minecraft account."""
    try:
        return uuid.UUID(str(pid)).version == 3
    except ValueError:
        return False


def ban(server_dir: Path, name: str, online_mode: bool, reason: str = "") -> str:
    """Add to banned-players.json (the server is stopped)."""
    path = Path(server_dir) / f"{BANNED}.json"
    data = _read(path, strict=True)
    real_name, pid = _resolve(server_dir, name, online_mode)
    data = [e for e in data if e.get("uuid") != pid]
    data.append({"uuid": pid, "name": real_name, "created": time.strftime("%Y-%m-%d %H:%M:%S %z"),
                 "source": "Server", "expires": "forever", "reason": reason or "Banned by an operator."})
    _write(path, data)
    return real_name


def pardon(server_dir: Path, name: str) -> None:
    remove(server_dir, BANNED, name)


def roster(server_dir: Path, online: Iterable[str] = (), recent: int = RECENT_LIMIT) -> List[Player]:
    """Online players, everyone on a list, and who played here lately: online first, then by name."""
    server_dir = Path(server_dir)
    people: Dict[str, Player] = {}

    def get(name: str, pid: str = "") -> Player:
        p = people.setdefault(name.lower(), Player(name))
        p.uuid = p.uuid or pid
        return p

    for name in online:
        get(name).online = True
    for e in _read(server_dir / "ops.json"):
        get(str(e.get("name", "?")), e.get("uuid", "")).op = True
    for e in _read(server_dir / "whitelist.json"):
        get(str(e.get("name", "?")), e.get("uuid", "")).whitelisted = True
    for e in _read(server_dir / f"{BANNED}.json"):
        p = get(str(e.get("name", "?")), e.get("uuid", ""))
        p.banned, p.ban_reason = True, str(e.get("reason", ""))
    # usercache.json: everyone who joined, expiring a month after their last visit
    cache = sorted(_read(server_dir / "usercache.json"), key=lambda e: str(e.get("expiresOn", "")), reverse=True)
    for e in cache[:recent]:
        if e.get("name"):
            get(str(e["name"]), e.get("uuid", ""))
    return sorted(people.values(), key=lambda p: (not p.online, p.name.lower()))
