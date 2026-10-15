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
    "Console", "Settings", "World", "Players", "Network", "Update",
    "Operators (OP)", "Whitelist",
    "Online mode (off = allow non-premium accounts)", "PvP", "Hardcore", "Whitelist only",
    "Allow flight (recommended with mods/plugins)", "Command blocks",
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


if __name__ == "__main__":
    unittest.main()
