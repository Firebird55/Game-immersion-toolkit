"""Canonical source/restore model; publisher authenticity is proved separately."""
import copy
import json
import sys
import threading
from types import SimpleNamespace

import pytest

from backend import nte_assets as assets, nte_game_data_snapshot as snapshot
from backend.game_data_protocol import GameDataRequest, GameDataError
from backend.game_tools import _atomic_file
from backend.language_worker import write_payload
from backend.multilingual_index import MultilingualTextIndex
from backend.tests.test_nte_text_mode import staging

LOCALES = [('en', 'Watch the western entrance.'), ('zh-Hans', '请守住西侧入口。'),
    ('zh-Hant', '請守住西側入口。'), ('ja', '西側の入口を守って。'), ('ko', '서쪽 입구를 지켜.')]


def fixture(path, locale='en', text='Watch the western entrance.'):
    path.mkdir(); staging(path)
    code = assets.TEXT_LOCALES[locale]
    values = json.loads((path/'localization.json').read_bytes())['en']
    values[0]['value'] = text
    (path/'localization.json').write_text(json.dumps({code: values}), encoding='utf-8')
    (path/'voice-bank-paths.json').write_text(json.dumps([
        'HT/Content/WwiseAudio/Event/'+assets.VOICE_LOCALES[locale]+'/Play_Vo_One.bnk']))
    rows = assets.build_records(path, source_locale=locale, content_mode='text')
    payload = {'format': 2, 'game': 'nte', 'install': None, 'source_mode': 'publisher', 'source_region': 'global',
        'source_locale': locale, 'content_mode': 'text', 'fingerprint': 'owned-source-model', 'records': rows,
        'missing_translation_locales': [], 'coverage_warnings': []}
    write_payload('nte', payload, locale, [], path/'validated.json')
    ctx = SimpleNamespace(directory=path, check=lambda: None, transfer_lock=threading.RLock(),
        request=GameDataRequest('global', locale, (), 'text'))
    # Authored identities model the boundary; no real publisher claim is made.
    inputs = {key: 'a'*64 for key in snapshot.INPUTS-{'reader', 'initial_descriptions'}}
    inputs.update(reader={'kind': 'nte-owned-test-reader-v1', 'source_sha256': 'b'*64, 'dependencies_sha256': 'c'*64},
        initial_descriptions=dict.fromkeys(('archive', 'localization', 'seed'), 'd'*64))
    return payload, inputs, ctx


@pytest.mark.parametrize('locale,text', LOCALES)
def test_all_study_text_snapshots_restore_without_native_or_current_source_lookups(tmp_path, monkeypatch, locale, text):
    payload, inputs, ctx = fixture(tmp_path/'source', locale, text)
    result = snapshot.publish(payload, inputs, ctx, _atomic_file)
    assert result.voice_source is None
    from backend.nte_game_data import NteGameDataProvider
    provider = NteGameDataProvider(platform='android')
    monkeypatch.setattr(provider, '_reader', lambda *_: pytest.fail('Offline text restore requested a native reader'))
    for name in ('nte_game_data_runtime', 'nte_game_data_text', 'nte_native_metadata', 'nte_publisher', 'nte_archive_metadata'):
        monkeypatch.setitem(sys.modules, 'backend.'+name, None)
    restored = provider.restore(result.restore_handle, ctx)
    assert restored.source_proof == result.source_proof and restored.restore_handle == result.restore_handle
    index = MultilingualTextIndex('nte', ctx.directory)
    assert index.ready and index.state == 'text_only' and index.audio_count == 0
    match = index.match_lines([text], exact_only=True)
    assert match and match.voice_status == 'voiced' and match.audio_omitted_by_request and match.source_voice_binding
    caption = index.match_lines(['An authored cinematic caption.'], exact_only=True)
    assert caption and caption.voice_status == 'unknown' and caption.audio_omitted_by_request


@pytest.mark.parametrize('fault', ['profile', 'receipt', 'snapshot', 'missing-receipt',
    'profile-swap', 'receipt-swap', 'recipe', 'request', 'audio-mode'])
def test_corrupt_or_swapped_source_receipts_never_restore_as_a_provisional_library(tmp_path, fault):
    payload, inputs, ctx = fixture(tmp_path/'source')
    result = snapshot.publish(payload, inputs, ctx, _atomic_file)
    handle = copy.deepcopy(result.restore_handle)
    if fault in {'profile', 'receipt', 'snapshot'}:
        names = {'profile': 'nte-source-profile.json', 'receipt': 'nte-source-receipt.json', 'snapshot': 'textmap.json'}
        with (ctx.directory/names[fault]).open('ab') as stream: stream.write(b'!')
    elif fault == 'missing-receipt': (ctx.directory/'nte-source-receipt.json').unlink()
    elif fault in {'profile-swap', 'receipt-swap'}:
        other_payload, other_inputs, other = fixture(tmp_path/'other')
        other_inputs['native_validation_sha256'] = 'e'*64
        snapshot.publish(other_payload, other_inputs, other, _atomic_file)
        name = 'nte-source-'+fault.removesuffix('-swap')+'.json'
        (ctx.directory/name).write_bytes((other.directory/name).read_bytes())
    elif fault == 'recipe': handle['recipe'] = '0'*64
    elif fault == 'request': ctx.request = GameDataRequest('global', 'ja', (), 'text')
    else: ctx.request = GameDataRequest('global', 'en', (), 'text-audio')
    with pytest.raises(GameDataError) as rejected: snapshot.restore(handle, ctx)
    assert rejected.value.code == 'nte_text_source_invalid'


def test_interrupted_new_profile_publication_keeps_the_old_complete_source(tmp_path):
    payload, inputs, old = fixture(tmp_path/'old')
    complete = snapshot.publish(payload, inputs, old, _atomic_file)
    saved = {path.name: path.read_bytes() for path in old.directory.glob('nte-source-*.json')}
    saved['textmap.json'] = (old.directory/'textmap.json').read_bytes()
    new_payload, new_inputs, new = fixture(tmp_path/'new')
    new_inputs['recipe_sha256'] = 'e'*64
    def interrupted(path, data):
        if path.name == 'nte-source-receipt.json': raise OSError('Authored interruption before source receipt')
        _atomic_file(path, data)
    with pytest.raises(OSError): snapshot.publish(new_payload, new_inputs, new, interrupted)
    assert not (new.directory/'nte-source-receipt.json').exists()
    assert all((old.directory/name).read_bytes() == raw for name, raw in saved.items())
    assert snapshot.restore(complete.restore_handle, old).source_proof == complete.source_proof
