"""Can players actually join? Checks the server like a Minecraft client would.

- local / LAN: Server List Ping (the same handshake the multiplayer screen uses)
- internet: asks mcsrvstat.us to ping the address from outside, which is the only
  way to know whether friends in other homes can reach it
"""

import json
import re
import socket
import struct
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import quote

from mc_server_maker.core import net

EXTERNAL_API = "https://api.mcsrvstat.us/3/{address}"
EXTERNAL_API_BEDROCK = "https://api.mcsrvstat.us/bedrock/3/{address}"


@dataclass
class CheckResult:
    ok: bool
    latency_ms: Optional[float] = None
    version: str = ""
    players: str = ""  # "3/20"
    error: str = ""


def _varint(n: int) -> bytes:
    out = b""
    n &= 0xFFFFFFFF
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _read_varint(sock: socket.socket) -> int:
    result = 0
    for i in range(5):
        b = sock.recv(1)
        if not b:
            raise ConnectionError("connection closed")
        result |= (b[0] & 0x7F) << (7 * i)
        if not b[0] & 0x80:
            return result
    raise ValueError("varint too long")


def _recv_exact(sock: socket.socket, n: int) -> bytes:
    data = b""
    while len(data) < n:
        chunk = sock.recv(n - len(data))
        if not chunk:
            raise ConnectionError("connection closed")
        data += chunk
    return data


def _packet(packet_id: int, payload: bytes = b"") -> bytes:
    body = _varint(packet_id) + payload
    return _varint(len(body)) + body


def server_list_ping(host: str, port: int = 25565, timeout: float = 3.0) -> CheckResult:
    """Ask a Java server for its status (version, players) like the multiplayer screen does."""
    try:
        start = time.monotonic()
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            addr = host.encode("utf-8")
            handshake = _varint(47) + _varint(len(addr)) + addr + struct.pack(">H", port) + _varint(1)
            sock.sendall(_packet(0x00, handshake) + _packet(0x00))
            _read_varint(sock)  # packet length
            if _read_varint(sock) != 0x00:
                return CheckResult(False, error="unexpected reply")
            data = _recv_exact(sock, _read_varint(sock))
            latency = (time.monotonic() - start) * 1000
        status = json.loads(data.decode("utf-8", "replace"))
        players = status.get("players", {})
        return CheckResult(
            True,
            latency_ms=latency,
            version=str(status.get("version", {}).get("name", "")),
            players=f"{players.get('online', 0)}/{players.get('max', 0)}",
        )
    except (OSError, ValueError, ConnectionError) as e:
        return CheckResult(False, error=str(e) or e.__class__.__name__)


def external_check(address: str, bedrock: bool = False) -> CheckResult:
    """Ping `address` (host[:port]) from the internet via mcsrvstat.us. Results are cached there for a few minutes."""
    if not re.fullmatch(r"[A-Za-z0-9.\-:\[\]]+", address or ""):
        return CheckResult(False, error="invalid address")
    url = (EXTERNAL_API_BEDROCK if bedrock else EXTERNAL_API).format(address=quote(address, safe=":[]"))
    try:
        data = net.get_json(url)
    except net.NetError as e:
        return CheckResult(False, error=str(e))
    if not data.get("online"):
        return CheckResult(False, error="offline")
    players = data.get("players", {})
    return CheckResult(
        True,
        version=str(data.get("version", "")),
        players=f"{players.get('online', 0)}/{players.get('max', 0)}",
    )
