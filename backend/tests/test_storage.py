from __future__ import annotations

from backend.models import TextMatch
from backend.storage import TranscriptStore


def test_transcript_round_trip(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    match = TextMatch(
        text_id="dialogue_1",
        english="Stay close to me.",
        chinese="跟紧我。",
        source_ocr="Stay close to me",
        score=100,
        kind="exact",
    )
    created = store.add(match, "session-a")

    lines = store.list()
    assert lines == [created]
    assert store.count() == 1
    assert store.count("session-a") == 1
    assert store.count("session-b") == 0
