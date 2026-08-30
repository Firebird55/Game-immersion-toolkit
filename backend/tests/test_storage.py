from __future__ import annotations

from datetime import datetime, timedelta, timezone

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


def test_transcript_channel_migrates_and_round_trips(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    match = TextMatch(
        text_id="Tips_1",
        english="Obtain an S-Rank in the previous battle.",
        chinese="在上次战斗中取得S级评价。",
        source_ocr="Obtain an S-Rank in the previous battle.",
        score=100,
        kind="exact",
    )
    created = store.add(match, "session-a", channel="tip")
    assert created.channel == "tip"
    assert store.list()[0].channel == "tip"
    updated = store.update_audio(created.id, f"{created.id}.mp3", voiced=True)
    assert updated is not None
    assert updated.voiced is True
    assert updated.has_audio is True
    assert store.audio_path(created.id) == f"{created.id}.mp3"


def test_partial_line_is_upgraded_and_recent_duplicates_are_skipped(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    started = datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc)
    partial = TextMatch(
        text_id="line_short",
        english='What is "reinforce the seal" supposed to mean?',
        chinese="「加固封印」是什么意思？",
        source_ocr='What is "reinforce the seal" supposed to mean?',
        score=89.2,
        kind="fuzzy",
    )
    complete = TextMatch(
        text_id="line_complete",
        english=(
            'What is "reinforce the seal" supposed to mean? '
            "Wasn't that part of his over-the-top delusions?"
        ),
        chinese="「加固封印」是什么意思？这竟然不是它的中二病妄想吗。",
        source_ocr=(
            'What is "reinforce the seal" supposed to mean? '
            "Wasn't that part of his over-the-top delusions?"
        ),
        score=100,
        kind="exact",
    )

    first, upgraded = store.add_or_upgrade_recent(partial, "session-a", created_at=started)
    assert first is not None and upgraded is False
    replacement, upgraded = store.add_or_upgrade_recent(
        complete, "session-a", created_at=started + timedelta(seconds=1.5)
    )
    assert replacement is not None and upgraded is True
    assert replacement.id == first.id
    assert replacement.english == complete.english
    assert store.count() == 1

    duplicate, upgraded = store.add_or_upgrade_recent(
        complete, "session-a", created_at=started + timedelta(seconds=3)
    )
    assert duplicate is None and upgraded is False
    assert store.count() == 1
