"""Let players from other homes join: public IP, automatic port opening (UPnP), firewall.

UPnP (IGD) is the "automatic port forwarding" most home routers support.
It does nothing if UPnP is turned off in the router settings.
"""

import ipaddress
import os
import socket
import urllib.error
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence
from urllib.parse import urljoin, urlparse
from xml.sax.saxutils import escape as xml_escape

from mc_server_maker.core import net
from mc_server_maker.i18n import t

SSDP_ADDR = ("239.255.255.250", 1900)
SEARCH_TARGETS = (
    "urn:schemas-upnp-org:device:InternetGatewayDevice:1",
    "urn:schemas-upnp-org:device:InternetGatewayDevice:2",
    "urn:schemas-upnp-org:service:WANIPConnection:1",
    "urn:schemas-upnp-org:service:WANPPPConnection:1",
)
WAN_SERVICES = ("WANIPConnection", "WANPPPConnection")
PUBLIC_IP_URLS = ("https://api.ipify.org", "https://checkip.amazonaws.com", "https://ifconfig.me/ip")

# talk to the router directly, never through a proxy
_LOCAL = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class UPnPError(Exception):
    pass


def lan_ip() -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))  # no packet is actually sent
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def is_public(ip: str) -> bool:
    try:
        return ipaddress.ip_address(ip).is_global
    except ValueError:
        return False


def public_ip() -> str:
    """This network's IP as seen from the internet."""
    last = None
    for url in PUBLIC_IP_URLS:
        try:
            ip = net.get_text(url).strip()
            ipaddress.ip_address(ip)
            return ip
        except (net.NetError, ValueError) as e:
            last = e
    raise net.NetError(t("Could not get the public IP. ({err})", err=last))


# ------------------------------------------------------------------ UPnP


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def discover(timeout: float = 2.5) -> List[str]:
    """Find routers via SSDP and return their description URLs (LOCATION)."""
    locations: List[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    try:
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
        try:
            sock.bind((lan_ip(), 0))  # send from the right network adapter
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
            raise UPnPError(_soap_error(e.read()) or t("Router error (HTTP {code})", code=e.code)) from e
        except (urllib.error.URLError, OSError) as e:
            raise UPnPError(t("Could not talk to the router: {err}", err=e)) from e
        result: Dict[str, str] = {}
        try:
            root = ET.fromstring(xml)
        except ET.ParseError as e:
            raise UPnPError(t("Could not read the router response.")) from e
        for el in root.iter():
            if _local(el.tag).endswith("Response"):
                for child in el:
                    result[_local(child.tag)] = (child.text or "").strip()
        return result

    def external_ip(self) -> str:
        return self.call("GetExternalIPAddress").get("NewExternalIPAddress", "")

    def add_port(self, port: int, internal_ip: str, description: str, protocol: str = "TCP") -> None:
        last = None
        # some routers reject permanent (0) leases, so also try one day
        for lease in (0, 86400):
            try:
                self.call(
                    "AddPortMapping",
                    {
                        "NewRemoteHost": "",
                        "NewExternalPort": port,
                        "NewProtocol": protocol,
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

    def delete_port(self, port: int, protocol: str = "TCP") -> None:
        self.call("DeletePortMapping", {"NewRemoteHost": "", "NewExternalPort": port, "NewProtocol": protocol})


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
        "718": t("Another device already uses this port. Use another port or remove the old rule in the router."),
        "606": t("The router refused the request (UPnP permissions)."),
    }
    return t("Router error {code} {desc}", code=code, desc=desc).strip() + (f" - {hints[code]}" if code in hints else "")


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
        t("No UPnP router found.\nTurn on UPnP in your router settings, or set up port forwarding manually (see below).")
    )


@dataclass
class PortResult:
    port: int
    lan_ip: str
    router_ip: str  # external IP reported by the router
    router_host: str  # router admin page host
    cgnat: bool  # router WAN IP is private -> behind carrier NAT, forwarding cannot work


def open_port(
    port: int,
    description: str = "Minecraft Server",
    gateway: Optional[Gateway] = None,
    udp_ports: Sequence[int] = (),
) -> PortResult:
    """Open the Java TCP port (plus UDP ports, e.g. 19132 for Bedrock players)."""
    gw = gateway or find_gateway()
    ip = lan_ip()
    gw.add_port(port, ip, description)
    for udp in udp_ports:
        gw.add_port(udp, ip, description + " (Bedrock)", "UDP")
    try:
        ext = gw.external_ip()
    except UPnPError:
        ext = ""
    return PortResult(port, ip, ext, gw.host, cgnat=bool(ext) and not is_public(ext))


def close_port(port: int, gateway: Optional[Gateway] = None, udp_ports: Sequence[int] = ()) -> None:
    gw = gateway or find_gateway()
    gw.delete_port(port)
    for udp in udp_ports:
        try:
            gw.delete_port(udp, "UDP")
        except UPnPError:
            pass


# ---------------------------------------------------------------- firewall


def allow_firewall(port: int, udp_ports: Sequence[int] = ()) -> bool:
    """Add Windows Firewall allow rules (shows one admin prompt)."""
    if os.name != "nt":
        return False
    import ctypes

    rules = [f'netsh advfirewall firewall add rule name="Minecraft Server {port}" dir=in action=allow protocol=TCP localport={port}']
    rules += [
        f'netsh advfirewall firewall add rule name="Minecraft Bedrock {u}" dir=in action=allow protocol=UDP localport={u}'
        for u in udp_ports
    ]
    # ShellExecute returns > 32 on success
    return ctypes.windll.shell32.ShellExecuteW(None, "runas", "cmd", "/c " + " && ".join(rules), None, 0) > 32
