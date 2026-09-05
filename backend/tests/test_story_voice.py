import sqlite3

import numpy as np

import backend.story_voice as story_voice
from backend.story_voice import StoryVoiceResolver, _verification_score


def test_waveform_verification_finds_clean_voice_inside_mixed_recording():
    rng = np.random.default_rng(4)
    reference = rng.normal(0, 0.15, 16_000).astype(np.float32)
    observed = rng.normal(0, 0.015, 24_000).astype(np.float32)
    observed[3_000:19_000] += reference
    assert _verification_score(reference, observed) > 0.9


def test_resolver_accepts_only_large_landmark_margin(tmp_path, monkeypatch):
    database_path = tmp_path / "story-fingerprints.db"
    with sqlite3.connect(database_path) as database:
        database.execute(
            "CREATE TABLE clips (asset_id TEXT PRIMARY KEY, file_id TEXT, package TEXT, "
            "offset INTEGER, size INTEGER, duration REAL, stamp TEXT)"
        )
        database.execute("CREATE TABLE hashes (hash INTEGER, asset_id TEXT, frame INTEGER)")
        database.execute("CREATE INDEX idx_story_hash ON hashes(hash)")
        database.execute(
            "INSERT INTO clips VALUES ('best', '000000000000007b', 'voice.pck', 64, 12, 2, 'x')"
        )
        database.execute(
            "INSERT INTO clips VALUES ('other', '000000000000007c', 'voice.pck', 80, 12, 2, 'x')"
        )
        database.executemany(
            "INSERT INTO hashes VALUES (?, 'best', ?)", [(1000 + n, n) for n in range(50)]
        )
        database.executemany(
            "INSERT INTO hashes VALUES (?, 'other', ?)", [(1000 + n, n) for n in range(5)]
        )

    samples = np.sin(np.linspace(0, 400, 16_000)).astype(np.float32)
    monkeypatch.setattr(story_voice, "_recording_samples", lambda _path: samples)
    noise = np.random.default_rng(8).normal(0, 0.2, len(samples)).astype(np.float32)
    monkeypatch.setattr(
        story_voice,
        "_decode_entry",
        lambda entry, _decoder: samples if entry.file_id == 123 else noise,
    )
    monkeypatch.setattr(
        story_voice,
        "landmarks",
        lambda _samples: [(1000 + n, n + 8) for n in range(50)],
    )
    resolver = StoryVoiceResolver(tmp_path, tmp_path / "decoder", tmp_path, object())
    try:
        entry, diagnostics = resolver.match(tmp_path / "recording.mp3")
        assert entry is not None
        assert entry.file_id == 123
        assert diagnostics["accepted"]["landmark_votes"] >= 50
    finally:
        resolver.close()
