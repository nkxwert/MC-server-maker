"""1.24: direct connections, tunnel per server, old downloaded copies, friendly task errors."""

import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mc_server_maker.core import network, tunnel, updater  # noqa: E402


class ConnectionKindTest(unittest.TestCase):
    def test_kinds(self):
        self.assertEqual(network.connection_kind("182.214.183.205"), "direct")
        self.assertEqual(network.connection_kind("100.72.1.9"), "carrier")
        self.assertEqual(network.connection_kind("192.168.0.12"), "router")
        self.assertEqual(network.connection_kind("10.0.0.5"), "router")

    def test_router_check_kind(self):
        r = network.RouterCheck(gateway="192.168.0.1", lan_ip="192.168.0.5", wan_ip="100.66.2.3")
        self.assertEqual(r.kind, "carrier")  # the router itself sits behind the provider's NAT
        self.assertEqual(network.RouterCheck(lan_ip="182.214.183.205").kind, "direct")

    def test_hide_public(self):
        self.assertEqual(network.hide_public("182.214.183.205"), "182.214.x.x")
        self.assertEqual(network.hide_public("192.168.0.12"), "192.168.0.12")


class TunnelPerServerTest(unittest.TestCase):
    def test_other_servers_tunnel_is_not_offered(self):
        a = tunnel.PlayitTunnel(address="a.joinmc.link", kind="minecraft-java", port_type="tcp", local_port=25565, disabled="")
        b = tunnel.PlayitTunnel(address="b.joinmc.link", kind="minecraft-java", port_type="tcp", local_port=25566, disabled="")
        self.assertEqual(tunnel.java_address([a, b], 25565), "a.joinmc.link")
        self.assertEqual(tunnel.java_address([a, b], 25566), "b.joinmc.link")
        self.assertEqual(tunnel.java_address([a, b], 25567), "")  # no tunnel for this server
        anywhere = tunnel.PlayitTunnel(address="c.joinmc.link", kind="minecraft-java", port_type="tcp", local_port=None, disabled="")
        self.assertEqual(tunnel.java_address([a, anywhere], 25567), "c.joinmc.link")


class OldCopiesTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_finds_only_real_bartizan_files(self):
        (self.dir / "Bartizan (1).exe").write_bytes(b"MZ" + b"\0" * (3 << 20) + b"mc_server_maker.gui")
        (self.dir / "Bartizan-Setup (2).exe").write_bytes(b"MZ..." + "Bartizan".encode("utf-16-le"))
        (self.dir / "Bartizan.exe.old").write_bytes(b"xx mc_server_maker")
        (self.dir / "Bartizan-fake.exe").write_bytes(b"MZ something else")
        (self.dir / "notes.txt").write_bytes(b"mc_server_maker")
        names = sorted(p.name for p in updater.old_copies([self.dir, self.dir / "missing"]))
        self.assertEqual(names, ["Bartizan (1).exe", "Bartizan-Setup (2).exe", "Bartizan.exe.old"])


class FriendlyErrorTest(unittest.TestCase):
    def test_causes(self):
        from mc_server_maker.gui.workers import friendly_error
        from mc_server_maker.i18n import t

        self.assertEqual(friendly_error("<urlopen error timed out>"),
                         t("Couldn't download the files. Check the internet connection and try again."))
        self.assertEqual(friendly_error("[Errno 28] No space left on device"),
                         t("There isn't enough free disk space. Free some space and try again."))
        self.assertEqual(friendly_error("weird"), t("The task couldn't be finished. The details are below."))


if __name__ == "__main__":
    unittest.main()
