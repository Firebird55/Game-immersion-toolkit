"""Exercise adapter routing through the real mobile-export preparation path."""
import json
from types import SimpleNamespace

import pytest

from backend.mobile_library import prepare_source, export_library, file_digest


@pytest.mark.parametrize('game', ['zzz', 'pragmata', 'cyberpunk', 'witcher3', 'wuwa', 'nte', 'honkai3', 'hito'])
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
    monkeypatch.setattr(local_voice, 'LocalVoiceAssetService', lambda game, data, decoder, output: Service(output))
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
