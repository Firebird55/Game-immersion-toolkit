"""Reusing voice fingerprints when only a game's install path changes."""

import sqlite3
import tempfile
import unittest
from pathlib import Path

from scripts.build_agent_fingerprints import index_matches_library


class AgentIndexReuseTests(unittest.TestCase):
    def test_reuses_same_audio_hash_after_drive_change(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            pcm = folder / "pcm"
            pcm.mkdir()
            (pcm / "voice.npy").write_bytes(b"cached")
            db = sqlite3.connect(folder / "fingerprints.db")
            try:
                db.execute("CREATE TABLE clips (asset_id TEXT PRIMARY KEY, duration REAL, fingerprint TEXT)")
                db.execute("CREATE TABLE hashes (hash INTEGER, asset_id TEXT, frame INTEGER)")
                db.execute("CREATE INDEX idx_hashes_hash ON hashes(hash)")
                db.execute("CREATE INDEX idx_hashes_asset ON hashes(asset_id)")
                db.execute("INSERT INTO clips VALUES ('voice', 1.0, 'same-audio')")
                entry = {"package": "D:/new-game/voice.pck", "package_size": 100,
                         "package_mtime_ns": 123, "offset": 1, "size": 50, "sha256": "same-audio"}
                self.assertTrue(index_matches_library(db, {"voice": entry}, pcm))
                self.assertFalse(index_matches_library(db, {"voice": {**entry, "sha256": "new-audio"}}, pcm))
                (pcm / "voice.npy").unlink()
                self.assertFalse(index_matches_library(db, {"voice": entry}, pcm))
            finally:
                db.close()


if __name__ == "__main__":
    unittest.main()
