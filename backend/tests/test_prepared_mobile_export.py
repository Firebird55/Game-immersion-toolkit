"""The desktop-to-app boundary retains full dialogue semantics and exact voices."""
import copy
import json
import threading
from types import SimpleNamespace

import pytest

from backend import local_voice, mobile_library
from backend.prepared_library import PreparedLibraryStore
from backend.prepared_mobile_export import export_library
from backend.tests.test_prepared_session import fixture_library


def test_full_desktop_source_and_native_import_preserve_variants_and_context(tmp_path, monkeypatch):
    _, snapshot = fixture_library(tmp_path / 'source')
    male = snapshot['records'][0]
    male.update(player_voice='male', requires_previous=True, previous_text_id='owned:previous')
    female = copy.deepcopy(male)
    female.update(player_voice='female', audio={'source': 'owned-female-fixture'})
    silent = dict(copy.deepcopy(male), text_id='owned:written', player_voice=None,
                  audio=None, voice_status='unvoiced', requires_previous=False, previous_text_id=None)
    unknown = dict(copy.deepcopy(silent), text_id='owned:unknown', voice_status='unknown')
    snapshot.update(install=None, fingerprint='owned-source-one', targets_requested=['zh-Hans'],
                    records=[male, female, silent, unknown])
    source = tmp_path / 'source' / 'textmap.json'
    source.write_text(json.dumps(snapshot), encoding='utf8')
    female_clip = tmp_path / 'source' / 'female.wav'
    original_bytes = (tmp_path / 'source' / 'tone.wav').read_bytes()
    female_clip.write_bytes(original_bytes[:-2] + b'\x34\x12')
    calls = []
    class Voices:
        _adapter = SimpleNamespace(publisher_snapshot_available=lambda *_: True)
        tools_dir = tmp_path
        def __init__(self, *_args, **_kwargs): pass
        def extract_prepared(self, row, number):
            calls.append((row['text_id'], row['player_voice'], row['audio']))
            return 'female.wav' if row['player_voice'] == 'female' else 'tone.wav'
    monkeypatch.setattr(local_voice, 'LocalVoiceAssetService', Voices)
    full, voice, check, _ = mobile_library.prepare_source(tmp_path, 'zzz', tmp_path / 'source',
        source_path=source, translation_locale='zh-Hans', full_contract=True)
    assert full['records'] == snapshot['records']
    result = export_library(full, tmp_path / 'transfer', voice=voice, check=check)
    directory = PreparedLibraryStore(tmp_path / 'app').import_archive(result['bundle'])
    received = json.loads((directory / 'textmap.json').read_text(encoding='utf8'))
    for original, row in zip(snapshot['records'], received['records'], strict=True):
        assert {k: v for k, v in row.items() if k != 'audio'} == {k: v for k, v in original.items() if k != 'audio'}
    assert [item[1] for item in calls] == ['male', 'female']
    assert calls[0][2] != calls[1][2]
    first, second = received['records'][:2]
    assert first['audio']['prepared_clip'] != second['audio']['prepared_clip']
    assert (directory / first['audio']['prepared_clip']).read_bytes() == original_bytes
    assert (directory / second['audio']['prepared_clip']).read_bytes() == female_clip.read_bytes()
    assert result['coverage'] == {'dialogue': 4, 'exportedVoices': 2}


def test_source_change_at_publication_keeps_previous_completed_android_library(tmp_path):
    _, snapshot = fixture_library(tmp_path / 'source')
    clip = tmp_path / 'source' / 'tone.wav'
    original = export_library(snapshot, tmp_path / 'transfer', voice=lambda *_: clip, check=lambda: None)
    from pathlib import Path
    destination = Path(original['bundle'])
    previous = destination.read_bytes()
    snapshot['records'][0]['english'] = snapshot['records'][0]['source_text'] = 'A newer complete caption.'
    snapshot['records'][0]['texts']['en'] = 'A newer complete caption.'
    def check(): pass
    def stale(): raise ValueError('Account or selected snapshot changed')
    check.force = stale
    with pytest.raises(ValueError, match='changed'):
        export_library(snapshot, tmp_path / 'transfer', voice=lambda *_: clip, check=check)
    assert destination.read_bytes() == previous
    assert not destination.with_suffix('.zip.pending').exists()


def test_exact_variant_decode_never_uses_the_default_last_player_binding():
    service = local_voice.LocalVoiceAssetService.__new__(local_voice.LocalVoiceAssetService)
    service.game = 'zzz'
    service._lock = threading.RLock()
    male, female = {'source': 'owned-male'}, {'source': 'owned-female'}
    service._entries = {'shared': female}
    service._prepared_variants = {('shared', 'male'): male, ('shared', 'female'): female}
    service._install, service._fingerprint = None, 'source-one'
    service._extract_binding = lambda _identity, _number, audio, *_rest: audio['source']
    assert service.extract_prepared({'text_id': 'shared', 'player_voice': 'male', 'audio': male}, 1) == 'owned-male'
    assert service.extract_prepared({'text_id': 'shared', 'player_voice': 'female', 'audio': female}, 2) == 'owned-female'
    with pytest.raises(ValueError, match='binding changed'):
        service.extract_prepared({'text_id': 'shared', 'player_voice': 'male', 'audio': female}, 3)
