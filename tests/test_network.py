"""UPnP 자동 포트 열기 테스트 (가짜 공유기 HTTP 서버 사용)."""

import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

from mc_server_maker.core import network

DESC = b"""<?xml version="1.0"?>
<root xmlns="urn:schemas-upnp-org:device-1-0">
 <device><deviceType>urn:schemas-upnp-org:device:InternetGatewayDevice:1</deviceType>
  <deviceList><device><deviceList><device>
   <serviceList>
    <service>
     <serviceType>urn:schemas-upnp-org:service:WANIPConnection:1</serviceType>
     <controlURL>/ctl/IPConn</controlURL>
    </service>
   </serviceList>
  </device></deviceList></device></deviceList>
 </device>
</root>"""


class FakeRouter(BaseHTTPRequestHandler):
    calls = []
    external_ip = "1.2.3.4"
    reject_permanent = False

    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(DESC)

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"])).decode()
        action = self.headers["SOAPAction"].split("#")[1].strip('"')
        FakeRouter.calls.append((action, body))
        if action == "AddPortMapping" and self.reject_permanent and "<NewLeaseDuration>0<" in body:
            self.send_response(500)
            self.end_headers()
            self.wfile.write(
                b'<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body><s:Fault><detail>'
                b'<UPnPError xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>725</errorCode>'
                b"<errorDescription>OnlyPermanentLeasesSupported</errorDescription></UPnPError>"
                b"</detail></s:Fault></s:Body></s:Envelope>"
            )
            return
        extra = f"<NewExternalIPAddress>{self.external_ip}</NewExternalIPAddress>" if action == "GetExternalIPAddress" else ""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(
            (
                '<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/"><s:Body>'
                f'<u:{action}Response xmlns:u="urn:schemas-upnp-org:service:WANIPConnection:1">{extra}'
                f"</u:{action}Response></s:Body></s:Envelope>"
            ).encode()
        )


class UPnPTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = HTTPServer(("127.0.0.1", 0), FakeRouter)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.location = f"http://127.0.0.1:{cls.httpd.server_port}/rootDesc.xml"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        FakeRouter.calls = []
        FakeRouter.external_ip = "1.2.3.4"
        FakeRouter.reject_permanent = False

    def test_open_port(self):
        gw = network.gateway_from_location(self.location)
        self.assertEqual(gw.control_url, self.location.rsplit("/", 1)[0] + "/ctl/IPConn")
        res = network.open_port(25565, "Minecraft test", gateway=gw)
        self.assertEqual(res.router_ip, "1.2.3.4")
        self.assertFalse(res.cgnat)
        action, body = FakeRouter.calls[0]
        self.assertEqual(action, "AddPortMapping")
        self.assertIn("<NewExternalPort>25565</NewExternalPort>", body)
        self.assertIn("<NewProtocol>TCP</NewProtocol>", body)

    def test_cgnat_detected_and_lease_retry(self):
        FakeRouter.external_ip = "100.64.12.3"
        FakeRouter.reject_permanent = True
        gw = network.gateway_from_location(self.location)
        res = network.open_port(25565, gateway=gw)
        self.assertTrue(res.cgnat)
        adds = [b for a, b in FakeRouter.calls if a == "AddPortMapping"]
        self.assertEqual(len(adds), 2)
        self.assertIn("<NewLeaseDuration>86400<", adds[1])

    def test_error_message(self):
        msg = network._soap_error(
            b'<e xmlns="urn:schemas-upnp-org:control-1-0"><errorCode>718</errorCode>'
            b"<errorDescription>ConflictInMappingEntry</errorDescription></e>"
        )
        self.assertIn("718", msg)
        self.assertIn("already uses this port", msg)

    def test_is_public(self):
        self.assertTrue(network.is_public("8.8.8.8"))
        self.assertFalse(network.is_public("192.168.0.2"))
        self.assertFalse(network.is_public("100.64.1.1"))


if __name__ == "__main__":
    unittest.main()
