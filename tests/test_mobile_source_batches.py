"""Exercise adapter routing through the real mobile-export preparation path."""
import json
from types import SimpleNamespace

import pytest

from backend.mobile_library import prepare_source, export_library, file_digest


@pytest.mark.parametrize('game', ['zzz', 'pragmata', 'cyberpunk', 'witcher3', 'wuwa', 'nte', 'starrail', 'genshin', 'endfield'])
def test_prepared_sources_enable_verified_batching_for_every_voiced_game(tmp_path, monkeypatch, game):
    from backend import voice_assets, pragmata_audio, local_voice, game_paths, nte_assets
    from scripts import index_pragmata_assets
    install = tmp_path / 'game'; (install/'resources').mkdir(parents=True)
    archive = install/'resources/app.asar'; archive.write_bytes(b'synthetic licensed fixture')
    data = tmp_path / 'data'; data.mkdir()
    text_id = 'GalGame_fixture' if game == 'zzz' else f'{game}:fixture'
    payload = {'install': str(install), 'fingerprint': 'fixture', 'archive_hash': file_digest(archive),
               'records': [{'text_id': text_id, 'english': 'A synthetic performance.', 'chinese': '合成对白。', 'audio': None if game == 'hito' else {'depot': 'fixture'}}]}
    if game == 'zzz':
        maps = data/'textmaps'; maps.mkdir()
        for name, value in [('en_base', {text_id: 'A synthetic performance.', 'GalGame_text_only': 'A quiet unvoiced sentence.'}), ('zh_base', {text_id: '合成对白。', 'GalGame_text_only': '无声的句子。'}),
                            ('en_overwrite', {}), ('zh_overwrite', {})]:
            (maps/f'{name}.json').write_text(json.dumps(value), encoding='utf8')
        package = tmp_path/'fixture.pck'; package.write_bytes(b'RIFF' + bytes(100))
        stat = package.stat()
        payload = {'version': 1, 'entries': {text_id: {'package': str(package), 'package_size': stat.st_size,
                   'package_mtime_ns': stat.st_mtime_ns, 'source': '', 'file_id': 'fixture'}}}
        folder = data/'voice-assets'; folder.mkdir()
        (folder/'manifest.json').write_text(json.dumps(payload))
    else:
        folder = data/game; folder.mkdir()
        payload['records'].append({'text_id': game + ':text-only', 'english': 'A quiet unvoiced sentence.',
                                   'chinese': '无声的句子。', 'audio': None})
        (folder/'textmap.json').write_text(json.dumps(payload), encoding='utf8')
    class Service:
        def __init__(self, output):
            self.output = output; self.scalars = []; self.batches = []
            self._adapter = SimpleNamespace(fingerprint=lambda _: 'fixture')
            self._entries = payload['entries'] if game == 'zzz' else {text_id: {'depot': 'fixture'}}
            self.manifest = folder/'manifest.json'
        def _entry_key(self, text, english):
            return text if text in self._entries else None
        def has_variant(self, text, english):
            return text in self._entries
        def extract(self, text, number, english):
            self.scalars.append(text); return self.clip(number)
        def extract_batch(self, requests):
            self.batches.append(requests); return [self.clip(number) for text, number, english in requests]
        def clip(self, number):
            self.output.mkdir(parents=True, exist_ok=True)
            name = f'{number}.mp3'; (self.output/name).write_bytes(b'ID3' + bytes(200)); return name
        def close(self):
            pass
    monkeypatch.setattr(voice_assets, 'VoiceAssetService', lambda manifest, decoder, output, learned: Service(output))
    monkeypatch.setattr(pragmata_audio, 'PragmataVoiceAssetService', lambda data, decoder, output: Service(output))
    monkeypatch.setattr(local_voice, 'LocalVoiceAssetService', lambda game, data, decoder, output, **kwargs: Service(output))
    monkeypatch.setattr(index_pragmata_assets, 'fingerprint', lambda _: 'fixture')
    monkeypatch.setattr(nte_assets, 'ensure_extractor', lambda _: None)
    monkeypatch.setattr(game_paths, 'discover_install', lambda _: install)
    output = tmp_path/'export'
    records, voice, check, service = prepare_source(tmp_path, game, output/'decoded')
    events = []
    result = export_library(game, records, output, voice=voice, check=check, workers=2, progress=events.append)
    assert result['coverage']['dialogue'] == (2 if game in {'zzz', 'hito'} else 1)
    assert sum(not r.get('sourceVoice') for r in records) == (2 if game == 'hito' else 1 if game == 'zzz' else 0)
    if game == 'hito':
        assert service is None and not hasattr(voice, 'batch') and result['coverage']['exportedVoices'] == 0
    else:
        assert callable(voice.batch) and len(service.batches) == 1 and not service.scalars
        assert any(event.get('batchSize') == 8 for event in events)
        assert result['coverage']['exportedVoices'] == 1


@pytest.mark.parametrize('game', ['zzz', 'pragmata', 'cyberpunk', 'witcher3', 'wuwa', 'nte', 'beyond', 'heavyrain'])
def test_selected_multilingual_exports_use_the_selected_decoder_and_official_target(tmp_path, monkeypatch, game):
    from backend import language_preparation, lexirise, lexirise_settings, local_voice, pragmata_audio, nte_assets
    from scripts import index_pragmata_assets
    directory = tmp_path / 'data/languages' / game / 'ja'; directory.mkdir(parents=True)
    identity = 'GalGame_fixture:F' if game == 'zzz' else game + ':fixture'
    row = {'text_id': identity, 'english': '', 'chinese': '合成字幕。', 'source_text': '合成の字幕です。',
           'source_locale': 'ja', 'audio_locale': 'ja', 'texts': {'ja': '合成の字幕です。', 'zh-Hans': '合成字幕。'},
           'audio': {'locale': 'ja', 'fixture': 1}, 'channels': ['cinematic'], 'player_voice': 'female'}
    if game == 'zzz': row['member_text_ids'] = ['GalGame_fixture']
    path = directory / 'textmap.json'
    path.write_text(json.dumps({'format': 2, 'game': game, 'source_locale': 'ja', 'targets_requested': ['zh-hans'],
        'install': str(tmp_path / 'game'), 'fingerprint': 'fixture', 'records': [row]}), encoding='utf-8')
    state = {'active': 'one'}; protected = tmp_path / 'protected-fixture'; protected.write_bytes(b'one-profile-first-generation')
    accounts = SimpleNamespace(status=lambda: state, path=protected)
    monkeypatch.setattr(language_preparation, 'selected_snapshot', lambda *args: (path, accounts, 'one'))
    monkeypatch.setattr(language_preparation, 'LanguagePreparation', lambda *_: SimpleNamespace(selection_generation=lambda *_: 0))
    monkeypatch.setattr(lexirise, 'LexiriseService', lambda *args, **kwargs: SimpleNamespace(pin=lambda language: language))
    monkeypatch.setattr(lexirise_settings, 'account_settings', lambda client: {'global': {'effectiveTranslationLanguage': 'fr'},
        'languageSettings': {'ja': {'effectiveTranslationLanguage': 'zh-hans'}}})
    calls = []
    class Service:
        _adapter = SimpleNamespace(fingerprint=lambda _: 'fixture')
        def __init__(self, data, decoder, output, **kwargs):
            calls.append((data, kwargs)); self.output = output; self._entries = {identity: row['audio']}
        def has_variant(self, *_): return True
        def extract_batch(self, requests):
            self.output.mkdir(parents=True, exist_ok=True)
            for _, number, _ in requests: (self.output / f'{number}.mp3').write_bytes(b'ID3' + bytes(200))
            return [f'{number}.mp3' for _, number, _ in requests]
        def close(self): pass
    monkeypatch.setattr(local_voice, 'LocalVoiceAssetService', lambda game, *args, **kwargs: Service(*args, **kwargs))
    monkeypatch.setattr(pragmata_audio, 'PragmataVoiceAssetService', Service)
    monkeypatch.setattr(index_pragmata_assets, 'fingerprint', lambda _: 'fixture')
    monkeypatch.setattr(nte_assets, 'ensure_extractor', lambda _: None)
    records, voice, check, service = prepare_source(tmp_path, game, tmp_path / 'decoded')
    assert calls[0] == (directory, {'tools_dir': tmp_path / 'data' / game / 'tools'})
    assert records[0]['sourceLocale'] == records[0]['audioLocale'] == 'ja'
    assert records[0]['translationLocale'] == 'zh-Hans' and records[0]['translationText'] == row['texts']['zh-Hans']
    assert records[0]['channels'] == ['cinematic'] and records[0]['playerVoice'] == 'female'
    assert 'memberTextIds' not in records[0], 'A historical ZZZ alias is not a two-caption context'
    check.force()
    result = export_library(game, records, tmp_path / 'export', voice=voice, check=check)
    assert result['coverage']['exportedVoices'] == 1
    state['active'] = 'two'
    with pytest.raises(ValueError, match='changed'): check.force()
    state['active'] = 'one'; protected.write_bytes(b'one-profile-after-switching-back')
    with pytest.raises(ValueError, match='changed'): check.force()


def test_explicit_export_snapshot_never_reads_account_or_active_locale(tmp_path, monkeypatch):
    from backend import local_voice, lexirise, language_preparation
    def forbidden(*args, **kwargs):
        raise AssertionError('Automatic export consulted mutable account state')
    monkeypatch.setattr(lexirise, 'LexiriseService', forbidden)
    monkeypatch.setattr(language_preparation, 'selected_snapshot', forbidden)
    source = tmp_path / 'private-source/textmap.json'
    source.parent.mkdir()
    source.write_text(json.dumps({'format': 2, 'source_locale': 'ja', 'targets_requested': ['fr'],
        'install': str(tmp_path), 'fingerprint': 'stable', 'records': [{'text_id': 'example', 'english': '',
        'chinese': '', 'source_text': 'synthetic Japanese', 'audio_locale': 'ja', 'audio': {'locale': 'ja'},
        'texts': {'ja': 'synthetic Japanese', 'fr': 'synthetic French'}}]}), encoding='utf-8')
    service = SimpleNamespace(_adapter=SimpleNamespace(fingerprint=lambda _: 'stable'))
    monkeypatch.setattr(local_voice, 'LocalVoiceAssetService', lambda *args, **kwargs: service)
    rows, voice, check, _ = prepare_source(tmp_path, 'zzz', tmp_path/'decoded', source_path=source,
                                         expected_source_locale='ja', translation_locale='fr')
    check.force()
    assert rows[0]['sourceLocale'] == rows[0]['audioLocale'] == 'ja'
    assert rows[0]['translationLocale'] == 'fr'
    assert rows[0]['translationText'] == 'synthetic French'
    with pytest.raises(ValueError):
        prepare_source(tmp_path, 'zzz', tmp_path/'decoded', source_path=source,
                       expected_source_locale='en', translation_locale='fr')
