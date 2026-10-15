"""Resource usage of a running server: CPU, memory, network, disk, player ping."""

import ipaddress
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional

import psutil

NO_WINDOW = 0x08000000 if os.name == "nt" else 0


@dataclass
class Sample:
    cpu_percent: float = 0.0  # share of the whole PC (0-100)
    memory_bytes: int = 0
    net_recv_per_s: float = 0.0  # whole PC
    net_sent_per_s: float = 0.0


class ProcessMonitor:
    """Sample one server process. Call sample() every few seconds."""

    def __init__(self, pid: int):
        self.proc = psutil.Process(pid)
        self.cpus = psutil.cpu_count() or 1
        self.proc.cpu_percent(None)  # prime the counter
        self._net = psutil.net_io_counters()
        self._t = time.monotonic()

    def _tree(self):
        try:
            return [self.proc] + self.proc.children(recursive=True)
        except psutil.Error:
            return [self.proc]

    def sample(self) -> Optional[Sample]:
        try:
            procs = self._tree()
            cpu = sum(p.cpu_percent(None) for p in procs) / self.cpus
            mem = sum(p.memory_info().rss for p in procs)
        except psutil.Error:
            return None
        now = time.monotonic()
        net = psutil.net_io_counters()
        dt = max(now - self._t, 1e-3)
        recv = (net.bytes_recv - self._net.bytes_recv) / dt
        sent = (net.bytes_sent - self._net.bytes_sent) / dt
        self._net, self._t = net, now
        return Sample(min(cpu, 100.0), mem, max(recv, 0.0), max(sent, 0.0))

    def lower_priority(self) -> bool:
        """Run the server below normal priority so the PC stays responsive."""
        try:
            if os.name == "nt":
                self.proc.nice(psutil.BELOW_NORMAL_PRIORITY_CLASS)
            else:
                self.proc.nice(10)
            return True
        except (psutil.Error, OSError):
            return False


def folder_size(path: Path) -> int:
    total = 0
    for root, _dirs, files in os.walk(path):
        for f in files:
            try:
                total += os.path.getsize(os.path.join(root, f))
            except OSError:
                pass
    return total


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} GB"


# "time=12.3 ms", "time<1ms", "시간=12ms", "Zeit=12ms", "время=12мс" ... (any language)
_PING_RE = re.compile(r"[=<]\s*([\d.]+)\s*(?:ms|мс)", re.IGNORECASE)


def ping_ms(ip: str, timeout_s: int = 1) -> Optional[float]:
    """Round-trip time to an IP using the system ping command (no admin needed)."""
    try:
        ipaddress.ip_address(ip)  # never pass anything else to the shell command
    except ValueError:
        return None
    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", str(timeout_s * 1000), ip]
    elif sys.platform == "darwin":
        cmd = ["ping", "-c", "1", "-t", str(timeout_s), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout_s), ip]
    try:
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 2,
                             creationflags=NO_WINDOW, errors="replace")
    except (OSError, subprocess.TimeoutExpired):
        return None
    m = _PING_RE.search(out.stdout)
    return float(m.group(1)) if m and out.returncode == 0 else None


def average_ping(ips: Iterable[str]) -> Dict[str, Optional[float]]:
    return {ip: ping_ms(ip) for ip in ips}
