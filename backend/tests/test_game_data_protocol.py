import pytest

from backend.game_data_protocol import (GameDataError, GameDataRequest, GameDataPlan,
    SourceProof, SnapshotSource, PreparationStage, MAX_METADATA_BYTES, private_handle)


def test_bounded_language_request_and_unknown_download_size():
    request = GameDataRequest.parse({'region': 'global', 'source_locale': 'ja', 'target_locales': ['zh-Hans', 'en']})
    assert request.json()['target_locales'] == ['en', 'zh-Hans']
    plan = GameDataPlan('original-revision', None, None)
    assert plan.download_bytes is None and not plan.runtime_available
    for value in (-1, True, float('nan'), 2**54):
        with pytest.raises(GameDataError):
            GameDataPlan('revision', value, 100)
    assert MAX_METADATA_BYTES == 8 * 1024**2


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
