"""Every t("...") string must have a Korean translation."""

import ast
import unittest
from pathlib import Path

from mc_server_maker import i18n
from mc_server_maker.i18n_ko import KO

ROOT = Path(__file__).resolve().parents[1] / "mc_server_maker"
# labels passed through t() indirectly (lists / class attributes)
INDIRECT = [
    "Survival", "Creative", "Adventure", "Spectator", "Peaceful", "Easy", "Normal", "Hard",
    "Default", "Flat", "Large biomes", "Amplified",
    "Console", "Server status", "Settings", "World", "Network",
    "Operators (OP)", "Whitelist",
    "Online mode", "PvP", "Hardcore", "Whitelist only", "Allow flight", "Command blocks",
    "Players must sign in with a real Minecraft account. "
    "Turn it off to let non-premium accounts join (anyone can then use any name).",
    "One life: players become spectators when they die.",
    "Only players on the whitelist can join. Add a friend in the console: whitelist add <name>",
    "Stops the server from kicking players for flying. Turn it on if mods or plugins let players fly.",
    "Relevance", "Most downloads", "Recently updated",
    "Plugins", "Mods", "Bukkit/Paper plugin", "Fabric mod", "Quilt mod", "Forge mod", "NeoForge mod", "Unknown",
]


def source_strings():
    found = set()
    for path in ROOT.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "t"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                found.add(node.args[0].value)
    return found


def provider_strings():
    from mc_server_maker.core.providers import PROVIDERS

    return {s for p in PROVIDERS for s in (p.short, p.description)}


class I18nTest(unittest.TestCase):
    def test_all_translated(self):
        needed = source_strings() | set(INDIRECT) | provider_strings()
        missing = sorted(s for s in needed if s not in KO)
        self.assertEqual(missing, [], "missing Korean translations")

    def test_placeholders_match(self):
        import string

        fmt = string.Formatter()
        for en, ko in KO.items():
            en_fields = {f for _, f, _, _ in fmt.parse(en) if f}
            ko_fields = {f for _, f, _, _ in fmt.parse(ko) if f}
            self.assertEqual(en_fields, ko_fields, en)

    def test_switch(self):
        try:
            i18n.set_language("ko")
            self.assertEqual(i18n.t("Start"), KO["Start"])
            self.assertIn("21", i18n.t("Using Java {v}: {path}", v=21, path="x"))
        finally:
            i18n.set_language("en")
        self.assertEqual(i18n.t("Start"), "Start")


class DurationTest(unittest.TestCase):
    def test_format_total(self):
        from mc_server_maker.gui.tabs import format_total

        i18n.set_language("en")
        self.assertEqual(format_total(13), "13s")
        self.assertEqual(format_total(450), "7m 30s")
        self.assertEqual(format_total(5 * 3600 + 12 * 60 + 9), "5h 12m")
        self.assertEqual(format_total(3 * 86400 + 4 * 3600), "3d 4h")
        i18n.set_language("ko")
        try:
            self.assertEqual(format_total(5 * 3600 + 12 * 60), "5시간 12분")
        finally:
            i18n.set_language("en")


if __name__ == "__main__":
    unittest.main()
