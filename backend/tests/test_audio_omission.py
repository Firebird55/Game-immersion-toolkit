from dataclasses import asdict
import json

import pytest

from backend.capture_confirmation import capture_match_eligible
from backend.local_game import LocalDialogue
from backend.multilingual_index import MultilingualTextIndex

TEXT = 'Follow the river beyond the bridge.'


def record(identity='authored:bridge', *, status='voiced', **patch):
    values = dict(audio=None, source_locale='en', source_text=TEXT, audio_locale='en',
        texts={'en': TEXT, 'zh-Hans': '沿着河流走过桥。'}, ocr_texts={}, voice_status=status,
        text_capture_verified=True, audio_omitted_by_request=True,
        source_voice_binding={'publisher': 'authored', 'file_id': identity} if status == 'voiced' else None)
    values.update(patch)
    return asdict(LocalDialogue(identity, TEXT, '沿着河流走过桥。', **values))


def snapshot(records, mode='text'):
    return {'format': 2, 'game': 'zzz', 'content_mode': mode, 'fingerprint': 'authored-original-generation',
        'source_locale': 'en', 'records': records}


def index(tmp_path, records, mode='text'):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / 'textmap.json').write_text(json.dumps(snapshot(records, mode)), encoding='utf8')
    return MultilingualTextIndex('zzz', tmp_path)


@pytest.mark.parametrize('status', ['voiced', 'unknown'])
def test_omission_preserves_actual_status_and_captures_only_exact_verified_text(tmp_path, status):
    reader = index(tmp_path, [record(status=status)])
    assert reader.ready and reader.capture_text_only and reader.audio_count == 0
    hit = reader.match_lines([TEXT])
    assert hit and hit.voice_status == status and hit.is_requested_text_only
    assert not hit.is_verified_missing_audio
    def forbidden(_): raise AssertionError('Text capture attempted a playable voice lookup')
    assert capture_match_eligible(hit, capture_unvoiced=False, capture_missing_audio=False, mapped_voice=forbidden)
    assert not capture_match_eligible(hit.model_copy(update={'kind': 'fuzzy'}), capture_unvoiced=False,
        capture_missing_audio=False, mapped_voice=forbidden)
    assert reader.match_lines(['Follow the river beyond the bridg.']) is None
    assert reader.match_lines(['Extra preceding sentence. ' + TEXT]) is None


def test_nonplayable_binding_cannot_be_a_backdoor_to_voiced_or_audio_mode(tmp_path):
    with pytest.raises(ValueError): record(source_voice_binding=None)
    with pytest.raises(ValueError): record(audio={'publisher': 'authored', 'file_id': 'unexpected'})
    reader = index(tmp_path, [record()], mode='text-audio')
    assert not reader.ready
    playable = record(); playable.update(audio=playable['source_voice_binding'], audio_omitted_by_request=False, source_voice_binding=None)
    assert not index(tmp_path / 'unexpected-audio', [playable], mode='text').ready


def test_unresolved_duplicate_and_distinct_omitted_occurrences_remain_vetoes(tmp_path):
    first = record()
    assert index(tmp_path / 'first', [first]).match_lines([TEXT])
    unverified = record('authored:unverified', status='unknown', text_capture_verified=False)
    assert index(tmp_path / 'unverified', [first, unverified]).match_lines([TEXT]) is None
    duplicate = record('authored:second')
    assert index(tmp_path / 'duplicate', [first, duplicate]).match_lines([TEXT]) is None


def test_unvoiced_and_genuinely_missing_optins_remain_separate(tmp_path):
    missing = record(status='unavailable', audio_omitted_by_request=False)
    reader = index(tmp_path / 'missing', [missing])
    assert reader.match_lines([TEXT]) is None
    reader.capture_missing_audio = True
    assert reader.match_lines([TEXT]).is_verified_missing_audio
    silent = record(status='unvoiced', audio_omitted_by_request=False)
    reader = index(tmp_path / 'silent', [silent])
    assert reader.match_lines([TEXT]) is None
    reader.capture_unvoiced = True
    assert reader.match_lines([TEXT]).voice_status == 'unvoiced'


def test_previous_caption_guard_does_not_disappear_when_audio_is_omitted(tmp_path):
    entry = record(previous_text_id='authored:previous', requires_previous=True)
    reader = index(tmp_path, [entry])
    assert reader.match_lines([TEXT]) is None
    assert reader.match_lines([TEXT], previous_text_id='authored:wrong', exact_only=True) is None
    assert reader.match_lines([TEXT], previous_text_id='authored:previous', exact_only=True).text_id == entry['text_id']
