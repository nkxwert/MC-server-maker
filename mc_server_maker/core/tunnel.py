"""playit.gg tunnel: friends join without port forwarding.

The playit agent (an official open-source program) is downloaded into
runtime/playit/ and run in the background. On first use it prints a claim link;
the user approves this PC on playit.gg and adds a Minecraft tunnel there. After
that the agent keeps the tunnel up and logs its public address.
"""

import os
import platform
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from mc_server_maker.core import net, paths
from mc_server_maker.core.tasks import Task
from mc_server_maker.i18n import t

# playit 1.0 split the agent into a background service (playitd) plus a separate CLI; its
# Windows download is only the service, which doesn't understand this command line (it exits
# with code 2). 0.17.1 is the last standalone agent, and playit still supports it.
AGENT_VERSION = "v0.17.1"
RELEASES = f"https://api.github.com/repos/playit-cloud/playit-agent/releases/tags/{AGENT_VERSION}"
DASHBOARD = "https://playit.gg/account/tunnels"
CLAIM_RE = re.compile(r"https://playit\.gg/(?:claim|mc)/[A-Za-z0-9_-]+")
# public tunnel addresses look like "name.gl.joinmc.link" or "name.ply.gg:12345"
ADDRESS_RE = re.compile(r"\b((?:[a-z0-9-]+\.)+(?:joinmc\.link|ply\.gg)(?::\d{2,5})?)\b", re.IGNORECASE)


class TunnelError(Exception):
    pass


def agent_dir() -> Path:
    return paths.RUNTIME_DIR / "playit"


def agent_path() -> Path:
    return agent_dir() / ("playit.exe" if os.name == "nt" else "playit")


def secret_path() -> Path:
    return agent_dir() / "playit.toml"


def version_path() -> Path:
    return agent_dir() / "version.txt"


def is_installed() -> bool:
    """The right agent version is downloaded (an older app may have fetched playit 1.x)."""
    try:
        return agent_path().exists() and version_path().read_text(encoding="utf-8").strip() == AGENT_VERSION
    except OSError:
        return False


def remove_agent() -> None:
    for p in (agent_path(), version_path()):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


def is_claimed() -> bool:
    return secret_path().exists() and secret_path().stat().st_size > 0


def pick_asset(assets: List[dict], system: str, machine: str) -> Optional[dict]:
    """Choose the agent download for this OS/CPU from a GitHub release."""
    system, machine = system.lower(), machine.lower()
    arm = machine in ("arm64", "aarch64")
    names = [(a, a.get("name", "").lower()) for a in assets]
    if system == "windows":
        cands = [a for a, n in names if "windows" in n and n.endswith(".exe") and ("x86_64" in n or "amd64" in n)]
        cands.sort(key=lambda a: "signed" not in a["name"].lower())
    elif system == "linux":
        want = ("aarch64", "arm64") if arm else ("amd64", "x86_64")
        cands = [a for a, n in names if "linux" in n and any(w in n for w in want)
                 and not n.endswith((".deb", ".rpm", ".sha256", ".sig"))]
    elif system == "darwin":
        cands = [a for a, n in names if any(k in n for k in ("darwin", "macos", "apple"))
                 and not n.endswith((".sha256", ".sig", ".dmg", ".pkg"))]
    else:
        cands = []
    return cands[0] if cands else None


def install_agent(task: Optional[Task] = None) -> Path:
    task = task or Task()
    task.log(t("Downloading the playit.gg agent..."))
    release = net.get_json(RELEASES)
    asset = pick_asset(release.get("assets", []), platform.system(), platform.machine())
    if not asset:
        raise TunnelError(t("playit.gg has no agent for this system. Install it from playit.gg/download."))
    dest = agent_path()
    digest = str(asset.get("digest") or "")  # GitHub: "sha256:<hex>"
    net.download(asset["browser_download_url"], dest, task,
                 sha256=digest.split(":", 1)[1] if digest.startswith("sha256:") else None)
    if os.name != "nt":
        dest.chmod(0o755)
    version_path().write_text(AGENT_VERSION, encoding="utf-8")
    task.log(t("playit.gg agent {v} installed.", v=release.get("tag_name", "")))
    return dest


# Agent command lines to try, newest syntax first (the CLI has changed between versions).
def command_variants() -> List[List[str]]:
    exe, secret = str(agent_path()), str(secret_path())
    return [
        [exe, "--secret_path", secret, "--stdout", "start"],
        [exe, "--secret-path", secret, "--stdout", "start"],
        [exe, "--secret_path", secret, "-s"],
    ]


def find_claim_url(text: str) -> Optional[str]:
    m = CLAIM_RE.search(text)
    return m.group(0) if m else None


def find_address(text: str) -> Optional[str]:
    """The Java tunnel address in the agent's output (Bedrock tunnel lines are skipped)."""
    found = []
    for line in text.splitlines():
        low = line.lower()
        if "bedrock" in low or ":19132" in low or "udp" in low:
            continue  # the Bedrock tunnel must not replace the Java address
        found += [m.group(1).lower() for m in ADDRESS_RE.finditer(line)]
    # "*.joinmc.link" is playit's Minecraft Java address; prefer it over plain ply.gg ones
    return next((a for a in found if "joinmc.link" in a), found[0] if found else None)


# ---- tunnel addresses from playit's API
# In --stdout mode the 0.17 agent logs only the first line of its status ("N tunnels
# registered"), never the addresses; the agent itself asks the API for them, so we do too.
API_RUNDATA = "https://api.playit.gg/v1/agents/rundata"


@dataclass
class PlayitTunnel:
    address: str
    kind: str  # "minecraft-java", "minecraft-bedrock", ... ("" if unknown)
    port_type: str  # tcp / udp / both
    local_port: Optional[int]
    disabled: str  # reason, "" if it works


def read_secret() -> str:
    """The agent's secret key from playit.toml (written after this PC was approved)."""
    try:
        text = secret_path().read_text(encoding="utf-8")
    except OSError:
        return ""
    m = re.search(r'secret_key\s*=\s*["\']([0-9a-fA-F]+)["\']', text)
    return m.group(1) if m else ""


def parse_rundata(data: dict) -> List[PlayitTunnel]:
    if not isinstance(data, dict) or data.get("status") != "success":
        raise TunnelError(t("playit.gg didn't send the tunnel list."))
    tunnels = []
    for tun in (data.get("data") or {}).get("tunnels") or []:
        fields = {f.get("name"): f.get("value") for f in ((tun.get("agent_config") or {}).get("fields") or [])}
        try:
            local_port = int(fields.get("local_port")) if fields.get("local_port") else None
        except (TypeError, ValueError):
            local_port = None
        tunnels.append(PlayitTunnel(
            address=str(tun.get("display_address") or ""),
            kind=str(tun.get("tunnel_type") or "").lower(),
            port_type=str(tun.get("port_type") or "").lower(),
            local_port=local_port,
            disabled=str(tun.get("disabled_reason") or ""),
        ))
    return tunnels


def fetch_tunnels(secret: str) -> List[PlayitTunnel]:
    data = net.post_json(API_RUNDATA, {}, headers={"Authorization": f"Agent-Key {secret}"})
    return parse_rundata(data)


def java_address(tunnels: List[PlayitTunnel], server_port: Optional[int] = None) -> str:
    """The address friends use for Java Edition: a working, non-Bedrock (TCP) tunnel,
    preferring one that points at this server's port."""
    def is_java(tun: PlayitTunnel) -> bool:
        if tun.disabled or not tun.address:
            return False
        if "bedrock" in tun.kind or tun.port_type == "udp":
            return False
        return True

    # a tunnel to another local port leads to another server: never offer it for this one
    usable = [tun for tun in tunnels if is_java(tun)
              and (server_port is None or tun.local_port in (None, server_port))]
    usable.sort(key=lambda tun: (
        tun.local_port is None,  # the one known to point at this port first
        "minecraft-java" not in tun.kind,
    ))
    return usable[0].address if usable else ""
