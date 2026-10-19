"""Regression tests for world import / backup / Modrinth update bugs (QA review for 1.24)."""

import shutil
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from mc_server_maker.core import modrinth, net
from mc_server_maker.core import server as srv
from mc_server_maker.core.tasks import Cancelled, Task
from tests.test_modrinth import FakeModrinth, _version


def _world(folder: Path, tag: bytes, nether: bool = False, end: bool = False) -> Path:
    (folder / "region").mkdir(parents=True)
    (folder / "level.dat").write_bytes(tag)
    (folder / "region" / "r.0.0.mca").write_bytes(tag)
    if nether:
        (folder / "DIM-1" / "region").mkdir(parents=True)
        (folder / "DIM-1" / "region" / "r.0.0.mca").write_bytes(tag + b"-nether")
    if end:
        (folder / "DIM1" / "region").mkdir(parents=True)
        (folder / "DIM1" / "region" / "r.0.0.mca").write_bytes(tag + b"-end")
    return folder


def _paper_world(root: Path, tag: bytes, name: str = "world") -> Path:
    """world/, world_nether/DIM-1, world_the_end/DIM1 like Paper writes them."""
    main = _world(root / name, tag)
    for suffix, dim in (("_nether", "DIM-1"), ("_the_end", "DIM1")):
        d = root / (name + suffix)
        (d / dim / "region").mkdir(parents=True)
        (d / "level.dat").write_bytes(tag)
        (d / dim / "region" / "r.0.0.mca").write_bytes(tag + b"-" + dim.encode())
    return main


def _zip(folder: Path, dest: Path) -> Path:
    with zipfile.ZipFile(dest, "w") as z:
        for p in sorted(folder.rglob("*")):
            if p.is_file():
                z.write(p, p.relative_to(folder).as_posix())
    return dest


class Base(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)

    def server(self, software: str = "vanilla", level: str = "world") -> srv.ServerMeta:
        meta = srv.ServerMeta(name="s", software=software, mc_version="1.21.4", folder=self.dir / f"srv-{software}")
        meta.folder.mkdir()
        (meta.folder / "server.properties").write_text(f"level-name={level}\n")
        _world(meta.folder / level, b"old", nether=True)
        return meta


class ImportCancelTest(Base):
    def test_cancel_during_copy_keeps_old_world(self):
        meta = self.server()
        src = _world(self.dir / "new", b"new", nether=True)
        task = Task()
        real_copy2 = shutil.copy2

        def copy2(s, d, *a, **kw):  # cancel after the first world file is copied
            task.cancelled = True
            return real_copy2(s, d, *a, **kw)

        with mock.patch.object(srv.shutil, "copy2", copy2), self.assertRaises(Cancelled):
            srv.replace_world_with_import(meta, src, task)
        self.assertEqual((meta.folder / "world" / "level.dat").read_bytes(), b"old")
        self.assertTrue((meta.folder / "world" / "DIM-1").is_dir())
        self.assertEqual([p for p in meta.folder.iterdir() if p.name.startswith(".import-")], [])
        self.assertEqual(len(srv.list_backups(meta)), 1)  # the backup made before stays

    def test_cancel_during_zip_extract_keeps_old_world(self):
        meta = self.server()
        z = _zip(_world(self.dir / "new", b"new").parent, self.dir / "new.zip")
        task = Task()
        real = zipfile.ZipFile.extract

        def extract(zf, *a, **kw):
            task.cancelled = True
            return real(zf, *a, **kw)

        with mock.patch.object(zipfile.ZipFile, "extract", extract), self.assertRaises(Cancelled):
            srv.replace_world_with_import(meta, z, task)
        self.assertEqual((meta.folder / "world" / "level.dat").read_bytes(), b"old")
        self.assertEqual([p for p in meta.folder.iterdir() if p.name.startswith(".import-")], [])


class DimensionLayoutTest(Base):
    def test_paper_layout_into_vanilla_merges(self):
        for software in ("vanilla", "fabric", "forge", "neoforge"):
            with self.subTest(software=software):
                meta = self.server(software)
                src_root = self.dir / f"paper-{software}"
                _paper_world(src_root, b"new")
                srv.replace_world_with_import(meta, src_root / "world", Task())
                w = meta.folder / "world"
                self.assertEqual((w / "DIM-1" / "region" / "r.0.0.mca").read_bytes(), b"new-DIM-1")
                self.assertEqual((w / "DIM1" / "region" / "r.0.0.mca").read_bytes(), b"new-DIM1")
                self.assertFalse((meta.folder / "world_nether").exists())
                self.assertFalse((meta.folder / "world_the_end").exists())

    def test_paper_layout_zip_into_vanilla_merges(self):
        meta = self.server()
        _paper_world(self.dir / "paper", b"new")
        z = _zip(self.dir / "paper", self.dir / "paper.zip")
        srv.replace_world_with_import(meta, z, Task())
        self.assertEqual((meta.folder / "world" / "DIM-1" / "region" / "r.0.0.mca").read_bytes(), b"new-DIM-1")
        self.assertFalse((meta.folder / "world_nether").exists())

    def test_vanilla_layout_into_paper_splits(self):
        for software in ("paper", "purpur"):
            with self.subTest(software=software):
                meta = self.server(software)
                src = _world(self.dir / f"van-{software}" / "world", b"new", nether=True, end=True)
                srv.replace_world_with_import(meta, src, Task())
                f = meta.folder
                self.assertEqual((f / "world_nether" / "DIM-1" / "region" / "r.0.0.mca").read_bytes(), b"new-nether")
                self.assertEqual((f / "world_the_end" / "DIM1" / "region" / "r.0.0.mca").read_bytes(), b"new-end")
                self.assertEqual((f / "world_nether" / "level.dat").read_bytes(), b"new")
                self.assertFalse((f / "world" / "DIM-1").exists())
                self.assertFalse((f / "world" / "DIM1").exists())

    def test_vanilla_zip_into_paper_splits(self):
        meta = self.server("paper")
        _world(self.dir / "van" / "world", b"new", nether=True)
        z = _zip(self.dir / "van", self.dir / "van.zip")
        srv.replace_world_with_import(meta, z, Task())
        self.assertEqual((meta.folder / "world_nether" / "DIM-1" / "region" / "r.0.0.mca").read_bytes(),
                         b"new-nether")

    def test_both_layouts_keep_the_matching_one(self):
        root = self.dir / "both"
        _paper_world(root, b"new")
        (root / "world" / "DIM-1").mkdir()
        (root / "world" / "DIM-1" / "vanilla.txt").write_bytes(b"v")
        meta = self.server()
        srv.replace_world_with_import(meta, root / "world", Task())
        self.assertTrue((meta.folder / "world" / "DIM-1" / "vanilla.txt").exists())  # not overwritten
        self.assertFalse((meta.folder / "world" / "DIM-1" / "region").exists())
        paper = self.server("paper")
        srv.replace_world_with_import(paper, root / "world", Task())
        self.assertEqual((paper.folder / "world_nether" / "DIM-1" / "region" / "r.0.0.mca").read_bytes(),
                         b"new-DIM-1")
        self.assertFalse((paper.folder / "world_nether" / "DIM-1" / "vanilla.txt").exists())


class BackupNameTest(Base):
    def test_same_second_backups_dont_overwrite(self):
        meta = self.server()
        with mock.patch.object(srv.time, "strftime", return_value="20260101-120000"):
            a = srv.backup_server(meta, "x", worlds_only=True, task=Task())
            (meta.folder / "world" / "level.dat").write_bytes(b"changed")
            b = srv.backup_server(meta, "x", worlds_only=True, task=Task())
            c = srv.backup_server(meta, "x", worlds_only=True, task=Task())
        self.assertEqual(len({a, b, c}), 3)
        self.assertEqual(b.name, "20260101-120000-x-2.zip")
        with zipfile.ZipFile(a) as z:
            self.assertEqual(z.read("world/level.dat"), b"old")
        with zipfile.ZipFile(b) as z:
            self.assertEqual(z.read("world/level.dat"), b"changed")
        self.assertEqual(len(srv.list_backups(meta)), 3)


class NestedLevelNameTest(Base):
    def test_backup_of_nested_level_name_can_be_imported(self):
        meta = self.server("paper", level="worlds/main")
        nether = meta.folder / "worlds" / "main_nether" / "DIM-1"
        nether.mkdir(parents=True)
        (nether / "n.mca").write_bytes(b"paper-nether")
        shutil.rmtree(meta.folder / "worlds" / "main" / "DIM-1")
        backup = srv.backup_server(meta, "nested", task=Task())
        self.assertEqual(srv.find_world_root(backup), backup)
        # restore into a vanilla server: the Nether moves into the world folder
        target = self.server("vanilla")
        srv.replace_world_with_import(target, backup, Task())
        self.assertEqual((target.folder / "world" / "level.dat").read_bytes(), b"old")
        self.assertEqual((target.folder / "world" / "DIM-1" / "n.mca").read_bytes(), b"paper-nether")
        self.assertFalse((target.folder / "world_nether").exists())

    def test_shallowest_wins_and_traversal_rejected(self):
        root = self.dir / "deep"
        _world(root / "a" / "b" / "deeper", b"deep")
        _world(root / "z" / "main", b"main")
        _world(root / "a" / "main_nether", b"nether")
        self.assertEqual(srv.find_world_root(root), root / "z" / "main")  # overworld before _nether
        _world(root / "b" / "world", b"w")
        self.assertEqual(srv.find_world_root(root), root / "b" / "world")  # same depth: by name
        _world(root / "top", b"t")
        self.assertEqual(srv.find_world_root(root), root / "top")  # shallowest
        bad = self.dir / "bad.zip"
        with zipfile.ZipFile(bad, "w") as z:
            z.writestr("../evil/level.dat", b"x")
        with self.assertRaises(srv.ServerError):
            srv.find_world_root(bad)
        with zipfile.ZipFile(self.dir / "none.zip", "w") as z:
            z.writestr("readme.txt", b"x")
        with self.assertRaises(srv.ServerError):
            srv.find_world_root(self.dir / "none.zip")


class ModrinthUpdateDepsTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.meta = srv.ServerMeta(name="m", software="fabric", mc_version="1.21.4", folder=self.dir)
        self.fake = FakeModrinth()
        for name in ("get_json", "post_json", "download"):
            patcher = mock.patch.object(net, name, getattr(self.fake, name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_update_installs_new_required_dependency(self):
        old = _version("c1", "c", "1.0", "c-1.0.jar", b"C1", deps=["have"])
        new = _version("c2", "c", "2.0", "c-2.0.jar", b"C2", deps=["have", "lib"])
        self.fake.add(old, b"C1")
        self.fake.contents[new["files"][0]["url"]] = b"C2"
        self.fake.add(_version("have1", "have", "1.0", "have.jar", b"H1"), b"H1")
        self.fake.add(_version("lib1", "lib", "1.0", "lib.jar", b"L1"), b"L1")
        self.fake.versions["have"].insert(0, _version("have2", "have", "2.0", "have-2.jar", b"H2"))
        self.fake.contents[self.fake.versions["have"][0]["files"][0]["url"]] = b"H2"
        mods = self.dir / "mods"
        mods.mkdir()
        (mods / "c-1.0.jar").write_bytes(b"C1")
        (mods / "have.jar").write_bytes(b"H1")
        self.fake.latest[old["files"][0]["hashes"]["sha1"]] = new
        updates, _ = modrinth.check_updates(self.meta)
        path = modrinth.apply_update(self.meta, updates[0], Task())
        self.assertEqual(path, mods / "c-2.0.jar")
        # lib newly required -> installed; "have" already there -> left alone
        self.assertEqual(sorted(p.name for p in mods.iterdir()), ["c-2.0.jar", "have.jar", "lib.jar"])


if __name__ == "__main__":
    unittest.main()
