"""1.26: the player manager's file edits while the server is stopped."""

import json
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mc_server_maker.core import players


def _uuid(n: int) -> str:
    return f"00000000-0000-0000-0000-{n:012d}"


class PlayerFilesTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        # online-mode lookups go to Mojang: answered here instead
        self.lookup = mock.patch.object(players.net, "get_json",
                                        side_effect=lambda url: {"name": url.rsplit("/", 1)[-1].capitalize(),
                                                                 "id": "0" * 31 + "1"})
        self.mojang = self.lookup.start()
        self.addCleanup(self.lookup.stop)

    def read(self, kind):
        return json.loads((self.dir / f"{kind}.json").read_text(encoding="utf-8"))

    def test_whitelist_add_remove(self):
        name = players.add(self.dir, "whitelist", "steve", online_mode=True)
        self.assertEqual(name, "Steve")  # the exact name from Mojang
        self.assertEqual(self.read("whitelist"), [{"uuid": "00000000-0000-0000-0000-000000000001", "name": "Steve"}])
        players.remove(self.dir, "whitelist", "STEVE")
        self.assertEqual(self.read("whitelist"), [])

    def test_failed_lookup_changes_nothing(self):
        self.mojang.side_effect = players.net.NetError("404")
        with self.assertRaises(players.PlayerError):
            players.add(self.dir, "whitelist", "nobody", online_mode=True)
        self.assertFalse((self.dir / "whitelist.json").exists())

    def test_known_player_needs_no_lookup(self):
        (self.dir / "usercache.json").write_text(json.dumps(
            [{"name": "Alex", "uuid": _uuid(7), "expiresOn": "2026-01-01 00:00:00 +0000"}]), encoding="utf-8")
        players.add(self.dir, "ops", "alex", online_mode=True)
        self.mojang.assert_not_called()
        self.assertEqual(self.read("ops"), [{"uuid": _uuid(7), "name": "Alex", "level": 4, "bypassesPlayerLimit": False}])
        players.remove(self.dir, "ops", "Alex")
        self.assertEqual(self.read("ops"), [])

    def test_offline_op_uses_offline_uuid(self):
        players.add(self.dir, "ops", "Steve", online_mode=False)
        self.mojang.assert_not_called()
        self.assertEqual(self.read("ops")[0]["uuid"], players.offline_uuid("Steve"))

    def test_ban_and_pardon(self):
        players.ban(self.dir, "Griefer", online_mode=False, reason="TNT at spawn")
        players.ban(self.dir, "Griefer", online_mode=False)  # banned again: one entry
        bans = self.read("banned-players")
        self.assertEqual(len(bans), 1)
        self.assertEqual(bans[0]["name"], "Griefer")
        self.assertEqual(bans[0]["expires"], "forever")
        players.pardon(self.dir, "griefer")
        self.assertEqual(self.read("banned-players"), [])

    def test_broken_file_is_not_overwritten(self):
        (self.dir / "banned-players.json").write_text("{broken", encoding="utf-8")
        with self.assertRaises(players.PlayerError):
            players.pardon(self.dir, "x")
        self.assertEqual((self.dir / "banned-players.json").read_text(encoding="utf-8"), "{broken")

    def test_roster(self):
        (self.dir / "ops.json").write_text(json.dumps([{"uuid": _uuid(1), "name": "Steve", "level": 4}]), encoding="utf-8")
        (self.dir / "whitelist.json").write_text(json.dumps(
            [{"uuid": _uuid(1), "name": "Steve"}, {"uuid": _uuid(2), "name": "alex"}]), encoding="utf-8")
        (self.dir / "banned-players.json").write_text(json.dumps(
            [{"uuid": _uuid(3), "name": "Bad", "reason": "griefing"}]), encoding="utf-8")
        cache = [{"name": f"Visitor{i}", "uuid": _uuid(10 + i), "expiresOn": f"2026-01-{i + 1:02d} 00:00:00 +0000"}
                 for i in range(25)]
        (self.dir / "usercache.json").write_text(json.dumps(cache), encoding="utf-8")
        people = players.roster(self.dir, online=["Zed", "steve"], recent=20)
        by_name = {p.name.lower(): p for p in people}
        self.assertEqual([p.name for p in people[:2]], ["steve", "Zed"])  # online first
        self.assertTrue(by_name["steve"].op and by_name["steve"].whitelisted and by_name["steve"].online)
        self.assertTrue(by_name["bad"].banned)
        self.assertEqual(by_name["bad"].ban_reason, "griefing")
        self.assertIn("visitor24", by_name)  # the most recent visitors only
        self.assertNotIn("visitor4", by_name)
        self.assertEqual(len(people), 3 + 1 + 20)


if __name__ == "__main__":
    unittest.main()


class OfflineUuidTest(unittest.TestCase):
    def test_online_mode_ignores_offline_uuid_from_files(self):
        import json
        import tempfile
        from pathlib import Path
        from unittest import mock

        from mc_server_maker.core import players
        d = Path(tempfile.mkdtemp())
        offline = players.lookup_uuid("Griefer", False)[1]
        (d / "usercache.json").write_text(json.dumps([{"name": "Griefer", "uuid": offline}]), encoding="utf-8")
        real = "069a79f4-44e9-4726-a5be-fca90e38aaf5"
        with mock.patch.object(players, "lookup_uuid", return_value=("Griefer", real)):
            players.ban(d, "Griefer", True)
        data = json.loads((d / "banned-players.json").read_text(encoding="utf-8"))
        self.assertEqual(data[0]["uuid"], real)
