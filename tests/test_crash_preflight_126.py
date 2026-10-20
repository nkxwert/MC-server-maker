"""1.26: plain-language crash causes and the check before a start."""

import socket
import tempfile
import unittest
from pathlib import Path

from mc_server_maker.core import crashhelp, preflight


class DiagnoseTest(unittest.TestCase):
    def kind(self, *lines):
        d = crashhelp.diagnose(list(lines))
        return d.kind if d else None

    def test_known_causes(self):
        self.assertEqual(self.kind("[12:00:01 WARN]: **** FAILED TO BIND TO PORT!",
                                   "java.net.BindException: Address already in use: bind"), "port")
        self.assertEqual(self.kind("Error: LinkageError occurred while loading main class net.minecraft.server.Main",
                                   "java.lang.UnsupportedClassVersionError: ... class file version 65.0"), "java")
        self.assertEqual(self.kind("Error occurred during initialization of VM",
                                   "Could not reserve enough space for object heap"), "memory")
        self.assertEqual(self.kind("[main/INFO]: You need to agree to the EULA in order to run the server."), "eula")
        self.assertEqual(self.kind("[Server thread/ERROR]: Failed to load level"), "world")

    def test_fabric_missing_mod(self):
        d = crashhelp.diagnose([
            "[main/ERROR]: Incompatible mods found!",
            " - Mod 'Sodium Extra' (sodium-extra) 0.6.0 requires any version of mod 'Sodium' (sodium), which is missing!",
        ])
        self.assertEqual((d.kind, d.mod), ("mod", "sodium"))

    def test_last_cause_wins_and_plugin_bind_errors_are_not_the_port(self):
        d = crashhelp.diagnose([
            "[Geyser] java.net.BindException: Address already in use",  # a plugin's own port
            "Exception in thread \"Server thread\" java.lang.OutOfMemoryError: Java heap space",
        ])
        self.assertEqual(d.kind, "memory")
        d = crashhelp.diagnose(["You need to agree to the EULA in order to run the server.",
                                "java.lang.UnsupportedClassVersionError: class file version 65.0"])
        self.assertEqual(d.kind, "java")

    def test_unknown_is_none(self):
        self.assertIsNone(crashhelp.diagnose(["[12:00:00 INFO]: Done (3.2s)!", "Stopping server"]))

    def test_shareable_log_hides_addresses(self):
        text = crashhelp.shareable_log(["/127.0.0.1:5000 lost connection", "Player from 182.214.183.205"])
        self.assertIn("127.0.x.x", text)
        self.assertIn("182.214.x.x", text)
        self.assertNotIn("183.205", text)


class PreflightTest(unittest.TestCase):
    def test_port_taken_by_running_server(self):
        free = preflight.next_free_port(40000, [])
        issues = preflight.check(free, 1024, tempfile.gettempdir(), {"Other": free}, [], available_mb=8000)
        self.assertEqual([i.kind for i in issues], ["port"])
        self.assertTrue(issues[0].error)
        self.assertNotEqual(issues[0].value, free)

    def test_port_taken_by_another_program(self):
        with socket.socket() as s:
            s.bind(("0.0.0.0", 0))
            s.listen()
            port = s.getsockname()[1]
            issues = preflight.check(port, 1024, tempfile.gettempdir(), {}, [], available_mb=8000)
        self.assertEqual(issues[0].kind, "port")

    def test_memory_warning_offers_less(self):
        port = preflight.next_free_port(41000, [])
        issues = preflight.check(port, 8192, Path(tempfile.gettempdir()), {}, [], available_mb=3000)
        self.assertEqual([(i.kind, i.error) for i in issues], [("memory", False)])
        self.assertEqual(issues[0].value, 2)

    def test_all_fine(self):
        port = preflight.next_free_port(42000, [])
        self.assertEqual(preflight.check(port, 2048, tempfile.gettempdir(), {}, [], available_mb=8000), [])


if __name__ == "__main__":
    unittest.main()
