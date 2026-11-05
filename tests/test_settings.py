import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from analyser import settings


class Settings(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = Path(self.tmp.name) / "config.yaml"
        patch = mock.patch.object(settings, "CONFIG", self.cfg)
        patch.start()
        self.addCleanup(patch.stop)
        self.addCleanup(self.tmp.cleanup)
        env = mock.patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        for k in ("CRID_WORK_ROOT", "ELECTORS_DB"):
            os.environ.pop(k, None)

    def test_defaults(self):
        self.assertEqual(settings.data_root(), settings.ROOT / "data")
        self.assertEqual(settings.electors_db(), settings.ROOT / "data" / "Electors" / "electors.db")

    def test_config_file(self):
        self.cfg.write_text('data_root: ~/ppn-data\n', encoding="utf-8")
        self.assertEqual(settings.data_root(), Path("~/ppn-data").expanduser())
        self.assertEqual(settings.electors_db(), Path("~/ppn-data").expanduser() / "Electors" / "electors.db")

    def test_environment_wins(self):
        self.cfg.write_text("data_root: /from/config\nelectors_db: /from/config/e.db\n", encoding="utf-8")
        os.environ["CRID_WORK_ROOT"] = "/from/env"
        os.environ["ELECTORS_DB"] = "/from/env/e.db"
        self.assertEqual(settings.data_root(), Path("/from/env"))
        self.assertEqual(settings.electors_db(), Path("/from/env/e.db"))

    def test_relative_paths_are_inside_the_project(self):
        self.cfg.write_text("data_root: my-data\n", encoding="utf-8")
        self.assertEqual(settings.data_root(), settings.ROOT / "my-data")

    def test_broken_config_is_ignored(self):
        self.cfg.write_text(":\n  - [unbalanced", encoding="utf-8")
        self.assertEqual(settings.data_root(), settings.ROOT / "data")


if __name__ == "__main__":
    unittest.main()
