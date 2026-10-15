from __future__ import annotations

from datetime import datetime, timedelta, timezone
import pytest

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


def test_game_histories_are_partitioned(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    zzz = TextMatch(
        text_id="zzz-line", english="A shared line.", chinese="一句台词。",
        source_ocr="A shared line.", score=100, kind="exact",
    )
    pragmata = TextMatch(
        game="pragmata", text_id="pragmata-line", english="A shared line.",
        chinese="一句台词。", source_ocr="A shared line.", score=100, kind="exact",
        speaker_english="Ken", speaker_chinese="肯",
    )
    first, _ = store.add_or_upgrade_recent(zzz, "session-a")
    second, _ = store.add_or_upgrade_recent(pragmata, "session-a")
    assert first is not None and second is not None
    assert store.list(game="zzz") == [first]
    assert store.list(game="pragmata") == [second]
    assert second.speaker_english == "Ken"
    assert second.speaker_chinese == "肯"


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
    labelled = store.update_speaker(created.id, "Belle", "铃")
    assert labelled is not None
    assert labelled.speaker_english == "Belle"
    assert labelled.speaker_chinese == "铃"


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


def test_suffix_fragment_after_complete_line_is_skipped(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    started = datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc)
    complete = TextMatch(
        text_id="complete",
        english="But that's not important. We should start looking for the prototype.",
        chinese="不过现在就不说这些了，我们还是赶快开始找原型机吧。",
        source_ocr="Ben But that's not important. We should start looking for the prototype.",
        score=100,
        kind="exact",
    )
    fragment = TextMatch(
        text_id="fragment",
        english="The prototype?",
        chinese="「原型机」？",
        source_ocr="the prototype.",
        score=100,
        kind="exact",
    )
    line, _ = store.add_or_upgrade_recent(complete, "session-a", created_at=started)
    assert line is not None
    skipped, upgraded = store.add_or_upgrade_recent(
        fragment, "session-a", created_at=started + timedelta(seconds=12)
    )
    assert skipped is None and upgraded is False
    assert store.count() == 1


def test_suffix_seen_first_is_replaced_by_complete_line(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    started = datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc)
    fragment = TextMatch(
        text_id="fragment",
        english="The prototype?",
        chinese="「原型机」？",
        source_ocr="the prototype.  ?",
        score=100,
        kind="exact",
    )
    complete = TextMatch(
        text_id="complete",
        english="But that's not important. We should start looking for the prototype.",
        chinese="不过现在就不说这些了，我们还是赶快开始找原型机吧。",
        source_ocr="But that's not important. We should start looking for the prototype.",
        score=92,
        kind="fuzzy",
    )
    first, upgraded = store.add_or_upgrade_recent(fragment, "session-a", created_at=started)
    assert first is not None and upgraded is False
    replacement, upgraded = store.add_or_upgrade_recent(
        complete, "session-a", created_at=started + timedelta(seconds=2)
    )
    assert replacement is not None and upgraded is True
    assert replacement.id == first.id
    assert replacement.english == complete.english
    assert store.count() == 1


def test_adjacent_duplicate_ignores_punctuation_and_spacing(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    started = datetime(2026, 8, 30, 18, 0, tzinfo=timezone.utc)
    first = TextMatch(
        text_id="variant-a",
        english="The prototype?",
        chinese="「原型机」？",
        source_ocr="The prototype?",
        score=100,
        kind="exact",
    )
    punctuation_variant = TextMatch(
        text_id="variant-b",
        english="The prototype.  ?",
        chinese="「原型机」？",
        source_ocr="The prototype.  ?",
        score=100,
        kind="exact",
    )
    line, _ = store.add_or_upgrade_recent(first, "session-a", created_at=started)
    assert line is not None
    duplicate, upgraded = store.add_or_upgrade_recent(
        punctuation_variant, "session-a", created_at=started + timedelta(seconds=3)
    )
    assert duplicate is None and upgraded is False
    assert store.count() == 1


def test_prune_keeps_favorites_plus_fifty_recent_lines(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    favorite_id = None
    for index in range(53):
        line = store.add(
            TextMatch(
                text_id=f"line-{index}",
                english=f"Spoken sentence number {index}.",
                chinese=f"句子{index}。",
                source_ocr=f"Spoken sentence number {index}.",
                score=100,
                kind="exact",
            ),
            "session-a",
        )
        store.update_audio(line.id, f"{line.id}.mp3", voiced=True)
        if index == 0:
            favorite_id = line.id
            store.set_favorite(line.id, True)

    removed = store.prune(keep_nonfavorite=50)
    assert len(removed) == 2
    assert favorite_id is not None
    favorite = store.get(favorite_id)
    assert favorite is not None and favorite.favorite is True
    assert store.count() == 51


def test_list_favorites_returns_all_favorites_newest_first(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    match = TextMatch(
        text_id="favorite",
        english="Keep this spoken line.",
        chinese="保存这句台词。",
        source_ocr="Keep this spoken line.",
        score=100,
        kind="exact",
    )
    first = store.add(match.model_copy(update={"text_id": "favorite-a"}), "session-a")
    store.add(match.model_copy(update={"text_id": "ordinary"}), "session-a")
    last = store.add(match.model_copy(update={"text_id": "favorite-b"}), "session-b")
    store.set_favorite(first.id, True)
    store.set_favorite(last.id, True)

    favorites = store.list_favorites()

    assert [line.id for line in favorites] == [last.id, first.id]
    assert all(line.favorite for line in favorites)


def test_purge_unvoiced_keeps_confirmed_subtitles_and_favorites(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    match = TextMatch(
        text_id="line",
        english="A spoken line.",
        chinese="一句台词。",
        source_ocr="A spoken line.",
        score=100,
        kind="exact",
    )
    unvoiced = store.add(match.model_copy(update={"text_id": "unvoiced"}), "session-a")
    voiced = store.add(match.model_copy(update={"text_id": "voiced"}), "session-a")
    favorite = store.add(match.model_copy(update={"text_id": "favorite"}), "session-a")
    cinematic = store.add(
        match.model_copy(update={"text_id": "cinematic"}),
        "session-a",
        channel="cinematic",
    )
    store.update_audio(voiced.id, f"{voiced.id}.mp3", voiced=True)
    store.update_audio(cinematic.id, None, voiced=True)
    pending = store.add(match.model_copy(update={"text_id": "pending"}), "session-a")
    store.update_audio(pending.id, None, voiced=True)
    store.set_favorite(favorite.id, True)

    removed_ids = {line_id for line_id, _ in store.purge_unvoiced()}
    assert unvoiced.id in removed_ids
    assert favorite.id not in removed_ids
    assert store.get(voiced.id) is not None
    assert store.get(cinematic.id) is not None
    assert store.get(favorite.id) is not None
    assert store.get(pending.id).audio_source == "original"


def test_only_zzz_cinematic_comic_ids_are_exempt_from_voice_cleanup(tmp_path) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    match = TextMatch(text_id="Comic_" + "b" * 32, english="Please wait here.",
                      chinese="请在这里等。", source_ocr="Please wait here.", score=100, kind="exact")
    comic = store.add(match, "session", channel="cinematic")
    wrong_channel = store.add(match, "session", channel="dialogue")
    wrong_game = store.add(match.model_copy(update={"game": "pragmata"}), "session", channel="cinematic")
    video = store.add(match.model_copy(update={"text_id": "Video_" + "c" * 32}), "session", channel="cinematic")
    invalid = store.add(match.model_copy(update={"text_id": "Comic_not-an-official-id"}), "session", channel="cinematic")
    removed = {line_id for line_id, _ in store.purge_unvoiced()}
    assert removed == {wrong_channel.id, wrong_game.id, video.id, invalid.id}
    assert TranscriptStore(store.path).get(comic.id) is not None


@pytest.mark.parametrize("previous_comic,incoming_comic,previous_text,incoming_text", [
    (False, True, "Please stay here.", "Please stay here. We will return tomorrow."),
    (True, True, "Please stay here.", "Please stay here. We will return tomorrow."),
    (True, True, "Please stay here. We will return tomorrow.", "Please stay here."),
    (True, True, "Please stay here.", "Please stay here!"),
    (True, False, "Please stay here.", "Please stay here. We will return tomorrow."),
    (False, True, "Please stay here. We will return tomorrow.", "Please stay here."),
])
def test_comic_identity_preserves_independent_bubbles_and_prior_audio(
    tmp_path, previous_comic, incoming_comic, previous_text, incoming_text,
) -> None:
    store = TranscriptStore(tmp_path / "transcript.db")
    started = datetime.now(timezone.utc)
    first = TextMatch(text_id="Comic_" + "a" * 32 if previous_comic else "GalGame_previous",
                      english=previous_text, chinese="请在这里等。", source_ocr=previous_text, score=100, kind="exact")
    previous = store.add(first, "session", created_at=started,
                         channel="cinematic" if previous_comic else "dialogue")
    store.update_audio(previous.id, "original-previous.mp3", True)
    store.set_favorite(previous.id, True)
    second = first.model_copy(update={
        "text_id": "Comic_" + "b" * 32 if incoming_comic else "GalGame_next",
        "english": incoming_text, "source_ocr": incoming_text, "chinese": "我们明天会回来。"})
    channel = "cinematic" if incoming_comic else "dialogue"
    incoming, upgraded = store.add_or_upgrade_recent(
        second, "session", created_at=started + timedelta(seconds=1), channel=channel)
    assert incoming is not None and incoming.id != previous.id and not upgraded
    unchanged = store.get(previous.id)
    assert unchanged.english == previous_text and unchanged.chinese == first.chinese
    assert unchanged.voiced and unchanged.favorite and unchanged.has_audio
    assert store.audio_path(previous.id) == "original-previous.mp3"
    assert store.add_or_upgrade_recent(
        second, "session", created_at=started + timedelta(seconds=2), channel=channel) == (None, False)
    assert store.count() == 2
