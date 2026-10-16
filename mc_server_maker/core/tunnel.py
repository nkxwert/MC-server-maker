"""playit.gg tunnel: friends join without port forwarding.

The playit agent (an official open-source program) is downloaded into
runtime/playit/ and run in the background. On first use it prints a claim link;
the user approves this PC on playit.gg and adds a Minecraft tunnel there. After
that the agent keeps the tunnel up and logs its public address.
"""

import os
import platform
import re
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
