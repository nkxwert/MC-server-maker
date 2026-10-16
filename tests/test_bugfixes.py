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


class SwitchSoftwareTest(unittest.TestCase):
    def test_paper_to_fabric_keeps_nether_and_end(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        meta = srv.ServerMeta(name="s", software="paper", mc_version="1.21.4", folder=d,
                              launch={"type": "jar", "jar": "server.jar"})
        meta.save()
        (d / "server.properties").write_text("level-name=world\nmotd=hi\n")
        (d / "server.jar").write_bytes(b"paper")
        for folder, dim in (("world", None), ("world_nether", "DIM-1"), ("world_the_end", "DIM1")):
            base = d / folder / (dim or "")
            base.mkdir(parents=True)
            (base / "level.dat" if not dim else base / "region.mca").write_bytes(b"x")

        class FakeFabric:
            name = "Fabric"

            def install(self, folder, version, java, task):
                (Path(folder) / "fabric-server-launch.jar").write_bytes(b"fabric")
                return {"launch": {"type": "jar", "jar": "fabric-server-launch.jar"}, "build": "loader 1"}

        java = mock.Mock(major=21, path="java")
        with mock.patch.object(srv, "get_provider", return_value=FakeFabric()), \
                mock.patch.object(srv, "_java_for", return_value=java):
            srv.upgrade_server(meta, "1.21.4", backup_first=False, new_software="fabric")
        saved = srv.ServerMeta.load(d)
        self.assertEqual((saved.software, saved.mc_version, saved.launch["jar"]), ("fabric", "1.21.4", "fabric-server-launch.jar"))
        self.assertTrue((d / "world" / "DIM-1" / "region.mca").exists())
        self.assertTrue((d / "world" / "DIM1" / "region.mca").exists())
        self.assertFalse((d / "world_nether").exists())
        self.assertFalse((d / "server.jar").exists())  # Paper's jar is gone
        self.assertEqual(Properties(d / "server.properties").get("motd"), "hi")  # settings stay


class ReviewFixes117Test(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_failed_import_keeps_current_world(self):
        import zipfile
        meta = srv.ServerMeta(name="i", software="vanilla", mc_version="1.21.4", folder=self.dir / "srv")
        meta.folder.mkdir()
        (meta.folder / "world").mkdir()
        (meta.folder / "world" / "level.dat").write_bytes(b"mine")
        bad = self.dir / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("world/level.dat", b"x")
            z.writestr("../../evil.txt", b"x")
        with self.assertRaises(srv.ServerError):
            srv.replace_world_with_import(meta, bad, Task())
        self.assertEqual((meta.folder / "world" / "level.dat").read_bytes(), b"mine")
        with self.assertRaises(srv.ServerError):  # its own world can't be imported over itself
            srv.replace_world_with_import(meta, meta.folder / "world", Task())

    def test_backup_with_pre_1980_file(self):
        import os
        meta = srv.ServerMeta(name="b", software="vanilla", mc_version="1.21.4", folder=self.dir)
        (self.dir / "world").mkdir()
        old = self.dir / "world" / "level.dat"
        old.write_bytes(b"x")
        os.utime(old, (0, 0))
        srv.backup_server(meta, "x", worlds_only=True, task=Task())
        self.assertEqual(len(srv.list_backups(meta)), 1)

    def test_properties_keep_their_encoding(self):
        path = self.dir / "server.properties"
        path.write_bytes("motd=\xc7\xd1\n".encode("latin-1"))  # not UTF-8 (cp949 text)
        p = Properties(path)
        p.set("pvp", "true")
        p.save()
        self.assertTrue(path.read_bytes().startswith(b"motd=\xc7\xd1"))  # (\r\n on Windows)
        self.assertNotIn("\xc7".encode("utf-8"), path.read_bytes())

    def test_custom_level_type_survives_upgrade_check(self):
        self.assertFalse(srv.is_builtin_level_type("biomesoplenty:biomesoplenty"))
        self.assertTrue(srv.is_builtin_level_type("minecraft:flat"))
        self.assertTrue(srv.is_builtin_level_type("DEFAULT"))

    def test_cancelled_download_leaves_no_part(self):
        class Resp:
            headers = {"Content-Length": "10"}
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, n): return b"12345"
        task = Task()
        calls = {"n": 0}
        def check():
            calls["n"] += 1
            if calls["n"] > 1:
                raise Cancelled()
        task.check = check
        with mock.patch.object(net, "_open", return_value=Resp()):
            with self.assertRaises(Cancelled):
                net.download("http://x/file", self.dir / "f.bin", task)
        self.assertEqual(list(self.dir.iterdir()), [])

    def test_duplicate_keeps_plugin_logs(self):
        meta = srv.ServerMeta(name="d", software="paper", mc_version="1.21.4", folder=self.dir / "a")
        (meta.folder / "plugins" / "X" / "logs").mkdir(parents=True)
        (meta.folder / "plugins" / "X" / "logs" / "l.txt").write_text("x")
        (meta.folder / "logs").mkdir()
        meta.save()
        with mock.patch.object(srv.paths, "SERVERS_DIR", self.dir):
            copy = srv.duplicate_server(meta, "b")
        self.assertTrue((copy.folder / "plugins" / "X" / "logs" / "l.txt").exists())
        self.assertFalse((copy.folder / "logs").exists())

    def test_login_line_from_chat_is_ignored(self):
        from mc_server_maker.gui.runner import LOGIN_RE
        self.assertIsNotNone(LOGIN_RE.search("[12:00:00 INFO]: Steve[/1.2.3.4:5] logged in with entity id 1"))
        self.assertIsNone(LOGIN_RE.search("[12:00:00 INFO]: <Steve> Notch[/6.6.6.6:1] logged in"))


class ReviewFixes118Test(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def test_nel_byte_does_not_split_a_line(self):
        path = self.dir / "server.properties"
        path.write_bytes(b"motd=Welcome\x85 friends\npvp=true\n")  # not UTF-8: read as latin-1
        p = Properties(path)
        self.assertEqual(p.get("motd"), "Welcome\x85 friends")
        p.set("pvp", "false")
        p.save()
        self.assertIn(b"motd=Welcome\x85 friends", path.read_bytes())

    def test_import_with_nested_level_name(self):
        meta = srv.ServerMeta(name="n", software="vanilla", mc_version="1.21.4", folder=self.dir / "srv")
        meta.folder.mkdir()
        (meta.folder / "server.properties").write_text("level-name=worlds/main\n")
        (meta.folder / "worlds" / "main").mkdir(parents=True)
        (meta.folder / "worlds" / "main" / "level.dat").write_bytes(b"old")
        src = self.dir / "new"
        src.mkdir()
        (src / "level.dat").write_bytes(b"new")
        srv.replace_world_with_import(meta, src, Task())
        self.assertEqual((meta.folder / "worlds" / "main" / "level.dat").read_bytes(), b"new")
        self.assertFalse((meta.folder / "worlds" / "worlds").exists())


class PlayitAgentVersionTest(unittest.TestCase):
    def test_only_the_pinned_agent_counts_as_installed(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.object(tunnel, "agent_dir", return_value=d):
            tunnel.agent_path().write_bytes(b"x")  # e.g. playit 1.x fetched by an older app
            self.assertFalse(tunnel.is_installed())
            tunnel.version_path().write_text(tunnel.AGENT_VERSION)
            self.assertTrue(tunnel.is_installed())
            tunnel.remove_agent()
            self.assertFalse(tunnel.agent_path().exists())
        self.assertIn("/tags/" + tunnel.AGENT_VERSION, tunnel.RELEASES)


class PlayitApiTest(unittest.TestCase):
    def test_rundata_and_java_address(self):
        data = {"status": "success", "data": {"agent_id": "a", "tunnels": [
            {"display_address": "fun-bed.ply.gg:41234", "tunnel_type": "minecraft-bedrock", "port_type": "udp",
             "agent_config": {"fields": [{"name": "local_port", "value": "19132"}]}, "disabled_reason": None},
            {"display_address": "old.gl.joinmc.link", "tunnel_type": "minecraft-java", "port_type": "tcp",
             "agent_config": {"fields": []}, "disabled_reason": "account limit"},
            {"display_address": "brave-fox.gl.joinmc.link", "tunnel_type": "minecraft-java", "port_type": "tcp",
             "agent_config": {"fields": [{"name": "local_port", "value": "25565"}]}, "disabled_reason": None},
        ], "pending": [], "notices": []}}
        tunnels = tunnel.parse_rundata(data)
        self.assertEqual(len(tunnels), 3)
        self.assertEqual(tunnel.java_address(tunnels), "brave-fox.gl.joinmc.link")
        self.assertEqual(tunnel.java_address(tunnels[:2]), "")  # only Bedrock + a disabled one
        with self.assertRaises(tunnel.TunnelError):
            tunnel.parse_rundata({"status": "error", "data": {}})

    def test_secret_from_toml(self):
        d = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, d, True)
        with mock.patch.object(tunnel, "agent_dir", return_value=d):
            self.assertEqual(tunnel.read_secret(), "")
            tunnel.secret_path().write_text('secret_key = "0a1B2c"\n')
            self.assertEqual(tunnel.read_secret(), "0a1B2c")


if __name__ == "__main__":
    unittest.main()
