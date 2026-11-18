import pytest

from backend.game_data_protocol import (GameDataError, GameDataRequest, GameDataPlan,
    SourceProof, SnapshotSource, PreparationStage, MAX_METADATA_BYTES, private_handle, VoiceChoiceSelection, VoiceChoiceSet)


def test_bounded_language_request_and_unknown_download_size():
    request = GameDataRequest.parse({'region': 'global', 'source_locale': 'ja', 'target_locales': ['zh-Hans', 'en'], 'content_mode': 'text'})
    assert request.json()['target_locales'] == ['en', 'zh-Hans']
    plan = GameDataPlan('original-revision', None, None)
    assert plan.download_bytes is None and not plan.runtime_available
    for value in (-1, True, float('nan'), 2**54):
        with pytest.raises(GameDataError):
            GameDataPlan('revision', value, 100)
    assert MAX_METADATA_BYTES == 8 * 1024**2
    with pytest.raises(GameDataError):
        GameDataRequest.parse({'region': 'global', 'source_locale': 'en', 'target_locales': []})


def test_original_content_and_exceptional_key_fallback_need_separate_receipts():
    with pytest.raises(GameDataError):
        SourceProof('official', 'a' * 64, False)
    with pytest.raises(GameDataError):
        SourceProof('maintained-community-fallback', 'a' * 64, True)
    fallback = SourceProof('maintained-community-fallback', 'a' * 64, True, 'b' * 64)
    assert fallback.publisher_content_verified
    assert SnapshotSource('textmap.json', {}, fallback).source_proof == fallback
    assert not isinstance(PreparationStage({}, 'Check the remaining download size.'), SnapshotSource)


def test_private_handle_is_bounded_inert_json_and_copied():
    original = {'revision': ['original']}
    copied = private_handle(original); original['revision'].append('changed')
    assert copied == {'revision': ['original']}
    for value in ({'native': object()}, {'value': float('nan')}, {'value': 'x' * (1024**2)}):
        with pytest.raises(GameDataError):
            private_handle(value)


def test_explicit_voice_selection_is_immutable_canonical_and_empty_preserves_legacy_json():
    from dataclasses import FrozenInstanceError
    old = {'region': 'global', 'source_locale': 'en', 'target_locales': [], 'content_mode': 'text-audio'}
    assert GameDataRequest.parse(old).json() == old
    assert GameDataRequest.parse(old | {'voice_choices': None}).json() == old
    assert GameDataRequest.parse(old | {'voice_choices': {'choice_set_sha256': 'a'*64, 'choices': []}}).json() == old
    supplied = {'choice_set_sha256': 'a'*64, 'choices': [
        {'group_key': 'starrail:copyright-avatar:9001', 'alternative': 'copyright-dub'},
        {'group_key': 'starrail:copyright-avatar:7001', 'alternative': 'selected-dub'}]}
    request = GameDataRequest.parse(old | {'voice_choices': supplied})
    supplied['choices'][0]['alternative'] = 'selected-dub'
    assert request.voice_choices.choices == (('starrail:copyright-avatar:7001', 'selected-dub'),
                                            ('starrail:copyright-avatar:9001', 'copyright-dub'))
    assert GameDataRequest.parse(request.json()) == request
    with pytest.raises(FrozenInstanceError):
        request.voice_choices.choice_set_sha256 = 'b'*64
    encoded = request.json(); encoded['voice_choices']['choices'].clear()
    assert len(request.voice_choices.choices) == 2


@pytest.mark.parametrize('change', [
    {'choice_set_sha256': 'invalid', 'choices': []}, {}, [],
    {'choice_set_sha256': 'a'*64, 'choices': [{'group_key': 'starrail:copyright-avatar:0', 'alternative': 'selected-dub'}]},
    {'choice_set_sha256': 'a'*64, 'choices': [{'group_key': 'starrail:copyright-avatar:1', 'alternative': []}]},
    {'choice_set_sha256': 'a'*64, 'choices': [{'group_key': 'starrail:copyright-avatar:1', 'alternative': 'default'}]},
    {'choice_set_sha256': 'a'*64, 'choices': [{'group_key': 'starrail:copyright-avatar:1', 'alternative': 'selected-dub', 'extra': True}]},
    {'choice_set_sha256': 'a'*64, 'choices': [{'group_key': 'starrail:copyright-avatar:1', 'alternative': value}
                                          for value in ('selected-dub', 'copyright-dub')]}])
def test_voice_selection_rejects_malformed_unknown_default_and_conflicting_choices(change):
    with pytest.raises(GameDataError):
        GameDataRequest.parse({'region': 'global', 'source_locale': 'en', 'target_locales': [],
                               'content_mode': 'text-audio', 'voice_choices': change})


def test_available_choices_are_typed_metadata_with_unknown_default_and_unproven_locale():
    available = VoiceChoiceSet('a'*64, 'b'*64, 'c'*64, 'd'*64,
        (('starrail:copyright-avatar:7001', 7001, 'en', 'ja'),))
    group, = available.json()['groups']
    assert group['default_status'] == 'unknown' and group['default_alternative'] is None
    assert group['alternatives'][1]['declared_spoken_locale'] == 'ja'
    assert all(item['requires_authored_locale_receipt'] for item in group['alternatives'])
    assert GameDataPlan('r', None, None, available_voice_choices=available).available_voice_choices == available
    with pytest.raises(GameDataError):
        GameDataPlan('r', 0, 0, available_voice_choices=available.json())
