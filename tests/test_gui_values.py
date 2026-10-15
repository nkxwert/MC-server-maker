"""Out-of-range numbers in server.properties must never crash the app."""

import os
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QSpinBox  # noqa: E402

from mc_server_maker.core.properties import Properties  # noqa: E402
from mc_server_maker.gui.tabs import set_spin  # noqa: E402

app = QApplication.instance() or QApplication([])


class SetSpinTest(unittest.TestCase):
    def setUp(self):
        self.spin = QSpinBox()
        self.spin.setRange(1, 1000)

    def test_huge_value_is_clamped(self):
        set_spin(self.spin, 99999999999)  # used to raise OverflowError
        self.assertEqual(self.spin.value(), 1000)

    def test_negative_and_garbage(self):
        set_spin(self.spin, -5)
        self.assertEqual(self.spin.value(), 1)
        set_spin(self.spin, "abc")
        self.assertEqual(self.spin.value(), 1)

    def test_normal(self):
        set_spin(self.spin, 20)
        self.assertEqual(self.spin.value(), 20)


class GetIntTest(unittest.TestCase):
    def test_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "server.properties"
            path.write_text("max-players=99999999999\nview-distance= 8 \nsimulation-distance=abc\n")
            p = Properties(path)
            self.assertEqual(p.get_int("max-players", 20), 99999999999)
            self.assertEqual(p.get_int("view-distance", 10), 8)
            self.assertEqual(p.get_int("simulation-distance", 10), 10)
            self.assertEqual(p.get_int("missing", 3), 3)


if __name__ == "__main__":
    unittest.main()
