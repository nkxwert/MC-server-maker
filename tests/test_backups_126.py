"""1.26: backup kinds in file names, pruning automatic backups, restoring a backup."""

import os
import shutil
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mc_server_maker.core import server as srv  # noqa: E402
from mc_server_maker.core.tasks import Cancelled, Task  # noqa: E402


class BackupNameTest(unittest.TestCase):
    def kind(self, name):
        return srv.parse_backup_name(name)[1:3]

    def test_kinds(self):
        self.assertEqual(self.kind("20250101-120000-auto.zip"), ("auto", ""))
        self.assertEqual(self.kind("20250101-120000-auto-2.zip"), ("auto", ""))
        self.assertEqual(self.kind("20250101-120000-world.zip"), ("manual", ""))
        self.assertEqual(self.kind("20250101-120000.zip"), ("manual", ""))
        self.assertEqual(self.kind("20250101-120000-2.zip"), ("manual", ""))
        self.assertEqual(self.kind("20250101-120000-before-restore.zip"), ("restore", ""))
        self.assertEqual(self.kind("20250101-120000-before-1.21.4.zip"), ("update", "1.21.4"))
        self.assertEqual(self.kind("20250101-120000-before-paper-1.21.4.zip"), ("update", "paper-1.21.4"))
        self.assertEqual(self.kind("20250101-120000-world-before-import.zip"), ("other", "world-before-import"))
        self.assertEqual(self.kind("20250101-120000-world-before-reset-3.zip"), ("other", "world-before-reset"))
        self.assertEqual(self.kind("20250101-120000-x.zip"), ("other", "x"))
        self.assertEqual(self.kind("my world.zip"), ("other", "my world"))

    def test_counter_and_time(self):
        when, _, _, seq = srv.parse_backup_name("20250101-120000-auto-2.zip")
        self.assertEqual(seq, 2)
        self.assertIsNotNone(when)
        self.assertIsNone(srv.parse_backup_name("odd.zip")[0])


class _ServerCase(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.meta = srv.ServerMeta(name="b", software="vanilla", mc_version="1.21.4", folder=self.dir / "srv")
        self.meta.folder.mkdir()
        self.world = self.meta.folder / "world"
        self.world.mkdir()
        (self.world / "level.dat").write_bytes(b"current")
        (self.meta.folder / srv.BACKUP_DIR).mkdir()

    def fake(self, name: str, files: dict) -> Path:
        path = self.meta.folder / srv.BACKUP_DIR / name
        with zipfile.ZipFile(path, "w") as z:
            for n, data in files.items():
                z.writestr(n, data)
        return path


class PruneTest(_ServerCase):
    def test_keeps_newest_automatic_and_every_other_kind(self):
        for day in range(1, 8):
            self.fake(f"2025010{day}-120000-auto.zip", {"world/level.dat": b"a"})
        others = ["20250101-110000-world.zip", "20240101-120000-before-1.21.4.zip",
                  "20240101-130000-before-restore.zip", "20240101-140000-world-before-import.zip",
                  "20240101-150000.zip", "odd name.zip"]
        for n in others:
            self.fake(n, {"world/level.dat": b"m"})
        removed = srv.prune_auto_backups(self.meta, 3)
        self.assertEqual(len(removed), 4)
        left = {p.name for p in srv.list_backups(self.meta)}
        self.assertEqual(left, set(others) | {f"2025010{d}-120000-auto.zip" for d in (5, 6, 7)})

    def test_newest_first(self):
        self.fake("20250101-120000-auto.zip", {"world/level.dat": b"a"})
        self.fake("20250101-120000-auto-2.zip", {"world/level.dat": b"a"})
        self.fake("20250102-120000-world.zip", {"world/level.dat": b"a"})
        names = [b.path.name for b in srv.backup_infos(self.meta)]
        self.assertEqual(names, ["20250102-120000-world.zip", "20250101-120000-auto-2.zip", "20250101-120000-auto.zip"])

    def test_auto_backup_name_round_trip(self):
        path = srv.backup_server(self.meta, srv.AUTO_LABEL, worlds_only=True, task=Task(log=lambda m: None))
        self.assertEqual(srv.parse_backup_name(path.name)[1], "auto")
        self.assertFalse(list((self.meta.folder / srv.BACKUP_DIR).glob("*.part")))

    def test_new_meta_fields(self):
        self.meta.auto_backup = True
        self.meta.auto_backup_keep = 10
        self.meta.save()
        loaded = srv.ServerMeta.load(self.meta.folder)
        self.assertTrue(loaded.auto_backup)
        self.assertEqual(loaded.auto_backup_keep, 10)


class RestoreTest(_ServerCase):
    quiet = staticmethod(lambda m: None)

    def test_world_only_backup(self):
        path = self.fake("20250101-120000-world.zip", {
            "world/level.dat": b"old", "world/region/r.0.0.mca": b"r", "world/session.lock": b"",
            "world_nether/DIM-1/region/n.mca": b"n"})
        srv.restore_backup(self.meta, path, Task(log=self.quiet))
        self.assertEqual((self.world / "level.dat").read_bytes(), b"old")
        self.assertEqual((self.world / "region" / "r.0.0.mca").read_bytes(), b"r")
        self.assertFalse((self.world / "session.lock").exists())
        # vanilla reads the Nether inside the world folder
        self.assertEqual((self.world / "DIM-1" / "region" / "n.mca").read_bytes(), b"n")
        kinds = [b.kind for b in srv.backup_infos(self.meta)]
        self.assertIn("restore", kinds)  # the replaced world was kept
        before = next(b for b in srv.backup_infos(self.meta) if b.kind == "restore")
        with zipfile.ZipFile(before.path) as z:
            self.assertEqual(z.read("world/level.dat"), b"current")
        self.assertFalse([p for p in self.meta.folder.iterdir() if p.name.startswith(".restore-")])

    def test_whole_server_backup_restores_only_the_world(self):
        (self.meta.folder / "server.properties").write_text("level-name=world\n", encoding="utf-8")
        path = self.fake("20250101-120000-before-1.21.5.zip", {
            "server.properties": "level-name=main\nmotd=old\n", "server-maker.json": "{}", "server.jar": b"jar",
            "plugins/x.jar": b"p", "plugins/Thing/level.dat": b"not a world", "creative/level.dat": b"other world",
            "main/level.dat": b"main world", "main/data/x.dat": b"d"})
        self.assertTrue(srv.backup_has_server_files(path))
        srv.restore_backup(self.meta, path, Task(log=self.quiet))
        # its own level-name ("main") wins over the other world, and lands in this server's "world"
        self.assertEqual((self.world / "level.dat").read_bytes(), b"main world")
        self.assertEqual((self.world / "data" / "x.dat").read_bytes(), b"d")
        self.assertFalse((self.meta.folder / "server.jar").exists())
        self.assertFalse((self.meta.folder / "plugins").exists())
        self.assertFalse((self.meta.folder / "main").exists())
        self.assertEqual((self.meta.folder / "server.properties").read_text(encoding="utf-8"), "level-name=world\n")

    def test_failures_keep_the_world(self):
        bad = self.fake("20250101-120000-x.zip", {"world/level.dat": b"x", "../evil.txt": b"x"})
        with self.assertRaises(srv.ServerError):
            srv.restore_backup(self.meta, bad, Task(log=self.quiet))
        empty = self.fake("20250101-120001-auto.zip", {"readme.txt": b"no world"})
        with self.assertRaises(srv.ServerError):
            srv.restore_backup(self.meta, empty, Task(log=self.quiet))
        broken = self.meta.folder / srv.BACKUP_DIR / "20250101-120002-auto.zip"
        broken.write_bytes(b"not a zip")
        with self.assertRaises(srv.ServerError):
            srv.restore_backup(self.meta, broken, Task(log=self.quiet))
        self.assertEqual((self.world / "level.dat").read_bytes(), b"current")

    def test_cancel_or_error_while_extracting_keeps_the_world(self):
        good = self.fake("20250101-120000-world.zip", {"world/level.dat": b"old", "world/a.dat": b"a"})
        task = Task(log=self.quiet)
        with mock.patch.object(srv, "_fit_dimensions", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                srv.restore_backup(self.meta, good, task)
        self.assertEqual((self.world / "level.dat").read_bytes(), b"current")
        task.cancelled = True
        with self.assertRaises(Cancelled):
            srv.restore_backup(self.meta, good, task)
        self.assertEqual((self.world / "level.dat").read_bytes(), b"current")
        self.assertFalse([p for p in self.meta.folder.iterdir() if p.name.startswith(".restore-")])


class AutoBackupTest(_ServerCase):
    def test_backup_after_stop_marks_busy_and_prunes(self):
        import time

        from PySide6.QtWidgets import QApplication

        from mc_server_maker.gui import manage
        from mc_server_maker.gui.runner import ServerRunner

        app = QApplication.instance() or QApplication([])
        runner = ServerRunner()
        lines = []
        runner.line.connect(lambda key, text: lines.append(text))
        key = str(self.meta.folder)
        self.meta.save()
        runner.exits[key] = "stopped"
        self.assertFalse(manage.auto_backup_after_stop(runner, key))  # off by default
        import os
        for day in range(1, 4):
            z = self.fake(f"2025010{day}-120000-auto.zip", {"world/level.dat": b"a"})
            os.utime(z, (1735732800 + day * 86400,) * 2)  # files as old as their names
        self.fake("20240101-120000-world.zip", {"world/level.dat": b"m"})
        self.meta.auto_backup, self.meta.auto_backup_keep = True, 3
        self.meta.save()
        runner.exits[key] = "crash"
        self.assertFalse(manage.auto_backup_after_stop(runner, key))  # a crash never rotates backups out
        runner.exits[key] = "stopped"
        self.assertTrue(manage.auto_backup_after_stop(runner, key))
        self.assertIn(key, runner.busy)  # Start waits
        self.assertTrue(manage.auto_backups_running())
        deadline = time.monotonic() + 20
        while manage.auto_backups_running() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        self.assertNotIn(key, runner.busy)
        self.assertTrue(any("Automatic backup saved." in ln for ln in lines), lines)
        kinds = [b.kind for b in srv.backup_infos(self.meta)]
        self.assertEqual(kinds.count("auto"), 3)  # the oldest automatic one made room
        self.assertEqual(kinds.count("manual"), 1)
        self.assertNotIn("20250101-120000-auto.zip", [b.path.name for b in srv.backup_infos(self.meta)])


if __name__ == "__main__":
    unittest.main()


class Review126Test(_ServerCase):
    def test_prune_keeps_the_new_backup_even_if_its_name_sorts_older(self):
        import os
        for day in range(1, 4):
            z = self.fake(f"2025010{day}-120000-auto.zip", {"world/level.dat": b"a"})
            os.utime(z, (1735732800 + day * 86400,) * 2)
        new = self.fake("20241231-090000-auto.zip", {"world/level.dat": b"n"})  # clock was set back
        srv.prune_auto_backups(self.meta, 3, protect=new)
        names = [b.path.name for b in srv.backup_infos(self.meta)]
        self.assertIn(new.name, names)
        self.assertEqual(sum(1 for n in names if n.endswith("-auto.zip")), 3)

    def test_failed_swap_puts_the_old_world_back(self):
        from unittest import mock
        level = srv.level_name(self.meta)
        before = sorted(p.name for p in (self.meta.folder / level).iterdir())
        staging = self.meta.folder / ".staging-test"
        (staging / level).mkdir(parents=True)
        (staging / level / "level.dat").write_bytes(b"new")
        with mock.patch("shutil.move", side_effect=OSError("locked")):
            with self.assertRaises(OSError):
                srv._swap_in_world(self.meta, staging, level, srv.Task())
        self.assertEqual(sorted(p.name for p in (self.meta.folder / level).iterdir()), before)
        self.assertFalse(any(p.name.startswith(f".{level}.old-") for p in self.meta.folder.iterdir()))
