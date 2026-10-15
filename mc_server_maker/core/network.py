"""외부(다른 집)에서 접속할 수 있게 하기: 공인 IP 확인, UPnP 자동 포트 열기, 방화벽.

UPnP(IGD)는 대부분의 가정용 공유기가 지원하는 '자동 포트포워딩' 기능이다.
공유기 설정에서 UPnP가 꺼져 있으면 동작하지 않는다.
"""

import ipaddress
import os
import socket
import subprocess
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape as xml_escape

from mc_server_maker.core import net

SSDP_ADDR = ("239.255.255.250", 1900)
SEARCH_TARGETS = (
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
    "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)
WAN_SERVICES = ("WANIPConnection", "WANPPPConnection")
PUBLIC_IP_URLS = ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip")

# 공유기와의 통신은 프록시를 거치지 않는다
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class UPnPError(Exception):
    pass


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # 실제로 패킷을 보내지 않음
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def is_public(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def public_ip() -> str:
    """인터넷에서 보이는 내 IP."""
    last = None
    for url in PUBLIC_IP_URLS:
        try:
            ip = net.get_text(url).strip()
            ipaddress.ip_address(ip)
            return ip
        except (net.NetError, ValueError) as e:
            last = e
    raise net.NetError(f"공인 IP를 확인하지 못했습니다. ({last})")


# ------------------------------------------------------------------ UPnP


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def discover(timeout: float = 2.5) -> List[str]:
    """SSDP로 공유기를 찾아 설명 XML 주소(LOCATION) 목록을 돌려준다."""
    locations: List[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        try:
            sock.bind((lan_ip(), 0))  # 올바른 네트워크 카드로 보내기
        except OSError:
            pass
        sock.settimeout(timeout)
        for st in SEARCH_TARGETS:
            msg = (
                "M-SEARCH * HTTP/1.1\r\n"
                f"HOST: {SSDP_ADDR[0]}:{SSDP_ADDR[1]}\r\n"
                'MAN: "ssdp:discover"\r\n'
                "MX: 2\r\n"
                f"ST: {st}\r\n\r\n"
            )
            try:
                sock.sendto(msg.encode("ascii"), SSDP_ADDR)
            except OSError:
                pass
        while True:
            try:
                data, _ = sock.recvfrom(65507)
            except (socket.timeout, OSError):
                break
            for line in data.decode("utf-8", errors="replace").split("\r\n"):
                name, _, value = line.partition(":")
                if name.strip().lower() == "location":
                    loc = value.strip()
                    if loc and loc not in locations:
                        locations.append(loc)
    finally:
        sock.close()
    return locations


@dataclass
class Gateway:
    location: str
    control_url: str
    service_type: str

    @property
    def host(self) -> str:
        return urlparse(self.location).hostname or ""

    def call(self, action: str, args: Optional[Dict[str, object]] = None) -> Dict[str, str]:
        body_args = "".join(f"<{k}>{xml_escape(str(v))}</{k}>" for k, v in (args or {}).items())
        body = (
            '<?xml version="1.0"?>'
            '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
            's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">'
            f'<s:Body><u:{action} xmlns:u="{self.service_type}">{body_args}</u:{action}></s:Body>'
            "</s:Envelope>"
        ).encode("utf-8")
        req = urllib.request.Request(
            self.control_url,
            data=body,
            headers={
                "Content-Type": 'text/xml; charset="utf-8"',
                "SOAPAction": f'"{self.service_type}#{action}"',
            },
        )
        try:
            with _LOCAL.open(req, timeout=8) as resp:
                xml = resp.read()
        except urllib.error.HTTPError as e:
            raise UPnPError(_soap_error(e.read()) or f"공유기 오류 (HTTP {e.code})") from e
        except (urllib.error.URLError, OSError) as e:
            raise UPnPError(f"공유기와 통신하지 못했습니다: {e}") from e
        result: Dict[str, str] = {}
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            raise UPnPError("공유기 응답을 읽지 못했습니다.") from e
        for el in root.iter():
            if _local(el.tag).endswith("Response"):
                for child in el:
                    result[_local(child.tag)] = (child.text or "").strip()
        return result

    def external_ip(self) -> str:
        return self.call("GetExternalIPAddress").get("NewExternalIPAddress", "")

    def add_port(self, port: int, internal_ip: str, description: str) -> None:
        last = None
        # 영구(0) 매핑을 거부하는 공유기가 있어서 하루짜리도 시도한다
        for lease in (0, 86400):
            try:
                self.call(
                    "AddPortMapping",
                    {
                        "NewRemoteHost": "",
                        "NewExternalPort": port,
                        "NewProtocol": "TCP",
                        "NewInternalPort": port,
                        "NewInternalClient": internal_ip,
                        "NewEnabled": 1,
                        "NewPortMappingDescription": description,
                        "NewLeaseDuration": lease,
                    },
                )
                return
            except UPnPError as e:
                last = e
        raise last

    def delete_port(self, port: int) -> None:
        self.call("DeletePortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": "TCP"})


def _soap_error(xml: bytes) -> str:
    try:
        root = ET.fromstring(xml)
    except ET.ParseError:
        return ""
    code = desc = ""
    for el in root.iter():
        name = _local(el.tag)
        if name == "errorCode":
            code = (el.text or "").strip()
        elif name == "errorDescription":
            desc = (el.text or "").strip()
    if not code:
        return ""
    hints = {
        "718": "다른 기기가 이미 이 포트를 쓰고 있습니다. 다른 포트를 쓰거나 공유기에서 기존 설정을 지워 주세요.",
        "606": "공유기가 이 요청을 허용하지 않습니다 (UPnP 권한 제한).",
    }
    return f"공유기 오류 {code} {desc}".strip() + (f" - {hints[code]}" if code in hints else "")


def gateway_from_location(location: str) -> Optional[Gateway]:
    try:
        with _LOCAL.open(location, timeout=5) as resp:
            xml = resp.read()
        root = ET.fromstring(xml)
    except (urllib.error.URLError, OSError, ET.ParseError):
        return None
    base = location
    for el in root.iter():
        if _local(el.tag) == "URLBase" and (el.text or "").strip():
            base = el.text.strip()
    for el in root.iter():
        if _local(el.tag) != "service":
            continue
        fields = {_local(c.tag): (c.text or "").strip() for c in el}
        stype = fields.get("serviceType", "")
        if any(s in stype for s in WAN_SERVICES) and fields.get("controlURL"):
            return Gateway(location, urljoin(base, fields["controlURL"]), stype)
    return None


def find_gateway(timeout: float = 2.5) -> Gateway:
    for loc in discover(timeout):
        gw = gateway_from_location(loc)
        if gw:
            return gw
    raise UPnPError(
        "공유기에서 자동 포트 열기(UPnP)를 찾지 못했습니다.\n"
        "공유기 관리 페이지에서 UPnP를 켜거나, 아래 안내대로 포트포워딩을 직접 설정해 주세요."
    )


@dataclass
class PortResult:
    port: int
    lan_ip: str
    router_ip: str  # 공유기가 알려준 외부 IP
    router_host: str  # 공유기 관리 페이지 주소
    cgnat: bool  # 공유기 외부 IP가 사설 IP면 통신사 NAT 뒤라 포트포워딩이 안 된다


def open_port(port: int, description: str = "Minecraft Server", gateway: Optional[Gateway] = None) -> PortResult:
    gw = gateway or find_gateway()
    ip = lan_ip()
    gw.add_port(port, ip, description)
    try:
        ext = gw.external_ip()
    except UPnPError:
        ext = ""
    return PortResult(port, ip, ext, gw.host, cgnat=bool(ext) and not is_public(ext))


def close_port(port: int, gateway: Optional[Gateway] = None) -> None:
    (gateway or find_gateway()).delete_port(port)


# ------------------------------------------------------------------ 방화벽


def allow_firewall(port: int) -> bool:
    """Windows 방화벽에 포트 허용 규칙 추가 (관리자 권한 창이 뜬다)."""
    if os.name != "nt":
        return False
    import ctypes

    params = (
        f'advfirewall firewall add rule name="Minecraft Server {port}" '
        f"dir=in action=allow protocol=TCP localport={port}"
    )
    # ShellExecute 반환값이 32보다 크면 성공
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", "netsh", params, None, 0) > 32


def firewall_rule_exists(port: int) -> bool:
    if os.name != "nt":
        return True
    try:
        out = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule", f"name=Minecraft Server {port}"],
            capture_output=True,
            text=True,
            timeout=10,
            creationflags=0x08000000,
        )
        return out.returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False
