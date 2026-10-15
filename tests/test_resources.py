"""Data folder migration, low-resource launch args, stats helpers, property catalog."""

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mc_server_maker.core import paths, property_catalog, stats
from mc_server_maker.core import server as srv


class MigrationTest(unittest.TestCase):
    def setUp(self):
        self.old = Path(tempfile.mkdtemp())
        self.new = Path(tempfile.mkdtemp()) / "Bartizan"
        self.addCleanup(shutil.rmtree, self.old, True)
        self.addCleanup(shutil.rmtree, self.new.parent, True)
        patches = [
            mock.patch.object(paths, "BASE_DIR", self.new),
            mock.patch.dict(os.environ, {"MCSM_HOME": ""}),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def test_moves_desktop_data(self):
        (self.old / "servers" / "My Server").mkdir(parents=True)
        (self.old / "servers" / "My Server" / "server-maker.json").write_text("{}")
        (self.old / "settings.json").write_text("{}")
        (self.old / "runtime").mkdir()  # empty leftover
        moved = paths.migrate_legacy_data(self.old)
        self.assertEqual(sorted(moved), ["servers", "settings.json"])
        self.assertTrue((self.new / "servers" / "My Server" / "server-maker.json").exists())
        self.assertFalse((self.old / "servers").exists())
        self.assertFalse((self.old / "runtime").exists())

    def test_renames_old_documents_folder(self):
        old_docs = self.new.parent / "MC-Server-Maker-Files"
        (old_docs / "servers" / "SMP").mkdir(parents=True)
        (old_docs / "settings.json").write_text("{}")
        moved = paths.migrate_legacy_data()
        self.assertIn("MC-Server-Maker-Files", moved)
        self.assertTrue((self.new / "servers" / "SMP").is_dir())
        self.assertFalse(old_docs.exists())

    def test_never_overwrites(self):
        (self.old / "settings.json").write_text("old")
        self.new.mkdir(parents=True)
        (self.new / "settings.json").write_text("new")
        self.assertEqual(paths.migrate_legacy_data(self.old), [])
        self.assertEqual((self.new / "settings.json").read_text(), "new")
        self.assertTrue((self.old / "settings.json").exists())

    def test_documents_dir_exists_or_home(self):
        d = paths.documents_dir()
        self.assertTrue(str(d).startswith(str(Path.home())) or d.exists())


class LaunchArgsTest(unittest.TestCase):
    def meta(self, java):
        return srv.ServerMeta(name="x", software="paper", mc_version="1.21.4", ram_mb=4096, java_major=java,
                              launch={"type": "jar", "jar": "server.jar"}, folder=Path("."))

    def tearDown(self):
        srv.set_low_resource(True)

    def test_low_resource(self):
        srv.set_low_resource(True)
        args = srv.launch_args(self.meta(21))
        self.assertIn("-Xms256M", args)
        self.assertIn("-Xmx4096M", args)
        self.assertIn("-XX:G1PeriodicGCInterval=30000", args)
        # the flag doesn't exist on old Java and would stop the JVM from starting
        self.assertNotIn("-XX:G1PeriodicGCInterval=30000", srv.launch_args(self.meta(8)))

    def test_normal(self):
        srv.set_low_resource(False)
        args = srv.launch_args(self.meta(21))
        self.assertIn("-Xms1024M", args)
        self.assertFalse(any(a.startswith("-XX:") for a in args))


class StatsTest(unittest.TestCase):
    def test_ping_parsing(self):
        outputs = [
            ("64 bytes from 1.1.1.1: icmp_seq=1 ttl=57 time=12.4 ms", 12.4),
            ("Reply from 1.1.1.1: bytes=32 time=8ms TTL=57", 8.0),
            ("Reply from 192.168.0.2: bytes=32 time<1ms TTL=128", 1.0),
            ("1.1.1.1의 응답: 바이트=32 시간=15ms TTL=57", 15.0),
        ]
        for text, expected in outputs:
            done = subprocess.CompletedProcess([], 0, stdout=text, stderr="")
            with mock.patch.object(subprocess, "run", return_value=done):
                self.assertEqual(stats.ping_ms("1.1.1.1"), expected, text)
        failed = subprocess.CompletedProcess([], 1, stdout="Request timed out.", stderr="")
        with mock.patch.object(subprocess, "run", return_value=failed):
            self.assertIsNone(stats.ping_ms("1.1.1.1"))
        self.assertIsNone(stats.ping_ms("1.1.1.1; rm -rf /"))

    def test_sample_own_process(self):
        mon = stats.ProcessMonitor(os.getpid())
        smp = mon.sample()
        self.assertGreater(smp.memory_bytes, 0)
        self.assertGreaterEqual(smp.cpu_percent, 0)

    def test_sizes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "a").write_bytes(b"x" * 1000)
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "b").write_bytes(b"x" * 24)
            self.assertEqual(stats.folder_size(Path(d)), 1024)
        self.assertEqual(stats.human_bytes(1024), "1 KB")
        self.assertEqual(stats.human_bytes(3 * 1024**3), "3.0 GB")


class CatalogTest(unittest.TestCase):
    def test_catalog(self):
        self.assertIn("server-port", property_catalog.BY_KEY)
        self.assertTrue(property_catalog.BY_KEY["pvp"].is_bool)
        self.assertFalse(property_catalog.BY_KEY["max-players"].is_bool)
        self.assertEqual(len(property_catalog.BY_KEY), len(property_catalog.CATALOG))
        for p in property_catalog.CATALOG:
            self.assertTrue(p.en and p.ko, p.key)


if __name__ == "__main__":
    unittest.main()


class MemorySaverTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.meta = srv.ServerMeta(name="m", software="paper", mc_version="1.21.4", ram_mb=2048, java_major=21,
                                   launch={"type": "jar", "jar": "server.jar"}, folder=self.dir)
        props = self.meta.properties()
        props.set("view-distance", 12)
        props.save()
        self.meta.save()

    def test_toggle_restores_distances(self):
        srv.set_memory_saver(self.meta, True)
        p = self.meta.properties()
        self.assertEqual((p.get("view-distance"), p.get("simulation-distance")), ("6", "4"))
        self.assertIn("-XX:MaxHeapFreeRatio=30", srv.launch_args(self.meta))
        self.assertTrue(srv.ServerMeta.load(self.dir).memory_saver)
        srv.set_memory_saver(self.meta, False)
        p = self.meta.properties()
        self.assertEqual((p.get("view-distance"), p.get("simulation-distance")), ("12", "10"))
        self.assertNotIn("-XX:MaxHeapFreeRatio=30", srv.launch_args(self.meta))

    def test_spawn_chunk_command_versions(self):
        for v, expected in (("1.20.4", None), ("1.20.5", "gamerule spawnChunkRadius 0"),
                            ("1.21.4", "gamerule spawnChunkRadius 0"), ("1.21.9", None), ("26.1", None)):
            self.meta.mc_version = v
            self.assertEqual(srv.spawn_chunk_command(self.meta), expected, v)

    def test_duplicate(self):
        (self.dir / "world").mkdir()
        (self.dir / "world" / "level.dat").write_text("w")
        (self.dir / "backups").mkdir()
        (self.dir / "backups" / "old.zip").write_text("big")
        with mock.patch.object(paths, "SERVERS_DIR", self.dir.parent / (self.dir.name + "-servers")):
            copy = srv.duplicate_server(self.meta, "m copy")
            self.addCleanup(shutil.rmtree, copy.folder.parent, True)
        self.assertEqual(copy.name, "m copy")
        self.assertTrue((copy.folder / "world" / "level.dat").exists())
        self.assertFalse((copy.folder / "backups").exists())
        self.assertEqual(srv.ServerMeta.load(copy.folder).name, "m copy")
        self.assertEqual(srv.ServerMeta.load(self.dir).name, "m")


class JoinCheckTest(unittest.TestCase):
    def test_server_list_ping(self):
        import json
        import socket
        import threading

        from mc_server_maker.core import joincheck

        sock = socket.socket()
        sock.bind(("127.0.0.1", 0))
        sock.listen()
        port = sock.getsockname()[1]

        def serve():
            c, _ = sock.accept()
            with c:
                for _ in range(2):  # handshake + status request
                    joincheck._recv_exact(c, joincheck._read_varint(c))
                body = json.dumps({"version": {"name": "1.21.4"}, "players": {"online": 3, "max": 20}}).encode()
                payload = joincheck._varint(0) + joincheck._varint(len(body)) + body
                c.sendall(joincheck._varint(len(payload)) + payload)

        threading.Thread(target=serve, daemon=True).start()
        r = joincheck.server_list_ping("127.0.0.1", port)
        sock.close()
        self.assertTrue(r.ok, r.error)
        self.assertEqual((r.version, r.players), ("1.21.4", "3/20"))
        self.assertFalse(joincheck.server_list_ping("127.0.0.1", 1, timeout=1).ok)

    def test_external_check(self):
        from mc_server_maker.core import joincheck, net

        calls = []

        def fake(url):
            calls.append(url)
            return {"online": True, "version": "Paper 1.21.4", "players": {"online": 1, "max": 20}} \
                if "1.2.3.4" in url else {"online": False}

        with mock.patch.object(net, "get_json", fake):
            self.assertTrue(joincheck.external_check("1.2.3.4:25565").ok)
            self.assertFalse(joincheck.external_check("5.6.7.8:25565").ok)
            self.assertTrue(joincheck.external_check("1.2.3.4:19132", bedrock=True).ok)
            self.assertFalse(joincheck.external_check("bad host/../x").ok)
        self.assertIn("/bedrock/3/1.2.3.4:19132", calls[-1])
        self.assertEqual(len(calls), 3)  # invalid address never hits the network
