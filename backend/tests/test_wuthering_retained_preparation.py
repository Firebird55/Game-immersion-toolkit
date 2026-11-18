"""Retained catalogue replay shares the current joins without replacing live discovery."""
import copy
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest

from backend import language_worker as worker, publisher_regions, wuthering_assets as assets
from backend import wuthering_release as release
from backend.tests.test_wuthering import plot_blob


@pytest.fixture
def original(tmp_path, monkeypatch):
    snapshot = {'schema': 1, 'base': {}, 'root': 'https://original.aki-game.net/retained/zip',
                'launcher': '1.0.0', 'products': {}, 'versions': {}}
    raw = json.dumps(snapshot, sort_keys=True, separators=(',', ':')).encode()
    stamp = 'wuwa-' + hashlib.sha256(raw).hexdigest()
    path = release._descriptor_path(tmp_path, stamp)
    path.parent.mkdir(parents=True); path.write_bytes(raw)
    calls = []
    def tables(tools, received, parameters, locales, folder):
        assert received == snapshot and set(locales) == set(assets.SUPPORTED_LOCALES)
        for locale in locales:
            file = folder/locale/'lang_multi_text.db'; file.parent.mkdir(parents=True)
            with closing(sqlite3.connect(file)) as db, db:
                db.execute('CREATE TABLE MultiText (Id TEXT, Content TEXT)')
                db.execute('INSERT INTO MultiText VALUES (?, ?)', ('spoken', '合成对白。' if locale == 'zh-Hans' else 'Owned original dialogue.'))
        with closing(sqlite3.connect(folder/'db_plot_audio.db')) as db, db:
            db.execute('CREATE TABLE plotaudio (Id TEXT, BinData BLOB)')
            db.execute('INSERT INTO plotaudio VALUES (?, ?)', ('spoken', plot_blob('spoken', 'vo_spoken')))
    monkeypatch.setattr(release, '_read_tables', tables)
    monkeypatch.setattr(release, '_voice_locations', lambda *_: {assets.EXTERNAL_ROOT+'en_vo_spoken.wem': ('original', 0)})
    monkeypatch.setattr(release, '_archive_parameters', lambda *_: ())
    monkeypatch.setattr(publisher_regions, 'selected_region', lambda *_: 'global')
    def current(*args):
        calls.append('current'); return stamp, copy.deepcopy(snapshot), (), {'original-live-pointer': b'current'}
    monkeypatch.setattr(release, '_current', current)
    monkeypatch.setattr(release, 'verify_pointers', lambda pointers: calls.append(('pointers', pointers)))
    monkeypatch.setattr(release, 'launcher', lambda region: calls.append(('launcher', region)) or ('1.0.0', snapshot['root'], {}))
    return tmp_path, stamp, path, snapshot, calls


def test_current_and_explicit_retained_input_use_same_real_joins_and_worker_bytes(original, monkeypatch):
    tools, stamp, path, snapshot, calls = original
    normal = release.build_language(tools, 'en', ['zh-Hans'])
    assert calls == ['current', ('pointers', {'original-live-pointer': b'current'}), ('launcher', 'global')]
    calls.clear()
    retained = release.build_retained_language(tools, stamp, 'en', ['zh-Hans'])
    assert calls == []  # Replay never asks a live root to impersonate the old catalogue.
    assert retained.pop('source_replay') == 'retained_original_catalogue' and retained == normal
    assert len(normal['records']) == 1 and normal['records'][0]['audio']['publisher'] == stamp
    monkeypatch.setattr(assets, 'index_language', lambda *_args, **_kwargs: copy.deepcopy(normal))
    ordinary, replay = tools/'ordinary.json', tools/'retained.json'
    worker.build('wuwa', None, tools, 'en', ['zh-Hans'], ordinary)
    worker.write_payload('wuwa', retained, 'en', ['zh-Hans'], replay)
    assert ordinary.read_bytes() == replay.read_bytes()
    expected = {**normal, 'dialogue_inventory': {'voice_counts': {'voiced': 1, 'unvoiced': 0, 'unavailable': 0, 'unknown': 0},
        'categories': {'dialogue': {'voiced': 1, 'unvoiced': 0, 'unavailable': 0, 'unknown': 0}}},
        'reader_revision': assets.LANGUAGE_INDEX_VERSION, 'targets_requested': ['zh-Hans']}
    assert ordinary.read_bytes() == json.dumps(expected, ensure_ascii=False).encode('utf-8')


@pytest.mark.parametrize('fault', ['digest', 'region', 'changed-descriptor', 'changed-region'])
def test_retained_replay_refuses_invalid_or_changing_authority(original, monkeypatch, fault):
    tools, stamp, path, snapshot, calls = original
    if fault == 'digest': path.write_bytes(path.read_bytes()+b' ')
    elif fault == 'region': monkeypatch.setattr(publisher_regions, 'selected_region', lambda *_: 'cn')
    else:
        selected = ['global']
        monkeypatch.setattr(publisher_regions, 'selected_region', lambda *_: selected[0])
        read = release._read_tables
        def changed(*args):
            read(*args)
            if fault == 'changed-descriptor': path.write_bytes(path.read_bytes()+b' ')
            else: selected[0] = 'cn'
        monkeypatch.setattr(release, '_read_tables', changed)
    with pytest.raises(ValueError):
        release.build_retained_language(tools, stamp, 'en', ['zh-Hans'])
    assert calls == []


@pytest.mark.parametrize('fault', ['pointer', 'launcher', 'region'])
def test_current_source_keeps_original_final_guards_and_never_falls_back(original, monkeypatch, fault):
    tools, stamp, path, snapshot, calls = original
    if fault == 'pointer':
        def changed(_): raise ValueError('Original live pointer changed')
        monkeypatch.setattr(release, 'verify_pointers', changed)
    elif fault == 'launcher': monkeypatch.setattr(release, 'launcher', lambda *_: ('2.0.0', snapshot['root'], {}))
    else:
        selected = ['global']
        monkeypatch.setattr(publisher_regions, 'selected_region', lambda *_: selected[0])
        read = release._read_tables
        def changed(*args):
            read(*args); selected[0] = 'cn'
        monkeypatch.setattr(release, '_read_tables', changed)
    with pytest.raises(ValueError): release.build_language(tools, 'en', ['zh-Hans'])
    assert calls[0] == 'current'


@pytest.mark.parametrize('fault', ['format', 'game', 'locale', 'empty', 'study-text', 'translation', 'dub', 'voice-status'])
def test_shared_worker_rejects_invalid_payload_before_replacing_old_output(original, fault):
    tools, stamp, path, snapshot, calls = original
    payload = release.build_retained_language(tools, stamp, 'en', ['zh-Hans'])
    output = tools/'prepared.json'; worker.write_payload('wuwa', copy.deepcopy(payload), 'en', ['zh-Hans'], output)
    before = output.read_bytes()
    if fault == 'format': payload['format'] = 1
    elif fault == 'game': payload['game'] = 'endfield'
    elif fault == 'locale': payload['source_locale'] = 'ja'
    elif fault == 'empty': payload['records'] = []
    elif fault == 'study-text': payload['records'][0]['source_text'] = ' '
    elif fault == 'translation': payload['records'][0]['texts']['en'] = 'Different canonical study text'
    elif fault == 'dub': payload['records'][0]['audio_locale'] = 'ja'
    else: payload['records'][0]['voice_status'] = 'unvoiced'
    with pytest.raises(ValueError): worker.write_payload('wuwa', payload, 'en', ['zh-Hans'], output)
    assert output.read_bytes() == before


def test_worker_real_interrupted_publication_preserves_last_complete_generation(original, monkeypatch):
    from backend import atomic_files

    tools, stamp, path, snapshot, calls = original
    payload = release.build_retained_language(tools, stamp, 'en', ['zh-Hans'])
    output = tools/'prepared.json'; worker.write_payload('wuwa', copy.deepcopy(payload), 'en', ['zh-Hans'], output)
    before = output.read_bytes(); payload['message'] = 'New generation'; replace = atomic_files.os.replace
    def interrupted(staged, destination):
        if destination == output:
            assert staged.name == 'download' and json.loads(staged.read_bytes())['message'] == 'New generation'
            assert output.read_bytes() == before
            raise OSError('Authored publication interruption')
        return replace(staged, destination)
    monkeypatch.setattr(atomic_files.os, 'replace', interrupted)
    with pytest.raises(OSError, match='publication interruption'):
        worker.write_payload('wuwa', payload, 'en', ['zh-Hans'], output)
    assert output.read_bytes() == before and not list(tools.glob('tmp*'))
