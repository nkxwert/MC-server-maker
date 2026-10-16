"""Minecraft version ordering / required Java version."""

import re
from typing import Optional

from mc_server_maker.core import net

MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

_manifest_cache: Optional[dict] = None
_version_json_cache: dict = {}


def version_key(v: str) -> tuple:
    """Sort key so that '1.21.1' < '1.21.2-pre1' < '1.21.2' < '26.1'."""
    weekly = re.fullmatch(r"(\d{2})w(\d{2})([a-z]?)", v.strip().lower())
    if weekly:  # "25w14a": a snapshot
        base = _release_before(v.strip().lower())
        if base:  # right after the release it follows (Mojang's list knows the dates)
            return (version_key(base)[0], 1, (0, int(weekly.group(1)), int(weekly.group(2)), ord(weekly.group(3) or "a")))
        # unknown date: below every release (never wrongly "newer than 1.21")
        return ((0, int(weekly.group(1)), int(weekly.group(2))), 0, (ord(weekly.group(3) or "a"),))
    main, _, suffix = v.partition("-")
    nums = tuple(int(n) for n in re.findall(r"\d+", main))
    suffix_nums = tuple(int(n) for n in re.findall(r"\d+", suffix))
    low = suffix.lower()
    kind = 0 if not suffix else 3 if "rc" in low else 2 if "pre" in low else 1  # snapshot < pre < rc
    return (nums, 0 if suffix else 1, (kind,) + suffix_nums)


def _release_before(snapshot: str) -> str:
    """The newest release older than this weekly snapshot, from Mojang's list if it was loaded."""
    entries = (_manifest_cache or {}).get("versions") or []
    when = next((e.get("releaseTime", "") for e in entries if e.get("id") == snapshot), "")
    if not when:
        return ""
    older = [e for e in entries if e.get("type") == "release" and e.get("releaseTime", "") < when]
    return max(older, key=lambda e: e.get("releaseTime", ""))["id"] if older else ""


def is_at_least(v: str, target: str) -> bool:
    return version_key(v)[0] >= version_key(target)[0]


def mojang_manifest() -> dict:
    global _manifest_cache
    if _manifest_cache is None:
        _manifest_cache = net.get_json(MOJANG_MANIFEST)
    return _manifest_cache


def mojang_version_json(mc_version: str) -> Optional[dict]:
    if mc_version in _version_json_cache:
        return _version_json_cache[mc_version]
    for entry in mojang_manifest()["versions"]:
        if entry["id"] == mc_version:
            data = net.get_json(entry["url"])
            _version_json_cache[mc_version] = data
            return data
    return None


def _guess_java(mc_version: str) -> int:
    if is_at_least(mc_version, "26"):
        return 25
    if is_at_least(mc_version, "1.20.5"):
        return 21
    if is_at_least(mc_version, "1.18"):
        return 17
    if is_at_least(mc_version, "1.17"):
        return 16
    return 8


def required_java(mc_version: str) -> int:
    """Minimum Java version for this Minecraft version."""
    try:
        data = mojang_version_json(mc_version)
        if data and data.get("javaVersion"):
            return int(data["javaVersion"]["majorVersion"])
    except net.NetError:
        pass
    # fall back to an estimate when Mojang has no data or is unreachable
    return _guess_java(mc_version)
