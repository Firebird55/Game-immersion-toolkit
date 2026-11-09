import hashlib
import json
import struct
from types import SimpleNamespace

import brotli
import pytest

from backend import endfield_release as publisher, endfield_tables
from backend import endfield_film_registry as registry, endfield_film_voice, endfield_cinematic_profile as profile


def text_table(name, key, value):
    root = bytes([endfield_tables.MAP]) + name.encode() + bytes([0, endfield_tables.LONG, endfield_tables.STRING])
    string_pos = 16 + len(root)
    string = value.encode() + b'\0'
    data_pos = (string_pos + len(string) + 7) // 8 * 8
    header = struct.pack('<4i', 12, 16, data_pos, 0)
    # Count and lookup bucket precede the aligned int64 key.
    return (header + root + string).ljust(data_pos, b'\0') + struct.pack('<i12xqi', 1, key, string_pos)


def test_owned_sparkbuffer_reads_exact_name_signed_key_and_utf8():
    raw = text_table('I18nTextTable_EN', -120, 'Quoted ☀')
    assert endfield_tables.read(raw, 'I18nTextTable_EN') == {'-120': 'Quoted ☀'}
    with pytest.raises(ValueError):
        endfield_tables.read(raw, 'I18nTextTable_JP')
    with pytest.raises(ValueError):
        endfield_tables.read(raw[:-4] + struct.pack('<i', len(raw)), 'I18nTextTable_EN')


def test_released_generation_follows_both_layers_and_preserves_old_descriptor(tmp_path, monkeypatch):
    version = '1.0.3'
    current = {'initial': b'a' * 40, 'main': b'b' * 40}
    def fetch(url, **_limits):
        if url == publisher.LATEST:
            return json.dumps({'version': version, 'pkg': {'packs': [
                {'url': publisher.CDN + '/1.0/update/6/6/Windows/1.0.3_test/packs/a.zip'}]}})
        if 'get_latest_resources?' in url:
            assert 'rand_str=test' in url
            return json.dumps({'resources': [{'name': role, 'version': '123-1', 'path':
                publisher.CDN + '/1.0/resource/Windows/' + role + '/123-1_test/files'} for role in current]})
        return current[url.rsplit('index_', 1)[1].split('.')[0]]
    monkeypatch.setattr(publisher, 'download', fetch)
    first, data = publisher.discover()
    publisher._atomic_file(tmp_path / 'endfield-releases' / first, data)
    current['initial'] += b'x'
    second, raw = publisher.discover()
    assert second != first
    assert publisher.descriptor(tmp_path, first)['layers']['initial']['sha256'] == hashlib.sha256(b'a' * 40).hexdigest()
    assert json.loads(raw)['layers']['initial']['sha256'] == hashlib.sha256(current['initial']).hexdigest()
    with pytest.raises(ValueError):
        publisher._resource_url('https://example.org/file', 'main')


def test_regional_timeline_profile_requires_both_publisher_indexes(tmp_path, monkeypatch):
    catalog = object.__new__(publisher.Catalog)
    catalog.tools, catalog.stamp = tmp_path, 'fixture'
    layers = {role: {'sha256': digest} for role, digest in publisher.FILM_MANIFESTS.items()}
    monkeypatch.setattr(publisher, 'descriptor', lambda *_: {'layers': layers})
    assert catalog.has_verified_clocks()
    layers['main'] = {'sha256': '0' * 64}
    assert not catalog.has_verified_clocks()


def test_cinematic_registry_selects_full_asset_path_and_bounds_decompression():
    def field(data):
        return struct.pack('<i', len(data)) + data

    path = 'assets/beyond/test.playable'
    name = 'main/abc123.ab'
    first = field(brotli.compress(path.encode('utf-16le')))
    assets = bytes(4) + struct.pack('<qii8x', 27, 0, 11)
    bundles = struct.pack('<iii40x', 1, 11, len(first))
    strings = first + field(name.encode('utf-16le'))
    data = bytes.fromhex('11ff11ff00000000f4f3f2f1') + bytes(8)
    data += field(assets) + field(b'') + field(bundles) + field(strings)
    assert registry.bindings(data, path_hashes={27}) == [(27, path, name)]
    assert registry.bindings(data, bundle_indices={11}) == [(27, path, name)]
    assert registry.bindings(data, path_hashes={11}) == []
    with pytest.raises(ValueError):
        registry.bindings(data[:-1], path_hashes={27})
    with pytest.raises(ValueError):
        registry.inflate(brotli.compress(bytes(65536)), 1024)


def test_film_event_definition_counts_unsupported_and_duplicate_objects():
    def section(data):
        return b'HIRC' + struct.pack('<I', len(data)) + data
    obj = struct.pack('<BII', 4, 4, 123)
    assert endfield_film_voice.event_counts(section(struct.pack('<I', 2) + obj * 2), {123, 321}) == {123: 2}
    assert not endfield_film_voice.event_counts(section(struct.pack('<I', 1) + obj), {321})
    with pytest.raises(ValueError):
        endfield_film_voice.event_counts(section(struct.pack('<I', 2) + obj), {123})
    with pytest.raises(ValueError):
        endfield_film_voice.event_counts(section(struct.pack('<I', 1) + obj + bytes(2)), {123})


def test_historical_hotfix_shards_keep_the_published_dub():
    assert publisher.hotfix_dub('Audio/hotfix_japanese_bD0.pck') == 'japanese'
    assert publisher.hotfix_dub('Audio/hotfix_main_b1A.pck') == 'main'
    assert publisher.hotfix_dub('Audio/hotfix_english.pck') == 'english'
    with pytest.raises(ValueError):
        publisher.hotfix_dub('Audio/hotfix_english_new_layout.pck')


def test_batch_film_bindings_reject_shared_and_redefined_voice_events(tmp_path, monkeypatch):
    names = ('au_vo_local', 'au_vo_shared', 'au_vo_duplicate', 'au_vo_delayed')
    local, shared, duplicate, delayed = (endfield_film_voice.wwise_hash(name) for name in names)
    def soundbank(ids):
        hirc = struct.pack('<I', len(ids)) + b''.join(struct.pack('<BII', 4, 4, key) for key in ids)
        return b'BKHD' + struct.pack('<II', 4, 150) + b'HIRC' + struct.pack('<I', len(hirc)) + hirc
    files = {12: ('default_banks.pck', (shared, duplicate)),
             102: ('default_english_banks.pck', (local, duplicate, delayed)),
             21: ('hotfix_japanese_bD0.pck', (local,))}
    def group(_tools, _stamp, block):
        if block not in files:
            return '', []
        name, keys = files[block]
        data = soundbank(keys)
        return '', [SimpleNamespace(name=name, data=data, size=len(data))]
    class Package:
        def __init__(self, source, params):
            self.source = source
            self._bank(1, 0, source.size)
    monkeypatch.setattr(endfield_film_voice.vfs, 'Package', Package)
    monkeypatch.setattr(endfield_film_voice.endfield_metadata, 'parameters', lambda _: None)
    monkeypatch.setattr(publisher, 'group', group)
    monkeypatch.setattr(publisher, '_source', lambda *args: None)
    monkeypatch.setattr(publisher, '_whole', lambda _tools, _base, file: file.data)
    def layers(path):
        return {key: [{'media_id': 15, 'delay_seconds': int(key == delayed)}]
                for key in endfield_film_voice.event_counts(path.read_bytes(), {local, duplicate, delayed})}
    monkeypatch.setattr(endfield_film_voice, 'read_bank_play_layers', layers)
    assert endfield_film_voice.recording_ids(tmp_path, 'build', 'english', names) == {'au_vo_local': 15}


def test_carry_forward_requires_current_clock_bank_and_recording(tmp_path, monkeypatch):
    monkeypatch.setattr(publisher, 'descriptor', lambda *_: {'layers': {k: {'sha256': 'changed'} for k in publisher.FILM_MANIFESTS}})
    monkeypatch.setattr(profile, 'FILMS', {k: (None, (i, str(i)), None, None)
                                          for i, k in enumerate(('same', 'retimed', 'new_voice', 'rebound'))})
    monkeypatch.setattr(profile, 'EVENTS', {k: (None, 'au_vo_' + k, None, None) for k in profile.FILMS})
    assets = {'singleconfigs/' + k + '.asset' for k in profile.FILMS}
    assets.update(k + '_others_au_en.playable' for k in ('same', 'new_voice', 'rebound'))
    monkeypatch.setattr(publisher, '_unchanged_film_assets', lambda *_: assets)
    def bank(_tools, stamp, dub, names):
        assert dub == 'english' and set(names) == {'au_vo_same', 'au_vo_new_voice', 'au_vo_rebound'}
        return {'au_vo_same': 0, 'au_vo_new_voice': 2, 'au_vo_rebound': 99} if stamp == 'first' else {}
    monkeypatch.setattr(endfield_film_voice, 'recording_ids', bank)
    def media(_tools, _stamp, dub, identity, digest):
        assert dub == 'english' and digest == str(identity)
        if identity == 2:
            raise publisher.UnmatchedRecording()
        assert identity == 0
    monkeypatch.setattr(publisher, 'media', media)
    assert publisher.verified_films(tmp_path, 'first', 'english') == {'same'}
    assert publisher.verified_films(tmp_path, 'next', 'english') == set()


def test_in_engine_scene_requires_its_own_director_audio_and_regional_clock(tmp_path, monkeypatch):
    scenes = profile.SCENE_FILMS
    monkeypatch.setattr(profile, 'FILMS', scenes)
    monkeypatch.setattr(publisher, 'descriptor', lambda *_: {'layers': {
        role: {'sha256': 'changed'} for role in publisher.FILM_MANIFESTS}})
    english = {path for scene in scenes for path in profile.scene_dependencies(scene, 'english')}
    assert english <= profile.SCENE_ASSETS.keys()
    male = 'm_cutscene_e0m0_5'
    female = 'f_cutscene_e0m0_5'
    def sources(_tools, stamp):
        if stamp == 'male-audio-changed':
            return {path for path in english if not path.endswith('/' + male + '_audio.prefab')}
        if stamp == 'english-clock-changed':
            return {path for path in english if not path.endswith('_others_au_en.playable')}
        return english
    monkeypatch.setattr(publisher, '_unchanged_film_assets', sources)
    monkeypatch.setattr(endfield_film_voice, 'recording_ids', lambda *_: {
        profile.EVENTS[scene][1]: ids[1][0] for scene, ids in scenes.items()})
    monkeypatch.setattr(publisher, 'media', lambda *_: None)
    assert publisher.verified_films(tmp_path, 'same', 'english') == {male, female}
    assert publisher.verified_films(tmp_path, 'male-audio-changed', 'english') == {female}
    assert publisher.verified_films(tmp_path, 'english-clock-changed', 'english') == set()
    assert publisher.verified_films(tmp_path, 'same', 'japanese') == set()
