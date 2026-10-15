"""Modrinth search / install / update against a fake API (no network)."""

import hashlib
import json
import shutil
import tempfile
import unittest
import urllib.parse
from pathlib import Path
from unittest import mock

from mc_server_maker.core import modrinth, net
from mc_server_maker.core import server as srv


def _version(vid, pid, number, filename, content, deps=(), vtype="release"):
    return {
        "id": vid, "project_id": pid, "version_number": number, "version_type": vtype,
        "dependencies": [{"project_id": d, "dependency_type": "required"} for d in deps],
        "files": [{"url": f"https://cdn.example/{vid}", "filename": filename, "primary": True,
                   "hashes": {"sha1": hashlib.sha1(content).hexdigest(),
                              "sha512": hashlib.sha512(content).hexdigest()}}],
    }


class FakeModrinth:
    def __init__(self):
        self.contents = {}  # download url -> bytes
        self.versions = {}  # project id -> [versions newest first]
        self.latest = {}  # sha1 -> newest version (for /version_files/update)
        self.calls = []

    def add(self, version, content):
        self.contents[version["files"][0]["url"]] = content
        self.versions.setdefault(version["project_id"], []).append(version)

    def by_hash(self):
        out = {}
        for vs in self.versions.values():
            for v in vs:
                out[v["files"][0]["hashes"]["sha1"]] = v
        return out

    def get_json(self, url):
        self.calls.append(url)
        u = urllib.parse.urlparse(url)
        q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
        if u.path.endswith("/search"):
            self.last_facets = json.loads(q["facets"])
            return {"total_hits": 2, "hits": [
                {"project_id": "srv", "slug": "srv", "title": "Server Mod", "server_side": "required",
                 "client_side": "required", "downloads": 1234},
                {"project_id": "map", "slug": "minimap", "title": "Minimap", "server_side": "unsupported"},
            ]}
        if "/project/" in u.path and u.path.endswith("/version"):
            return self.versions.get(u.path.split("/")[-2], [])
        raise AssertionError(url)

    def post_json(self, url, payload):
        self.calls.append(url)
        known = self.by_hash()
        if url.endswith("/version_files/update"):
            return {h: self.latest[h] for h in payload["hashes"] if h in self.latest}
        if url.endswith("/version_files"):
            return {h: known[h] for h in payload["hashes"] if h in known}
        raise AssertionError(url)

    def download(self, url, dest, task=None, **hashes):
        data = self.contents[url]
        assert hashlib.sha512(data).hexdigest() == hashes["sha512"]
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        Path(dest).write_bytes(data)
        return Path(dest)


class ModrinthTest(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.meta = srv.ServerMeta(name="m", software="fabric", mc_version="1.21.4", folder=self.dir)
        self.fake = FakeModrinth()
        for name in ("get_json", "post_json", "download"):
            patcher = mock.patch.object(net, name, getattr(self.fake, name))
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_search_filters_for_this_server(self):
        hits, total = modrinth.search(self.meta, "map")
        self.assertEqual([h.id for h in hits], ["srv"])  # client-only minimap hidden
        self.assertEqual(self.fake.last_facets,
                         [["project_type:mod"], ["categories:fabric"], ["versions:1.21.4"]])
        paper = srv.ServerMeta(name="p", software="paper", mc_version="1.21.4", folder=self.dir)
        modrinth.search(paper)
        self.assertEqual(self.fake.last_facets,
                         [["categories:paper", "categories:spigot", "categories:bukkit"], ["versions:1.21.4"]])

    def test_install_with_required_dependency(self):
        self.fake.add(_version("a2", "a", "2.0", "../../evil-a-2.0.jar", b"A2", deps=["api"]), b"A2")
        self.fake.add(_version("a1", "a", "1.0", "a-1.0.jar", b"A1"), b"A1")
        self.fake.add(_version("api1", "api", "0.9", "fabric-api.jar", b"API"), b"API")
        files = modrinth.install(self.meta, "a")
        mods = self.dir / "mods"
        self.assertEqual(sorted(files), ["evil-a-2.0.jar", "fabric-api.jar"])  # no path escape
        self.assertTrue((mods / "evil-a-2.0.jar").exists() and (mods / "fabric-api.jar").exists())
        self.assertEqual(set(modrinth.installed(self.meta)), {"a", "api"})

    def test_prefers_release_and_errors_without_version(self):
        self.fake.add(_version("b3", "b", "3.0-beta", "b3.jar", b"B3", vtype="beta"), b"B3")
        self.fake.add(_version("b2", "b", "2.0", "b2.jar", b"B2"), b"B2")
        self.assertEqual(modrinth.install(self.meta, "b"), ["b2.jar"])
        with self.assertRaises(modrinth.ModrinthError):
            modrinth.install(self.meta, "nothing")

    def test_update_keeps_disabled_and_removes_old(self):
        old = _version("c1", "c", "1.0", "c-1.0.jar", b"C1")
        new = _version("c2", "c", "2.0", "c-2.0.jar", b"C2")
        self.fake.add(old, b"C1")
        self.fake.contents[new["files"][0]["url"]] = b"C2"
        mods = self.dir / "mods"
        mods.mkdir()
        (mods / "c-1.0.jar.disabled").write_bytes(b"C1")
        (mods / "handmade.jar").write_bytes(b"???")
        self.fake.latest[old["files"][0]["hashes"]["sha1"]] = new
        updates, unknown = modrinth.check_updates(self.meta)
        self.assertEqual(unknown, 1)
        self.assertEqual([(u.old_version, u.new["version_number"]) for u in updates], [("1.0", "2.0")])
        modrinth.apply_update(self.meta, updates[0])
        self.assertEqual(sorted(p.name for p in mods.iterdir()), ["c-2.0.jar.disabled", "handmade.jar"])


if __name__ == "__main__":
    unittest.main()
