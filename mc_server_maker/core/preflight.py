"""Checks before a start that catch the common reasons a server stops right away.

Only real problems are reported: a port that is taken (error), and memory or disk space that look too
small (warnings, since what's free changes all the time). Nothing is changed or stopped here.
"""

import shutil
import socket
from dataclasses import dataclass
from typing import Dict, List, Optional

from mc_server_maker.i18n import t

MIN_FREE_DISK = 1 << 30  # 1 GB: worlds grow, backups and logs need room


@dataclass
class Issue:
    kind: str  # port / memory / disk
    error: bool  # True: the server can't start like this; False: it may work, but likely badly
    title: str
    detail: str
    fix: str = ""  # port / memory
    fix_label: str = ""
    value: int = 0  # the suggested port / memory in GB


def port_free(port: int) -> bool:
    """Can a server listen on this TCP port right now?"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("0.0.0.0", port))
            return True
        except OSError:
            return False


def next_free_port(port: int, taken: List[int]) -> int:
    for p in range(port + 1, min(port + 200, 65535)):
        if p not in taken and port_free(p):
            return p
    return 0


def check(port: int, ram_mb: int, folder, running_ports: Dict[str, int], all_ports: List[int],
          available_mb: Optional[int] = None) -> List[Issue]:
    """running_ports: other running servers of this app (name -> port); all_ports: every server's port."""
    issues: List[Issue] = []
    clash = next((name for name, p in running_ports.items() if p == port), None)
    if clash or not port_free(port):
        new = next_free_port(port, all_ports + list(running_ports.values()))
        issues.append(Issue(
            "port", True,
            t("Port {port} is used by '{name}'", port=port, name=clash) if clash
            else t("Port {port} is used by another program", port=port),
            t("Two servers can't listen on the same port at the same time."),
            "port" if new else "", t("Use port {port}", port=new) if new else "", new))
    if available_mb is None:
        try:
            import psutil

            available_mb = int(psutil.virtual_memory().available / (1 << 20))
        except Exception:  # noqa: BLE001 - no reading: no warning
            available_mb = None
    if available_mb is not None and ram_mb > available_mb:
        fit = max(1, (available_mb - 512) // 1024)
        issues.append(Issue(
            "memory", False, t("Not much free memory"),
            t("The server is set to use {ram} GB, but only {free:.1f} GB is free right now. "
              "Close other programs or give the server less.", ram=ram_mb // 1024, free=available_mb / 1024),
            "memory" if fit * 1024 < ram_mb else "", t("Use {gb} GB", gb=fit), fit))
    try:
        free = shutil.disk_usage(folder).free
    except OSError:
        free = None
    if free is not None and free < MIN_FREE_DISK:
        issues.append(Issue(
            "disk", False, t("The disk is almost full"),
            t("Only {mb} MB is free. The world can't be saved properly when the disk is full.", mb=free >> 20)))
    return issues
