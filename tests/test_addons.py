"""Plugins / mods: reading jars, on/off, compatibility. Tunnel helpers."""

import json
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path

from mc_server_maker.core import addons, tunnel
from mc_server_maker.core.server import ServerMeta


def make_jar(path: Path, files: dict) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, data in files.items():
            z.writestr(name, data)
    return path


class AddonsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.src = self.tmp / "downloads"
        self.src.mkdir()
        self.plugin = make_jar(self.src / "EssentialsX-2.20.1.jar", {
            "plugin.yml": "name: Essentials\nversion: '2.20.1'\nauthors: [md_5, SupaHam]\nmain: x.Y\n",
        })
        self.fabric = make_jar(self.src / "sodium.jar", {
            "fabric.mod.json": json.dumps({"id": "sodium", "name": "Sodium", "version": "0.6.0",
                                           "authors": ["JellySquid", {"name": "IMS"}]}),
        })
        self.forge = make_jar(self.src / "jei.jar", {
            "META-INF/mods.toml": 'modLoader="javafml"\n[[mods]]\nmodId="jei"\nversion="${file.jarVersion}"\n'
                                  'displayName="Just Enough Items"\nauthors="mezz"\n',
            "META-INF/MANIFEST.MF": "Manifest-Version: 1.0\nImplementation-Version: 15.2.0\n",
        })
        self.neo = make_jar(self.src / "create.jar", {
            "META-INF/neoforge.mods.toml": '[[mods]]\nmodId="create"\nversion="6.0.1"\ndisplayName="Create"\n',
        })

    def meta(self, software):
        folder = self.tmp / software
        folder.mkdir(exist_ok=True)
        return ServerMeta(name="s", software=software, mc_version="1.21.1", folder=folder)

    def test_read_info(self):
        p = addons.read_info(self.plugin)
        self.assertEqual((p.kind, p.name, p.version, p.authors), ("plugin", "Essentials", "2.20.1", ["md_5", "SupaHam"]))
        f = addons.read_info(self.fabric)
        self.assertEqual((f.kind, f.name, f.version, f.authors), ("fabric", "Sodium", "0.6.0", ["JellySquid", "IMS"]))
        j = addons.read_info(self.forge)
        self.assertEqual((j.kind, j.name, j.version, j.authors), ("forge", "Just Enough Items", "15.2.0", ["mezz"]))
        c = addons.read_info(self.neo)
        self.assertEqual((c.kind, c.name), ("neoforge", "Create"))
        broken = self.src / "broken.jar"
        broken.write_bytes(b"not a zip")
        self.assertEqual(addons.read_info(broken).kind, "unknown")

    def test_folders_and_labels(self):
        self.assertEqual(addons.kind_label(self.meta("paper")), "Plugins")
        self.assertEqual(addons.kind_label(self.meta("neoforge")), "Mods")
        self.assertEqual(addons.kind_label(self.meta("vanilla")), "")
        self.assertIsNone(addons.addon_dir(self.meta("vanilla")))
        with self.assertRaises(ValueError):
            addons.add_files(self.meta("vanilla"), [self.plugin])

    def test_add_toggle_remove(self):
        meta = self.meta("paper")
        results = addons.add_files(meta, [self.plugin, self.fabric, self.tmp / "readme.txt"])
        self.assertEqual(len(results), 2)  # non-jar ignored
        warnings = {a.name: w for a, w in results}
        self.assertEqual(warnings["Essentials"], "")
        self.assertIn("Fabric", warnings["Sodium"])

        items = addons.list_addons(meta)
        ess = next(a for a in items if a.name == "Essentials")
        addons.set_enabled(ess, False)
        self.assertTrue((meta.folder / "plugins" / "EssentialsX-2.20.1.jar.disabled").exists())
        self.assertFalse((meta.folder / "plugins" / "EssentialsX-2.20.1.jar").exists())
        again = next(a for a in addons.list_addons(meta) if a.name == "Essentials")
        self.assertFalse(again.enabled)
        self.assertEqual(again.file_name, "EssentialsX-2.20.1.jar")

        # adding the same jar again replaces the disabled copy
        addons.add_files(meta, [self.plugin])
        self.assertFalse((meta.folder / "plugins" / "EssentialsX-2.20.1.jar.disabled").exists())
        ess = next(a for a in addons.list_addons(meta) if a.name == "Essentials")
        self.assertTrue(ess.enabled)

        addons.remove(ess)
        self.assertEqual([a.name for a in addons.list_addons(meta)], ["Sodium"])

    def test_neoforge_accepts_old_forge_mods(self):
        meta = self.meta("neoforge")
        self.assertEqual(addons.compatibility_warning(meta, addons.read_info(self.forge)), "")
        self.assertEqual(addons.compatibility_warning(meta, addons.read_info(self.neo)), "")
        self.assertNotEqual(addons.compatibility_warning(meta, addons.read_info(self.fabric)), "")


class TunnelTest(unittest.TestCase):
    ASSETS = [{"name": n, "browser_download_url": "u/" + n} for n in (
        "playit-linux-aarch64", "playit-linux-amd64", "playit-linux-amd64.deb",
        "playit-windows-x86_64.exe", "playit-windows-x86_64-signed.exe", "playit-windows-x86-signed.exe",
    )]

    def test_pick_asset(self):
        self.assertEqual(tunnel.pick_asset(self.ASSETS, "Windows", "AMD64")["name"], "playit-windows-x86_64-signed.exe")
        self.assertEqual(tunnel.pick_asset(self.ASSETS, "Linux", "x86_64")["name"], "playit-linux-amd64")
        self.assertEqual(tunnel.pick_asset(self.ASSETS, "Linux", "aarch64")["name"], "playit-linux-aarch64")
        self.assertIsNone(tunnel.pick_asset(self.ASSETS, "Darwin", "arm64"))

    def test_parse_output(self):
        log = ("INFO agent starting\nVisit link to setup https://playit.gg/claim/ab12cd34ef\n"
               "tunnel running: cool-name.gl.joinmc.link => 127.0.0.1:25565\n")
        self.assertEqual(tunnel.find_claim_url(log), "https://playit.gg/claim/ab12cd34ef")
        self.assertEqual(tunnel.find_address(log), "cool-name.gl.joinmc.link")
        self.assertEqual(tunnel.find_address("addr: Fun-Site.at.ply.gg:28575"), "fun-site.at.ply.gg:28575")
        self.assertIsNone(tunnel.find_address("nothing here playit.gg/claim/x"))


if __name__ == "__main__":
    unittest.main()
