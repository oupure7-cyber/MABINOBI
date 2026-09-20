"""Run: python -m unittest discover -s tests (no game CLI calls)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import cli_settings


class CliSettingsTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_missing_file_returns_none(self):
        self.assertIsNone(cli_settings.load_cli_path(self.root))

    def test_save_then_load_round_trips(self):
        cli_settings.save_cli_path(self.root, r"D:\Games\Mabinogi\MabinogiMobile_CLI.exe")
        self.assertEqual(cli_settings.load_cli_path(self.root), r"D:\Games\Mabinogi\MabinogiMobile_CLI.exe")

    def test_save_overwrites_a_previous_value(self):
        cli_settings.save_cli_path(self.root, r"D:\Old\MabinogiMobile_CLI.exe")
        cli_settings.save_cli_path(self.root, r"E:\New\MabinogiMobile_CLI.exe")
        self.assertEqual(cli_settings.load_cli_path(self.root), r"E:\New\MabinogiMobile_CLI.exe")

    def test_corrupt_file_is_treated_as_missing(self):
        (self.root / cli_settings.SETTINGS_FILE_NAME).write_text("not json", encoding="utf-8")
        self.assertIsNone(cli_settings.load_cli_path(self.root))


if __name__ == "__main__":
    unittest.main()
