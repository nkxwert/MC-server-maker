"""Regression tests for bugs found in the 1.12 review."""

import http.server
import shutil
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

from mc_server_maker.core import modrinth, net, players, plugins, tunnel
from mc_server_maker.core import server as srv
from mc_server_maker.core.properties import Properties
from mc_server_maker.core.tasks import Cancelled, Task


class _Handler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/cut":
            self.send_response(200)
            self.send_header("Content-Length", "100000")
            self.end_headers()
            self.wfile.write(b"x" * 1000)  # then hang up
        else:
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<html>not json</html>")

    def log_message(self, *args):
        pass


class NetTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.httpd.server_port}"

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_cut_off_download_is_not_kept(self):
        with self.assertRaises(net.NetError):
            net.download(self.base + "/cut", self.dir / "agent.exe")
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_html_instead_of_json_is_a_net_error(self):
        with self.assertRaises(net.NetError):
            net.get_json(self.base + "/page")


class PlayersFileTest(unittest.TestCase):
    def test_broken_file_is_not_wiped(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        ops = d / "ops.json"
        ops.write_text('[{"uuid": "a", "name": "Alex"},]')  # trailing comma
        with self.assertRaises(players.PlayerError):
            players.add(d, "ops", "Steve", online_mode=False)
        self.assertIn("Alex", ops.read_text())
        ops.write_text('\ufeff[{"uuid": "a", "name": "Alex"}]', encoding="utf-8")  # BOM is fine
        self.assertEqual(players.list_names(d, "ops"), ["Alex"])


class PropertiesTest(unittest.TestCase):
    def test_bom_and_backslash_comment(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        path = d / "server.properties"
        path.write_bytes("\ufeffmotd=hi\n#path C:\\\nonline-mode=false\n".encode("utf-8"))
        p = Properties(path)
        self.assertEqual(p.get("motd"), "hi")
        self.assertEqual(p.get("online-mode"), "false")


class WorldTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def _world(self, root: Path, name: str):
        (root / name).mkdir(parents=True)
        (root / name / "level.dat").write_bytes(b"x")

    def test_import_keeps_nether_and_end(self):
        src = self.dir / "backup"
        for name in ("world_nether", "world", "world_the_end"):
            self._world(src, name)
        server = self.dir / "server"
        server.mkdir()
        self.assertEqual(srv.find_world_root(src).name, "world")
        srv.import_world(server, src, "world")
        self.assertEqual(sorted(p.name for p in server.iterdir()), ["world", "world_nether", "world_the_end"])

    def test_cancelled_backup_leaves_no_zip(self):
        meta = srv.ServerMeta(name="b", software="vanilla", mc_version="1.21.4", folder=self.dir)
        self._world(self.dir, "world")
        task = Task()
        task.cancelled = True
        with self.assertRaises(Cancelled):
            srv.backup_server(meta, "x", worlds_only=True, task=task)
        self.assertEqual(srv.list_backups(meta), [])
        self.assertEqual(list((self.dir / srv.BACKUP_DIR).glob("*")), [])


class SmallParsersTest(unittest.TestCase):
    def test_only_geyser_and_floodgate_jars_are_ours(self):
        self.assertTrue(plugins._is_ours("Geyser-Spigot.jar"))
        self.assertTrue(plugins._is_ours("floodgate-spigot.jar"))
        self.assertFalse(plugins._is_ours("GeyserSkinManager-Spigot.jar"))

    def test_tunnel_address_skips_bedrock(self):
        out = "Minecraft Bedrock (UDP) abc.ply.gg:41234 => 127.0.0.1:19132\nbrave-fox.gl.joinmc.link => 127.0.0.1:25565"
        self.assertEqual(tunnel.find_address(out), "brave-fox.gl.joinmc.link")

    def test_chat_cannot_fake_a_join(self):
        from mc_server_maker.gui.runner import JOIN_RE, LEFT_RE

        self.assertEqual(JOIN_RE.search("[12:00:00 INFO]: Steve joined the game").group(1), "Steve")
        self.assertIsNone(JOIN_RE.search("[12:00:00 INFO]: <Steve> lol: Notch joined the game"))
        self.assertIsNone(LEFT_RE.search("[12:00:00 INFO]: <Steve> x: Alex left the game"))


class ModrinthLockedJarTest(unittest.TestCase):
    def test_locked_old_jar_leaves_no_duplicate(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        meta = srv.ServerMeta(name="m", software="paper", mc_version="1.21.4", folder=d)
        (d / "plugins").mkdir()
        old = d / "plugins" / "Cool-1.0.jar"
        old.write_bytes(b"old")
        version = {"files": [{"url": "u", "filename": "Cool-2.0.jar", "primary": True, "hashes": {}}]}
        with mock.patch.object(Path, "rename", side_effect=PermissionError("in use")), \
                mock.patch.object(net, "download") as dl:
            with self.assertRaises(modrinth.ModrinthError):
                modrinth._write_version(meta, version, Task(), replace=old)
            dl.assert_not_called()
        self.assertEqual([p.name for p in (d / "plugins").iterdir()], ["Cool-1.0.jar"])


if __name__ == "__main__":
    unittest.main()
