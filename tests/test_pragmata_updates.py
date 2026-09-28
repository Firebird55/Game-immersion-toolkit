"""Portable PRAGMATA update checks when game drives change."""

import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from backend.pragmata_updates import PragmataUpdateManager


class FakeIndex:
    def __init__(self, path: Path):
        self.path = path
        self.entry_count = 1
        self.message = "cached subtitles ready"
        self.loads = 0

    def load(self):
        self.loads += 1
        return True


class FakeVoices:
    def __init__(self):
        self.reloads = 0

    def reload(self):
        self.reloads += 1


class PragmataUpdateTests(unittest.TestCase):
    def test_missing_game_retains_cached_subtitles(self):
        with tempfile.TemporaryDirectory() as temp:
            index = FakeIndex(Path(temp) / "textmap.json")
            voices = FakeVoices()
            manager = PragmataUpdateManager(Path(temp), index, voices)
            with patch("scripts.index_pragmata_assets.find_install", return_value=None):
                manager._run()
            self.assertEqual(manager.status()["state"], "waiting")
            self.assertIsNone(manager.status()["last_error"])
            self.assertEqual(index.loads, 1)
            self.assertEqual(voices.reloads, 1)

    def test_moved_game_rebuilds_using_current_drive(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "textmap.json"
            path.write_text(json.dumps({"format": 3, "install": "F:/old/PRAGMATA", "fingerprint": "same"}))
            index = FakeIndex(path)
            voices = FakeVoices()
            manager = PragmataUpdateManager(Path(temp), index, voices)
            moved = Path("E:/SteamLibrary/steamapps/common/PRAGMATA")
            with patch("scripts.index_pragmata_assets.find_install", return_value=moved), \
                 patch("scripts.index_pragmata_assets.fingerprint", return_value="same"), \
                 patch("backend.pragmata_updates.subprocess.run", return_value=SimpleNamespace(returncode=0)) as run:
                manager._run()
            self.assertEqual(run.call_args.args[0][-2:], ["--install", str(moved)])
            self.assertEqual(manager.status()["state"], "idle")


if __name__ == "__main__":
    unittest.main()
