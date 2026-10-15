"""핵심 기능 테스트 (네트워크 없이 실행).  python -m unittest discover tests"""

import json
import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

_TMP = tempfile.mkdtemp(prefix="mcsm-test-")
os.environ["MCSM_HOME"] = _TMP

from mc_server_maker.core import java as javamod  # noqa: E402
from mc_server_maker.core import net, players, providers, versions  # noqa: E402
from mc_server_maker.core import server as srv  # noqa: E402
from mc_server_maker.core.properties import Properties, escape, unescape  # noqa: E402


class FakeProvider(providers.Provider):
    id = "fake"
    name = "Fake"

    def _list_versions(self, include_unstable):
        return ["1.21.1", "1.20.1"]

    def install(self, server_dir, mc_version, java, task):
        (server_dir / "server.jar").write_text(f"jar {mc_version}")
        return {"launch": {"type": "jar", "jar": "server.jar"}, "build": "7"}


FAKE_JAVA = javamod.JavaInfo("/usr/bin/java", 21, False)


def make_world(root: Path, name="MyWorld") -> Path:
    w = root / name
    (w / "region").mkdir(parents=True)
    (w / "level.dat").write_bytes(b"level")
    (w / "region" / "r.0.0.mca").write_bytes(b"region")
    return w


class Base(unittest.TestCase):
    def setUp(self):
        shutil.rmtree(_TMP, ignore_errors=True)
        Path(_TMP).mkdir()
        self.tmp = Path(tempfile.mkdtemp())
        fake = FakeProvider()
        patches = [
            mock.patch.object(providers, "PROVIDERS", providers.PROVIDERS + [fake]),
            mock.patch.object(srv, "get_provider", lambda pid: fake if pid == "fake" else providers.get_provider(pid)),
            mock.patch.object(versions, "required_java", lambda v: 21),
            mock.patch.object(javamod, "ensure_java", lambda req, auto, task=None: FAKE_JAVA),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def create(self, **kw):
        opts = srv.CreateOptions(name="테스트 서버", software="fake", mc_version="1.20.1", eula_accepted=True, **kw)
        return srv.create_server(opts)


class PropertiesTest(unittest.TestCase):
    def test_escape_roundtrip(self):
        for s in ["§a안녕 서버", "line1\nline2", "a=b:c#d", " leading", "back\\slash", "😀 emoji"]:
            self.assertEqual(unescape(escape(s)), s)
        self.assertEqual(escape("§a"), "\\u00a7a")

    def test_preserves_comments_and_order(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "server.properties"
            p.write_text("#Minecraft server properties\n#date\nlevel-type=minecraft\\:normal\nmotd=A Server\npvp=true\n")
            props = Properties(p)
            self.assertEqual(props.get("level-type"), "minecraft:normal")
            props.set("motd", "§b한글\n둘째 줄")
            props.set("new-key", 5)
            props.save()
            text = p.read_text()
            self.assertTrue(text.startswith("#Minecraft server properties\n#date\n"))
            self.assertIn("motd=\\u00a7b\\ud55c\\uae00\\n\\ub458\\uc9f8 \\uc904", text)
            self.assertEqual(Properties(p).get("motd"), "§b한글\n둘째 줄")
            self.assertEqual(Properties(p).get_int("new-key"), 5)
            self.assertTrue(Properties(p).get_bool("pvp"))


class VersionsTest(unittest.TestCase):
    def test_order(self):
        vs = ["1.21.2-pre1", "1.9", "1.21.2", "1.21.10", "26.1", "1.21.1", "1.21"]
        self.assertEqual(
            sorted(vs, key=versions.version_key),
            ["1.9", "1.21", "1.21.1", "1.21.2-pre1", "1.21.2", "1.21.10", "26.1"],
        )
        self.assertTrue(versions.is_at_least("1.20.5", "1.20.5"))
        self.assertFalse(versions.is_at_least("1.20.4", "1.20.5"))

    def test_guess_java(self):
        with mock.patch.object(versions, "mojang_version_json", side_effect=net.NetError("x")):
            self.assertEqual(versions.required_java("1.12.2"), 8)
            self.assertEqual(versions.required_java("1.20.4"), 17)
            self.assertEqual(versions.required_java("1.21.4"), 21)
            self.assertEqual(versions.required_java("26.1"), 25)

    def test_install_target(self):
        self.assertEqual(javamod.install_target(16), 17)
        self.assertEqual(javamod.install_target(8), 8)
        self.assertEqual(javamod.install_target(21), 21)


class ProviderParsingTest(unittest.TestCase):
    def test_paper(self):
        responses = {
            "https://fill.papermc.io/v3/projects/paper": {
                "project": {"id": "paper"},
                "versions": {"1.21": ["1.21.1", "1.21", "1.21.2-rc1"], "1.20": ["1.20.6", "1.20.1"]},
            },
            "https://fill.papermc.io/v3/projects/paper/versions/1.21.1/builds": [
                {"id": 130, "channel": "STABLE", "downloads": {"server:default": {"url": "U130", "checksums": {"sha256": "aa"}}}},
                {"id": 131, "channel": "BETA", "downloads": {"server:default": {"url": "U131", "checksums": {"sha256": "bb"}}}},
                {"id": 129, "channel": "STABLE", "downloads": {"server:default": {"url": "U129", "checksums": {"sha256": "cc"}}}},
            ],
        }
        p = providers.PaperProvider()
        with mock.patch.object(net, "get_json", lambda url: responses[url]):
            self.assertEqual(p.list_versions(), ["1.21.1", "1.21", "1.20.6", "1.20.1"])
            with mock.patch.object(net, "download") as dl, tempfile.TemporaryDirectory() as d:
                res = p.install(Path(d), "1.21.1", FAKE_JAVA, srv.Task())
        self.assertEqual(dl.call_args.args[0], "U130")
        self.assertEqual(dl.call_args.kwargs["sha256"], "aa")
        self.assertEqual(res["build"], "130")

    def test_vanilla(self):
        manifest = {
            "versions": [
                {"id": "25w10a", "type": "snapshot", "url": "s"},
                {"id": "1.21.4", "type": "release", "url": "r1"},
                {"id": "1.2.5", "type": "release", "url": "r2"},
                {"id": "1.2.4", "type": "release", "url": "r3"},
            ]
        }
        with mock.patch.object(versions, "mojang_manifest", lambda: manifest):
            p = providers.VanillaProvider()
            self.assertEqual(p.list_versions(), ["1.21.4", "1.2.5"])
            self.assertEqual(p.list_versions(True), ["25w10a", "1.21.4", "1.2.5"])

    def test_fabric_and_forge(self):
        fabric = {
            "https://meta.fabricmc.net/v2/versions/game": [
                {"version": "25w10a", "stable": False},
                {"version": "1.21.4", "stable": True},
            ],
        }
        with mock.patch.object(net, "get_json", lambda url: fabric[url]):
            self.assertEqual(providers.FabricProvider().list_versions(), ["1.21.4"])
        promos = {"promos": {"1.20.1-latest": "47.4.0", "1.20.1-recommended": "47.3.0", "1.7.10-latest": "10.13.4.1614"}}
        with mock.patch.object(net, "get_json", lambda url: promos):
            f = providers.ForgeProvider()
            self.assertEqual(f.list_versions(), ["1.20.1", "1.7.10"])
            self.assertEqual(f.forge_version("1.20.1"), "47.3.0")


class NeoForgeTest(unittest.TestCase):
    def test_version_mapping(self):
        m = providers.NeoForgeProvider.mc_version_of
        self.assertEqual(m("21.1.77"), "1.21.1")
        self.assertEqual(m("21.0.5-beta"), "1.21")
        self.assertEqual(m("20.4.237"), "1.20.4")
        self.assertEqual(m("26.1.0.3"), "26.1")
        self.assertEqual(m("26.1.2.7"), "26.1.2")

    def test_list_and_pick(self):
        data = {"versions": ["20.4.237", "21.1.70", "21.1.77", "21.4.1-beta", "26.1.0.3"]}
        with mock.patch.object(net, "get_json", lambda url: data):
            p = providers.NeoForgeProvider()
            self.assertEqual(p.list_versions(), ["26.1", "1.21.1", "1.20.4"])
            self.assertEqual(p.list_versions(True), ["26.1", "1.21.4", "1.21.1", "1.20.4"])
            self.assertEqual(p.loader_version("1.21.1"), "21.1.77")
            self.assertEqual(p.loader_version("1.21.4"), "21.4.1-beta")


class BedrockTest(Base):
    def test_install_update_remove(self):
        from mc_server_maker.core import plugins

        meta = self.create()
        meta.software = "paper"
        api = {
            plugins.GEYSER_API.format(project=p): {
                "build": 900, "downloads": {"spigot": {"name": f"{p.capitalize()}-Spigot.jar", "sha256": "x"}}
            }
            for p in plugins.PROJECTS
        }
        downloads = []

        def fake_download(url, dest, task=None, **kw):
            downloads.append(url)
            Path(dest).write_text("jar")

        with mock.patch.object(net, "get_json", lambda url: api[url]), mock.patch.object(net, "download", fake_download):
            self.assertFalse(plugins.bedrock_installed(meta))
            self.assertEqual(plugins.udp_ports(meta), [])
            plugins.install_bedrock(meta)
        self.assertTrue(plugins.bedrock_installed(meta))
        self.assertEqual(plugins.udp_ports(meta), [19132])
        self.assertTrue(downloads[0].endswith("/geyser/versions/latest/builds/latest/downloads/spigot"))

        cfg = meta.folder / "plugins" / "Geyser-Spigot" / "config.yml"
        cfg.parent.mkdir()
        cfg.write_text("bedrock:\n  # The port\n  address: 0.0.0.0\n  port: 19200\nremote:\n  port: 25565\n")
        self.assertEqual(plugins.bedrock_port(meta), 19200)

        plugins.remove_bedrock(meta)
        self.assertFalse(plugins.bedrock_installed(meta))

    def test_vanilla_not_supported(self):
        from mc_server_maker.core import plugins

        meta = self.create()
        meta.software = "vanilla"
        self.assertFalse(plugins.supports_bedrock(meta))
        with self.assertRaises(ValueError):
            plugins.install_bedrock(meta)


class ServerTest(Base):
    def test_create_random(self):
        meta = self.create(motd="§a안녕")
        self.assertTrue((meta.folder / "server.jar").exists())
        self.assertIn("eula=true", (meta.folder / "eula.txt").read_text())
        props = meta.properties()
        self.assertEqual(props.get("motd"), "§a안녕")
        self.assertEqual(props.get("level-seed"), "")
        self.assertEqual(props.get("level-type"), "minecraft:normal")
        self.assertEqual(props.get("gamemode"), "survival")
        self.assertTrue((meta.folder / "start.sh").exists())
        self.assertIn("-jar server.jar nogui", (meta.folder / "start.bat").read_text())
        loaded = srv.list_servers()
        self.assertEqual([m.name for m in loaded], ["테스트 서버"])
        self.assertEqual(loaded[0].launch, {"type": "jar", "jar": "server.jar"})

    def test_create_requires_eula(self):
        with self.assertRaises(srv.ServerError):
            srv.create_server(srv.CreateOptions(name="x", software="fake", mc_version="1.20.1"))

    def test_create_seed_and_legacy_values(self):
        meta = srv.create_server(
            srv.CreateOptions(
                name="old", software="fake", mc_version="1.12.2", eula_accepted=True, gamemode="creative",
                world=srv.WorldOptions(mode="seed", seed="12345", level_type="flat"),
            )
        )
        props = meta.properties()
        self.assertEqual(props.get("level-seed"), "12345")
        self.assertEqual(props.get("level-type"), "flat")
        self.assertEqual(props.get("gamemode"), "1")
        self.assertEqual(srv.parse_choice("1", srv.GAMEMODES, "survival"), "creative")

    def test_create_import_folder_and_zip(self):
        world = make_world(self.tmp)
        meta = self.create(world=srv.WorldOptions(mode="import", import_path=str(world)))
        self.assertTrue((meta.folder / "world" / "level.dat").exists())
        self.assertTrue((meta.folder / "world" / "region" / "r.0.0.mca").exists())

        zpath = self.tmp / "map.zip"
        with zipfile.ZipFile(zpath, "w") as z:
            z.writestr("Cool Map/level.dat", "lv")
            z.writestr("Cool Map/region/r.0.0.mca", "rg")
        meta2 = self.create(world=srv.WorldOptions(mode="import", import_path=str(zpath)))
        self.assertTrue((meta2.folder / "world" / "level.dat").exists())
        self.assertNotEqual(meta.folder, meta2.folder)

    def test_import_rejects_non_world(self):
        (self.tmp / "empty").mkdir()
        with self.assertRaises(srv.ServerError):
            self.create(world=srv.WorldOptions(mode="import", import_path=str(self.tmp / "empty")))
        self.assertEqual(srv.list_servers(), [])

    def test_failed_create_cleans_up(self):
        with mock.patch.object(FakeProvider, "install", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.create()
        self.assertEqual(list((Path(_TMP) / "servers").iterdir()), [])

    def test_upgrade_with_backup(self):
        meta = self.create()
        make_world(meta.folder, "world")
        meta.properties_path.write_text(meta.properties_path.read_text().replace("minecraft\\:normal", "flat"))
        srv.upgrade_server(meta, "1.21.1", backup_first=True)
        self.assertEqual(srv.ServerMeta.load(meta.folder).mc_version, "1.21.1")
        self.assertEqual((meta.folder / "server.jar").read_text(), "jar 1.21.1")
        self.assertEqual(meta.properties().get("level-type"), "minecraft:flat")
        backups = srv.list_backups(meta)
        self.assertEqual(len(backups), 1)
        with zipfile.ZipFile(backups[0]) as z:
            names = z.namelist()
        self.assertIn("world/level.dat", names)
        self.assertIn("server.jar", names)
        self.assertFalse(any(n.startswith("backups/") for n in names))

    def test_regenerate_and_replace_world(self):
        meta = self.create()
        make_world(meta.folder, "world")
        (meta.folder / "world_nether").mkdir()
        srv.regenerate_world(meta, "777", "amplified")
        self.assertFalse((meta.folder / "world").exists())
        self.assertFalse((meta.folder / "world_nether").exists())
        self.assertEqual(meta.properties().get("level-seed"), "777")
        self.assertEqual(meta.properties().get("level-type"), "minecraft:amplified")
        self.assertEqual(len(srv.list_backups(meta)), 1)

        srv.replace_world_with_import(meta, make_world(self.tmp, "Other"))
        self.assertTrue((meta.folder / "world" / "level.dat").exists())

    def test_launch_args_forge(self):
        meta = self.create()
        meta.launch = {"type": "args", "unix": "libraries/x/unix_args.txt", "win": "libraries/x/win_args.txt"}
        self.assertIn("@libraries/x/win_args.txt", srv.launch_args(meta, windows=True))
        self.assertIn("@libraries/x/unix_args.txt", srv.launch_args(meta, windows=False))


class PlayersTest(unittest.TestCase):
    def test_offline_uuid(self):
        self.assertEqual(players.offline_uuid("Notch"), "b50ad385-829d-3141-a216-7e7d7539ba7f")

    def test_add_remove_offline(self):
        with tempfile.TemporaryDirectory() as d:
            players.add(Path(d), "ops", "Steve", online_mode=False)
            players.add(Path(d), "ops", "Steve", online_mode=False)
            self.assertEqual(players.list_names(Path(d), "ops"), ["Steve"])
            data = json.loads((Path(d) / "ops.json").read_text())
            self.assertEqual(data[0]["level"], 4)
            players.remove(Path(d), "ops", "steve")
            self.assertEqual(players.list_names(Path(d), "ops"), [])


class JavaTest(unittest.TestCase):
    @unittest.skipUnless(shutil.which("java"), "java 없음")
    def test_detect_system_java(self):
        major = javamod.java_major(shutil.which("java"))
        self.assertIsInstance(major, int)
        self.assertGreaterEqual(major, 8)


if __name__ == "__main__":
    unittest.main()
