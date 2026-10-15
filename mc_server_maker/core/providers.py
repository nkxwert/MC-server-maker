"""Server software (Vanilla, Paper, Purpur, Fabric, Forge, NeoForge): version lists / install."""

import re
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

from mc_server_maker.core import net, versions
from mc_server_maker.core.java import NO_WINDOW, JavaInfo
from mc_server_maker.core.tasks import Task
from mc_server_maker.i18n import t


class ProviderError(Exception):
    pass


class Provider:
    id = ""
    name = ""
    short = ""  # one-line description shown on the picker card
    description = ""
    supports_plugins = False
    supports_mods = False

    def __init__(self):
        self._cache: Dict[bool, List[str]] = {}

    def list_versions(self, include_unstable: bool = False) -> List[str]:
        """Versions, newest first."""
        if include_unstable not in self._cache:
            self._cache[include_unstable] = self._list_versions(include_unstable)
        return self._cache[include_unstable]

    def _list_versions(self, include_unstable: bool) -> List[str]:
        raise NotImplementedError

    def java_hint(self, mc_version: str) -> Optional[int]:
        """Minimum Java required by the software itself (None if unknown)."""
        return None

    def install(self, server_dir: Path, mc_version: str, java: JavaInfo, task: Task) -> dict:
        """Install the server files and return launch info.

        Returns {"launch": {...}, "build": "build / loader version"} where launch is
        {"type": "jar", "jar": "server.jar"} or
        {"type": "args", "unix": "...unix_args.txt", "win": "...win_args.txt"}.
        """
        raise NotImplementedError


def _is_stable(v: str) -> bool:
    return "-" not in v


class VanillaProvider(Provider):
    id = "vanilla"
    name = "Vanilla"
    short = "Official server"
    description = "Mojang's official server. No plugins or mods."

    def _list_versions(self, include_unstable):
        manifest = versions.mojang_manifest()
        types = {"release", "snapshot"} if include_unstable else {"release"}
        # No server downloads exist before 1.2.5.
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
            raise ProviderError(t("Version {v} has no server download.", v=mc_version))
        net.download(server["url"], server_dir / "server.jar", task, sha1=server.get("sha1"))
        return {"launch": {"type": "jar", "jar": "server.jar"}, "build": ""}


class PaperProvider(Provider):
    id = "paper"
    name = "Paper"
    short = "Plugins · fast (recommended)"
    description = "Plugin support and better performance. Recommended for most servers."
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
            raise ProviderError(t("There are no Paper builds for {v} yet.", v=mc_version))
        stable = [b for b in builds if b.get("channel") == "STABLE"]
        build = max(stable or builds, key=lambda b: b["id"])
        dl = build["downloads"]["server:default"]
        if not stable:
            task.log(t("Note: Paper {v} only has experimental builds so far.", v=mc_version))
        net.download(
            dl["url"], server_dir / "server.jar", task, sha256=dl.get("checksums", {}).get("sha256")
        )
        return {"launch": {"type": "jar", "jar": "server.jar"}, "build": str(build["id"])}


class PurpurProvider(Provider):
    id = "purpur"
    name = "Purpur"
    short = "Paper + extra options"
    description = "Based on Paper with many extra settings. Plugin support."
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
    name = "Fabric"
    short = "Lightweight mods"
    description = "Lightweight mod loader. Put Fabric mods in the mods folder."
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
        # The Fabric launcher downloads the vanilla server.jar on first start.
        # Remove an old one so an upgrade fetches the new version.
        (server_dir / "server.jar").unlink(missing_ok=True)
        return {"launch": {"type": "jar", "jar": self.JAR}, "build": f"loader {loader}"}


class _InstallerProvider(Provider):
    """Shared logic for Forge / NeoForge, which ship an installer jar."""

    MAVEN = ""
    GROUP_PATH = ""  # e.g. net/minecraftforge/forge
    ARTIFACT = ""

    def loader_version(self, mc_version: str) -> str:
        raise NotImplementedError

    def _artifact_versions(self, mc_version: str, loader: str) -> List[str]:
        return [loader]

    def install(self, server_dir, mc_version, java, task):
        loader = self.loader_version(mc_version)
        full = None
        for candidate in self._artifact_versions(mc_version, loader):
            if net.exists(f"{self.MAVEN}/{candidate}/{self.ARTIFACT}-{candidate}-installer.jar"):
                full = candidate
                break
        if not full:
            raise ProviderError(t("Could not find the {name} {v} installer.", name=self.name, v=loader))
        installer = server_dir / f"{self.ARTIFACT}-{full}-installer.jar"
        net.download(f"{self.MAVEN}/{full}/{self.ARTIFACT}-{full}-installer.jar", installer, task)

        task.log(t("Running the {name} installer... (this can take a few minutes)", name=self.name))
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
            raise ProviderError(t("{name} install failed. See the log above.", name=self.name))
        installer.unlink(missing_ok=True)
        Path(str(installer) + ".log").unlink(missing_ok=True)

        # Modern versions start through libraries/.../unix_args.txt
        args_dir = server_dir / "libraries" / Path(self.GROUP_PATH) / full
        if (args_dir / "unix_args.txt").exists():
            rel = args_dir.relative_to(server_dir).as_posix()
            launch = {"type": "args", "unix": f"{rel}/unix_args.txt", "win": f"{rel}/win_args.txt"}
        else:
            jars = [
                p
                for p in server_dir.glob(f"{self.ARTIFACT}-*.jar")
                if "installer" not in p.name and loader in p.name
            ]
            if not jars:
                raise ProviderError(t("Installed {name} server file not found.", name=self.name))
            launch = {"type": "jar", "jar": jars[0].name}
        return {"launch": launch, "build": loader}


class ForgeProvider(_InstallerProvider):
    id = "forge"
    name = "Forge"
    short = "Classic mods"
    description = "The classic mod loader. Put Forge mods in the mods folder."
    supports_mods = True
    PROMOS = "https://files.minecraftforge.net/net/minecraftforge/forge/promotions_slim.json"
    MAVEN = "https://maven.minecraftforge.net/net/minecraftforge/forge"
    GROUP_PATH = "net/minecraftforge/forge"
    ARTIFACT = "forge"

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

    def loader_version(self, mc_version: str) -> str:
        promos = self._get_promos()
        fv = promos.get(f"{mc_version}-recommended") or promos.get(f"{mc_version}-latest")
        if not fv:
            raise ProviderError(t("Could not find Forge for {v}.", v=mc_version))
        return fv

    # kept for backwards compatibility with older callers/tests
    forge_version = loader_version

    def _artifact_versions(self, mc_version, loader):
        # Very old versions (1.7.10 etc.) use '1.7.10-10.13.4.1614-1.7.10'.
        return [f"{mc_version}-{loader}", f"{mc_version}-{loader}-{mc_version}"]


class NeoForgeProvider(_InstallerProvider):
    id = "neoforge"
    name = "NeoForge"
    short = "Modern mods"
    description = "Modern fork of Forge used by most new mods. Put NeoForge mods in the mods folder."
    supports_mods = True
    LIST = "https://maven.neoforged.net/api/maven/versions/releases/net/neoforged/neoforge"
    MAVEN = "https://maven.neoforged.net/releases/net/neoforged/neoforge"
    GROUP_PATH = "net/neoforged/neoforge"
    ARTIFACT = "neoforge"

    def __init__(self):
        super().__init__()
        self._all: Optional[List[str]] = None

    def _versions(self) -> List[str]:
        if self._all is None:
            self._all = [v for v in net.get_json(self.LIST).get("versions", []) if not v.startswith("0.")]
        return self._all

    @staticmethod
    def mc_version_of(neo: str) -> Optional[str]:
        """'21.1.77' -> '1.21.1', '21.0.5-beta' -> '1.21', '26.1.0.3' -> '26.1'."""
        nums = re.findall(r"\d+", neo.split("-")[0])
        if len(nums) < 2:
            return None
        major, minor = int(nums[0]), int(nums[1])
        if major >= 26:  # year-based versions: 26.1(.x)
            patch = int(nums[2]) if len(nums) > 3 else 0
            return f"{major}.{minor}" + (f".{patch}" if patch else "")
        return f"1.{major}" + (f".{minor}" if minor else "")

    def _list_versions(self, include_unstable):
        out = {}
        for v in self._versions():
            if not include_unstable and "-" in v:
                continue
            mc = self.mc_version_of(v)
            if mc:
                out[mc] = True
        return sorted(out, key=versions.version_key, reverse=True)

    def loader_version(self, mc_version: str) -> str:
        matches = [v for v in self._versions() if self.mc_version_of(v) == mc_version]
        if not matches:
            raise ProviderError(t("Could not find NeoForge for {v}.", v=mc_version))
        stable = [v for v in matches if "-" not in v]
        return max(stable or matches, key=versions.version_key)


PROVIDERS: List[Provider] = [
    PaperProvider(),
    VanillaProvider(),
    PurpurProvider(),
    FabricProvider(),
    NeoForgeProvider(),
    ForgeProvider(),
]


def get_provider(provider_id: str) -> Provider:
    for p in PROVIDERS:
        if p.id == provider_id:
            return p
    raise ProviderError(t("Unknown server software: {id}", id=provider_id))
