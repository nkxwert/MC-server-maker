"""App self-update: changelog, release selection, EXE swap."""

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from mc_server_maker import APP_VERSION
from mc_server_maker.core import net, updater

ROOT = Path(__file__).resolve().parents[1]


def release(tag, body="", assets=("Bartizan.exe", "Bartizan.exe.sha256"), **kw):
    return {"tag_name": tag, "body": body, "html_url": f"https://x/{tag}",
            "assets": [{"name": n, "browser_download_url": f"https://dl/{tag}/{n}"} for n in assets], **kw}


class ChangelogTest(unittest.TestCase):
    def test_current_version_has_notes(self):
        # bumping APP_VERSION without a CHANGELOG entry must fail CI (the release would have no notes)
        langs = updater.parse_changelog((ROOT / "CHANGELOG.md").read_text(encoding="utf-8")).get(APP_VERSION)
        self.assertIsNotNone(langs, f"CHANGELOG.md needs a '## {APP_VERSION}' section")
        self.assertTrue(langs.get("en") and langs.get("ko"))

    def test_release_body_and_language(self):
        text = "# C\n## 2.0.0\n### en\n- New thing\n### ko\n- 새 기능\n## 1.0.0\n### en\n- Old\n"
        body = updater.release_body(text, "2.0.0")
        self.assertEqual(updater.notes_for_language(body, "ko"), "- 새 기능")
        self.assertEqual(updater.notes_for_language(body, "en"), "- New thing")
        self.assertEqual(updater.notes_for_language(updater.release_body(text, "1.0.0"), "ko"), "- Old")  # falls back
        self.assertEqual(updater.notes_for_language("plain notes", "ko"), "plain notes")
        with self.assertRaises(updater.UpdateError):
            updater.release_body(text, "3.0.0")


class CheckTest(unittest.TestCase):
    def test_picks_newest_and_collects_notes(self):
        releases = [
            release("v1.4.0", "<!-- lang:en -->\n- old"),
            release("v1.7.0", "<!-- lang:en -->\n- seven\n<!-- lang:ko -->\n- 칠"),
            release("v1.6.0", "<!-- lang:en -->\n- six"),
            release("v1.8.0", "draft", draft=True),
            release("v2.0.0-beta", "pre", prerelease=True),
        ]
        with mock.patch.object(net, "get_json", return_value=releases):
            info = updater.check("1.5.0")
            self.assertEqual(info.version, "1.7.0")
            self.assertEqual(info.exe_url, "https://dl/v1.7.0/Bartizan.exe")
            self.assertTrue(info.sha256_url.endswith(".sha256"))
            self.assertEqual([v for v, _ in info.notes], ["1.7.0", "1.6.0"])
            text = info.notes_text("ko")
            self.assertIn("### v1.7.0\n- 칠", text)
            self.assertIn("### v1.6.0\n- six", text)
            self.assertIsNone(updater.check("1.7.0"))
            self.assertIsNone(updater.check("1.10.0"))

    def test_version_compare(self):
        self.assertGreater(updater.parse_version("v1.10.0"), updater.parse_version("1.9.9"))
        self.assertEqual(updater.parse_version("v1.6"), (1, 6))


class InstallTest(unittest.TestCase):
    def test_install_starts_the_new_exe_as_installer(self):
        with tempfile.TemporaryDirectory() as d:
            exe = Path(d) / "Bartizan.exe"
            exe.write_text("old")
            new = Path(d) / "update" / "Bartizan.exe"
            new.parent.mkdir()
            new.write_text("new")
            with mock.patch.object(sys, "executable", str(exe)), \
                    mock.patch.object(updater.subprocess, "Popen") as popen:
                updater.install_and_restart(new)
            args = popen.call_args[0][0]
            self.assertEqual(args[:3], [str(new), updater.INSTALL_ARG, str(exe)])
            self.assertEqual(exe.read_text(), "old")  # nothing is renamed next to the app
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["Bartizan.exe", "update"])

    def test_installer_copies_itself_over_the_target_and_restarts(self):
        with tempfile.TemporaryDirectory() as d:
            target = Path(d) / "Bartizan.exe"
            target.write_text("old")
            me = Path(d) / "tmp" / "Bartizan.exe"
            me.parent.mkdir()
            me.write_text("new")
            with mock.patch.object(sys, "executable", str(me)), \
                    mock.patch.object(updater.subprocess, "Popen") as popen:
                self.assertTrue(updater.run_installer(["x", updater.INSTALL_ARG, str(target), "0"]))
            self.assertEqual(target.read_text(), "new")
            self.assertEqual(sorted(p.name for p in Path(d).iterdir()), ["Bartizan.exe", "tmp"])  # no .tmp/.old
            self.assertEqual(popen.call_args[0][0], [str(target)])
            self.assertNotIn("BARTIZAN_UPDATE_FAILED", popen.call_args[1]["env"])
        self.assertFalse(updater.run_installer(["Bartizan.exe"]))


if __name__ == "__main__":
    unittest.main()
