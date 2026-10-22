import json
import threading
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.multilingual_index import MultilingualTextIndex


DEFAULT_CHANNELS = ['dialogue', 'tip', 'cinematic', 'gameplay']


def row(identity, **extra):
    text = f'Synthetic caption {identity}.'
    return dict(text_id=identity, source_locale='en', source_text=text, texts={'en': text},
                audio_locale='en', audio={'file': identity}, **extra)


def snapshot(directory, records):
    path = directory / 'textmap.json'
    pending = directory / 'pending.json'
    pending.write_text(json.dumps({'format': 2, 'game': 'cyberpunk', 'source_locale': 'en', 'records': records}))
    pending.replace(path)


def legacy_membership(records, identity, channel):
    return any((r['text_id'] == identity or identity in (r.get('member_text_ids') or []))
               and channel in r.get('channels', DEFAULT_CHANNELS) for r in records)


@pytest.fixture
def records():
    no_audio = row('no-audio', channels=['cinematic'], member_text_ids=['no-audio-member'])
    no_audio['audio'] = None
    return [row('default'), row('empty', channels=[]), row('duplicate', channels=['tip']),
            row('duplicate', channels=['cinematic']), row('dialogue', channels=['dialogue'],
                member_text_ids=['member', 'shared', 'member']), row('second', channels=['gameplay'],
                member_text_ids=['shared']), no_audio, row('blank-members', member_text_ids=[]),
            row('null-members', member_text_ids=None), row('')]


def test_all_record_membership_exactly_matches_previous_scan(tmp_path, records):
    snapshot(tmp_path, records)
    index = MultilingualTextIndex('cyberpunk', tmp_path)
    assert index.ready
    for identity in ['default', 'empty', 'duplicate', 'dialogue', 'member', 'shared', 'second',
                     'no-audio', 'no-audio-member', 'blank-members', 'null-members', '', 'missing']:
        for channel in [*DEFAULT_CHANNELS, 'unknown', '']:
            assert index.is_capture_text(identity, 'unused', channel) == legacy_membership(records, identity, channel)
    assert index.match_text('Synthetic caption no-audio.') is None
    assert index.is_capture_text('no-audio-member', '', 'cinematic')


def test_membership_does_not_scan_catalog_after_load(tmp_path, records):
    snapshot(tmp_path, records)
    index = MultilingualTextIndex('cyberpunk', tmp_path)

    class NoScan(list):
        def __iter__(self):
            raise AssertionError('History membership scanned the complete catalog')

    index._records = NoScan(index._records)
    assert index.is_capture_text('shared', '', 'gameplay')
    assert not index.is_capture_text('missing', '', 'dialogue')


def test_refresh_publishes_complete_membership_and_failure_keeps_old_snapshot(tmp_path, monkeypatch):
    import backend.multilingual_index as module
    old = [row('old', member_text_ids=['shared'], channels=['tip']), row('retired')]
    new = [row('new', member_text_ids=['shared'], channels=['cinematic'])]
    snapshot(tmp_path, old)
    index = MultilingualTextIndex('cyberpunk', tmp_path)
    entered, release = threading.Event(), threading.Event()
    normalize = module.normalize_text

    def slow_normalize(*args):
        entered.set()
        assert release.wait(3)
        return normalize(*args)

    snapshot(tmp_path, new)
    monkeypatch.setattr(module, 'normalize_text', slow_normalize)
    result = []
    loader = threading.Thread(target=lambda: result.append(index.load()))
    loader.start()
    try:
        assert entered.wait(2)
        # Building must leave the complete old generation usable by readers.
        for _ in range(200):
            assert index.is_capture_text('shared', '', 'tip')
            assert not index.is_capture_text('shared', '', 'cinematic')
            assert index.is_capture_text('retired', '', 'dialogue')
    finally:
        release.set()
        loader.join(3)
    assert result == [True]
    assert index.is_capture_text('shared', '', 'cinematic')
    assert not index.is_capture_text('shared', '', 'tip')
    assert not index.is_capture_text('retired', '', 'dialogue')
    monkeypatch.setattr(module, 'normalize_text', normalize)
    for bad in ['{invalid', json.dumps({'format': 2, 'game': 'cyberpunk', 'source_locale': 'en',
            'records': [row('partial'), {**row('broken'), 'audio_locale': 'ja'}]})]:
        index.path.write_text(bad)
        assert not index.load()
        assert index.ready
        assert index.is_capture_text('shared', '', 'cinematic')
        assert not index.is_capture_text('partial', '', 'dialogue')
        assert index.match_text(new[0]['source_text'], channel='cinematic').text_id == 'new'


def test_real_history_and_favorites_routes_preserve_catalog_filtering(tmp_path, monkeypatch, records):
    from backend import api
    from backend.models import TextMatch
    from backend.storage import TranscriptStore
    snapshot(tmp_path, records)
    index = MultilingualTextIndex('cyberpunk', tmp_path)
    transcript = TranscriptStore(tmp_path / 'synthetic-history.db')
    for identity, channel, voiced in [('default', 'dialogue', True), ('empty', 'dialogue', True),
            ('shared', 'gameplay', True), ('no-audio-member', 'cinematic', True),
            ('missing', 'dialogue', True), ('default', 'tip', False)]:
        line = transcript.add(TextMatch(game='cyberpunk', text_id=identity, english='Synthetic',
            chinese='测试文字', source_ocr='Synthetic', score=100, kind='exact'), 'synthetic-session', channel=channel)
        transcript.update_audio(line.id, None, voiced)
        transcript.set_favorite(line.id, True)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(transcript=transcript, game_indexes={'cyberpunk': index}), raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8766')
    expected = [line.model_dump(mode='json') for line in transcript.list(game='cyberpunk')
                if line.voiced and legacy_membership(records, line.text_id, line.channel)]
    assert client.get('/api/lines?game=cyberpunk').json() == expected
    assert client.get('/api/lines?game=cyberpunk&before_id=4&limit=2').json() == [expected[1]]
    # Favorites intentionally retain saved rows even when a catalog removes one.
    assert client.get('/api/favorites?game=cyberpunk').json() == [line.model_dump(mode='json')
                                                               for line in transcript.list_favorites(game='cyberpunk')]
