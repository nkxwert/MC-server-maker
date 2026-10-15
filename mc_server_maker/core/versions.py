"""마인크래프트 버전 비교 / 필요한 Java 버전 계산."""

import re
from typing import Optional

from mc_server_maker.core import net

MOJANG_MANIFEST = "https://piston-meta.mojang.com/mc/game/version_manifest_v2.json"

_manifest_cache: Optional[dict] = None
_version_json_cache: dict = {}


def version_key(v: str) -> tuple:
    """'1.21.1' < '1.21.2-pre1' < '1.21.2' < '26.1' 순서가 되도록 비교 키를 만든다."""
    main, _, suffix = v.partition("-")
    nums = tuple(int(n) for n in re.findall(r"\d+", main))
    suffix_nums = tuple(int(n) for n in re.findall(r"\d+", suffix))
    return (nums, 0 if suffix else 1, suffix_nums)


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
    """이 마인크래프트 버전을 실행하는 데 필요한 최소 Java 버전."""
    try:
        data = mojang_version_json(mc_version)
        if data and data.get("javaVersion"):
            return int(data["javaVersion"]["majorVersion"])
    except net.NetError:
        pass
    # Mojang 목록에 없거나(구 버전 등) 연결 실패 시 추정값 사용
    return _guess_java(mc_version)
