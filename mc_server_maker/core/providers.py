"""서버 구동기(Vanilla, Paper, Purpur, Fabric, Forge)별 버전 목록 / 설치."""

import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from mc_server_maker.core import net, versions
from mc_server_maker.core.java import NO_WINDOW, JavaInfo
from mc_server_maker.core.tasks import Task


class ProviderError(Exception):
    pass


class Provider:
    id = ""
    name = ""
    description = ""
    short = ""  # 카드에 표시할 짧은 설명
    supports_plugins = False
    supports_mods = False

    def __init__(self):
        self._cache: Dict[bool, List[str]] = {}

    def list_versions(self, include_unstable: bool = False) -> List[str]:
        """최신 버전이 앞에 오는 버전 목록."""
        if include_unstable not in self._cache:
            self._cache[include_unstable] = self._list_versions(include_unstable)
        return self._cache[include_unstable]

    def _list_versions(self, include_unstable: bool) -> List[str]:
        raise NotImplementedError

    def java_hint(self, mc_version: str) -> Optional[int]:
        """구동기가 따로 요구하는 최소 Java 버전 (없으면 None)."""
        return None

    def install(self, server_dir: Path, mc_version: str, java: JavaInfo, task: Task) -> dict:
        """서버 파일을 설치하고 실행 정보를 돌려준다.

        반환값: {"launch": {...}, "build": "빌드/로더 버전"}
        launch는 {"type": "jar", "jar": "server.jar"} 또는
        {"type": "args", "unix": "...unix_args.txt", "win": "...win_args.txt"}
        """
        raise NotImplementedError


def _is_stable(v: str) -> bool:
    return "-" not in v


class VanillaProvider(Provider):
    id = "vanilla"
    name = "Vanilla (바닐라)"
    short = "순정 공식 서버"
    description = "Mojang 공식 서버. 플러그인/모드 없이 순정 그대로."

    def _list_versions(self, include_unstable):
        manifest = versions.mojang_manifest()
        types = {"release", "snapshot"} if include_unstable else {"release"}
        # 1.2.5 이전에는 서버 파일이 제공되지 않는다.
        out = []
        for v in manifest["versions"]:
            if v["type"] in types:
                out.append(v["id"])
            if v["id"] == "1.2.5":
                break
        return out

    def install(self, server_dir, mc_version, java, task):
        data = versions.mojang_version_json(mc_version)
        server = (data or {}).get("downloads", {}).get("server")
        if not server:
            raise ProviderError(f"{mc_version} 버전은 서버 파일을 제공하지 않습니다.")
        net.download(server["url"], server_dir / "server.jar", task, sha1=server.get("sha1"))
        return {"launch": {"type": "jar", "jar": "server.jar"}, "build": ""}


class PaperProvider(Provider):
    id = "paper"
    name = "Paper (추천)"
    short = "플러그인 · 최적화"
    description = "플러그인 지원 + 최적화. 대부분의 서버에 추천."
    supports_plugins = True
    API = "https://fill.papermc.io/v3/projects/paper"

    def _list_versions(self, include_unstable):
        data = net.get_json(self.API)
        raw = data.get("versions", [])
        if isinstance(raw, dict):  # {"1.21": ["1.21.8", ...], ...}
            raw = [v for group in raw.values() for v in group]
        out = [v for v in raw if include_unstable or _is_stable(v)]
        return sorted(set(out), key=versions.version_key, reverse=True)

    def java_hint(self, mc_version):
        try:
            data = net.get_json(f"{self.API}/versions/{mc_version}")
            return int(data["version"]["java"]["version"]["minimum"])
        except (net.NetError, KeyError, TypeError, ValueError):
            return None

    def install(self, server_dir, mc_version, java, task):
        builds = net.get_json(f"{self.API}/versions/{mc_version}/builds")
        if not builds:
            raise ProviderError(f"Paper {mc_version} 빌드가 아직 없습니다.")
        stable = [b for b in builds if b.get("channel") == "STABLE"]
        build = max(stable or builds, key=lambda b: b["id"])
        dl = build["downloads"]["server:default"]
        if not stable:
            task.log(f"주의: Paper {mc_version}은(는) 아직 실험 빌드만 있습니다.")
        net.download(
            dl["url"], server_dir / "server.jar", task, sha256=dl.get("checksums", {}).get("sha256")
        )
        return {"launch": {"type": "jar", "jar": "server.jar"}, "build": str(build["id"])}


class PurpurProvider(Provider):
    id = "purpur"
    name = "Purpur"
    short = "Paper + 추가 설정"
    description = "Paper 기반 + 추가 설정이 많은 서버. 플러그인 지원."
    supports_plugins = True
    API = "https://api.purpurmc.org/v2/purpur"

    def _list_versions(self, include_unstable):
        data = net.get_json(self.API)
        out = [v for v in data.get("versions", []) if include_unstable or _is_stable(v)]
        return sorted(set(out), key=versions.version_key, reverse=True)

    def install(self, server_dir, mc_version, java, task):
        info = net.get_json(f"{self.API}/{mc_version}/latest")
        build = str(info.get("build", "latest"))
        net.download(
            f"{self.API}/{mc_version}/{build}/download",
            server_dir / "server.jar",
            task,
            md5=info.get("md5"),
        )
        return {"launch": {"type": "jar", "jar": "server.jar"}, "build": build}


class FabricProvider(Provider):
    id = "fabric"
    name = "Fabric (모드)"
    short = "가벼운 모드 서버"
    description = "가벼운 모드 서버. mods 폴더에 Fabric 모드를 넣어 사용."
    supports_mods = True
    API = "https://meta.fabricmc.net/v2"
    JAR = "fabric-server-launch.jar"

    def _list_versions(self, include_unstable):
        data = net.get_json(f"{self.API}/versions/game")
        return [v["version"] for v in data if include_unstable or v.get("stable")]

    @staticmethod
    def _latest(items: list) -> str:
        stable = [i for i in items if i.get("stable")]
        return (stable or items)[0]["version"]

    def install(self, server_dir, mc_version, java, task):
        loader = self._latest(net.get_json(f"{self.API}/versions/loader"))
        installer = self._latest(net.get_json(f"{self.API}/versions/installer"))
        url = f"{self.API}/versions/loader/{mc_version}/{loader}/{installer}/server/jar"
        net.download(url, server_dir / self.JAR, task)
        # Fabric 실행기는 첫 실행 때 server.jar(바닐라)를 직접 받는다.
        # 업그레이드 시 예전 버전의 server.jar가 남아 있으면 지운다.
        (server_dir / "server.jar").unlink(missing_ok=True)
        return {"launch": {"type": "jar", "jar": self.JAR}, "build": f"loader {loader}"}


class ForgeProvider(Provider):
    id = "forge"
    name = "Forge (모드)"
    short = "대표 모드 서버"
    description = "가장 오래된 모드 서버. mods 폴더에 Forge 모드를 넣어 사용."
    supports_mods = True
    PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
    MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"

    def __init__(self):
        super().__init__()
        self._promos: Optional[dict] = None

    def _get_promos(self) -> dict:
        if self._promos is None:
            self._promos = net.get_json(self.PROMOS).get("promos", {})
        return self._promos

    def _list_versions(self, include_unstable):
        mc = {k.rsplit("-", 1)[0] for k in self._get_promos()}
        out = [v for v in mc if include_unstable or _is_stable(v)]
        return sorted(out, key=versions.version_key, reverse=True)

    def forge_version(self, mc_version: str) -> str:
        promos = self._get_promos()
        fv = promos.get(f"{mc_version}-recommended") or promos.get(f"{mc_version}-latest")
        if not fv:
            raise ProviderError(f"Forge {mc_version} 버전을 찾지 못했습니다.")
        return fv

    def install(self, server_dir, mc_version, java, task):
        fv = self.forge_version(mc_version)
        # 아주 오래된 버전(1.7.10 등)은 '1.7.10-10.13.4.1614-1.7.10' 형식을 쓴다.
        full = None
        for candidate in (f"{mc_version}-{fv}", f"{mc_version}-{fv}-{mc_version}"):
            if net.exists(f"{self.MAVEN}/{candidate}/forge-{candidate}-installer.jar"):
                full = candidate
                break
        if not full:
            raise ProviderError(f"Forge {mc_version}-{fv} 설치 파일을 찾지 못했습니다.")
        installer = server_dir / f"forge-{full}-installer.jar"
        net.download(f"{self.MAVEN}/{full}/forge-{full}-installer.jar", installer, task)

        task.log("Forge 설치 프로그램 실행 중... (몇 분 걸릴 수 있어요)")
        proc = subprocess.Popen(
            [java.path, "-jar", installer.name, "--installServer"],
            cwd=server_dir,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            errors="replace",
            creationflags=NO_WINDOW,
        )
        for line in proc.stdout:
            line = line.rstrip()
            if line:
                task.log("  " + line)
            if task.cancelled:
                proc.kill()
                task.check()
        if proc.wait() != 0:
            raise ProviderError("Forge 설치에 실패했습니다. 위 로그를 확인해 주세요.")
        installer.unlink(missing_ok=True)
        Path(str(installer) + ".log").unlink(missing_ok=True)

        # 1.17 이상: libraries/.../unix_args.txt 로 실행
        args_dir = server_dir / "libraries" / "net" / "minecraftforge" / "forge" / full
        if (args_dir / "unix_args.txt").exists():
            rel = args_dir.relative_to(server_dir).as_posix()
            launch = {"type": "args", "unix": f"{rel}/unix_args.txt", "win": f"{rel}/win_args.txt"}
        else:
            jars = [
                p
                for p in server_dir.glob("forge-*.jar")
                if "installer" not in p.name and full.split("-")[1] in p.name
            ]
            if not jars:
                raise ProviderError("설치된 Forge 서버 파일을 찾지 못했습니다.")
            launch = {"type": "jar", "jar": jars[0].name}
        return {"launch": launch, "build": fv}


PROVIDERS: List[Provider] = [
    PaperProvider(),
    VanillaProvider(),
    PurpurProvider(),
    FabricProvider(),
    ForgeProvider(),
]


def get_provider(provider_id: str) -> Provider:
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    raise ProviderError(f"알 수 없는 구동기: {provider_id}")
