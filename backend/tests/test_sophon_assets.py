import hashlib
import json
import struct
from types import SimpleNamespace

import pytest
import zstandard

from backend import dialogue_catalog, starrail_publisher
from backend.preparation_errors import PreparationFailure
from backend import genshin_publisher as publisher, sophon_assets as sophon
from backend.voice_assets import voice_hash


def varint(value):
    result = bytearray()
    while value >= 128:
        result.append(128 | (value & 127))
        value >>= 7
    result.append(value)
    return bytes(result)


@pytest.mark.parametrize('winner_ok', [True, False])
def test_windows_chunk_write_collision_requires_verified_winner(tmp_path, monkeypatch, winner_ok):
    data = b'original chunk'
    archive = zstandard.ZstdCompressor().compress(data)
    digest = hashlib.md5(data).hexdigest()
    monkeypatch.setattr(sophon, 'download', lambda *_args, **_kwargs: archive)
    def competing_writer(path, payload):
        path.write_bytes(payload if winner_ok else b'x' * len(payload))
        raise PermissionError('concurrent reader')
    monkeypatch.setattr(sophon, '_atomic_file', competing_writer)
    args = (tmp_path, 'url', len(archive), len(data), digest, sophon.MAX_CHUNK)
    if winner_ok:
        assert sophon._verified(*args) == data
    else:
        with pytest.raises(PermissionError):
            sophon._verified(*args)


def field(number, value):
    if isinstance(value, int):
        return varint(number << 3) + varint(value)
    return varint(number << 3 | 2) + varint(len(value)) + value


def test_older_sophon_manifest_directories_are_not_data_files(tmp_path, monkeypatch):
    base = 'https://autopatchhk.yuanshen.com/test'
    def read(body):
        raw = field(1, body)
        digest = hashlib.md5(raw).hexdigest()
        name = 'manifest_' + '0' * 16 + '_' + digest
        monkeypatch.setattr(sophon, '_verified', lambda *args: raw)
        return sophon.manifest(tmp_path, 'genshin-global', (base, name, 1, len(raw), digest, base), ('',))
    directory = field(1, b'GenshinImpact_Data/StreamingAssets') + field(3, 64) + field(4, 0)
    assert read(directory) == {}
    with pytest.raises((ValueError, KeyError)):
        read(field(1, b'file.pck') + field(4, 12))


def fixture(directory, monkeypatch, version, speech, *, game='genshin', channel=None):
    source = 'English(US)\\VO_AQ\\synthetic.wem' if game == 'genshin' else 'English/voice/story/test.wem'
    identity = voice_hash(source)
    wem = b'RIFF' + struct.pack('<I', 4 + len(speech)) + b'WAVE' + speech
    table = struct.pack('<I Q4I', 1, identity, 1, len(wem), 56, 0)
    package = b'AKPK' + struct.pack('<6I', 48, 1, 0, 0, 0, len(table)) + table + wem
    channel = channel or publisher.voices.CHANNELS[game]
    base = 'https://' + sophon.CHANNELS[channel][3] + '/test/' + version
    folder = 'GenshinImpact_Data' if channel == 'genshin-global' else 'YuanShen_Data'
    name = (folder + '/StreamingAssets/AudioAssets/English(US)/1.pck' if game == 'genshin' else
            'StarRail_Data/Persistent/Audio/AudioPackage/Windows/English/External0.pck')
    md5 = lambda data: hashlib.md5(data).hexdigest()
    def encode(data):
        return zstandard.ZstdCompressor(write_content_size=False).compress(data)
    objects = {}
    row = field(1, name.encode()) + field(4, len(package)) + field(5, md5(package).encode())
    for start, chunk in [(0, package[:60]), (60, package[60:])]:
        obj = '0' * 16 + '_' + md5(chunk)
        objects[base + '/' + obj] = encoded = encode(chunk)
        row += field(2, field(1, obj.encode()) + field(2, md5(chunk).encode()) +
                     field(3, start) + field(4, len(encoded)) + field(5, len(chunk)))
    raw = field(1, row)
    manifest_id = 'manifest_' + '0' * 16 + '_' + md5(raw)
    objects[base + '/' + manifest_id] = encoded = encode(raw)
    spec = (base, manifest_id, len(encoded), len(raw), md5(raw), base)
    build = {'channel': channel, 'version': version, 'manifests': {'en-us': spec}}
    stamp, descriptor = publisher.voices.descriptor(build)
    sophon._atomic_file(directory / 'tools/sophon/releases' / stamp, descriptor)
    monkeypatch.setattr(sophon, 'download', lambda url, limit: objects[url])
    return source, identity, stamp, wem, objects


def test_new_build_changes_voice_and_old_cached_clip_survives_offline(tmp_path, monkeypatch):
    clips = []
    for version, speech in [('1.0.0', b'first synthetic clip'), ('1.1.0', b'second synthetic clip')]:
        source, identity, stamp, wem, objects = fixture(tmp_path, monkeypatch, version, speech)
        binding = publisher.inventory(tmp_path, stamp, 'en')[identity] | {
            'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
        assert publisher.extract(binding, tmp_path / 'tools') == wem
        clips.append((binding, wem))
    assert clips[0][0]['publisher'] != clips[1][0]['publisher']
    objects.clear()
    sophon.manifest.cache_clear()
    publisher.voices._files.cache_clear()
    publisher.voices._table.cache_clear()
    for binding, wem in clips:
        assert publisher.extract(binding, tmp_path / 'tools') == wem
        with pytest.raises(ValueError):
            publisher.extract(binding | {'locale': 'ja'}, tmp_path / 'tools')


def test_genshin_update_retains_only_identical_released_dialogue(tmp_path, monkeypatch):
    from backend.genshin_history import retained_performances
    source, identity, original, wem, _ = fixture(tmp_path, monkeypatch, '1.0.0', b'original')
    package = publisher.inventory(tmp_path, original, 'en')[identity]
    audio = package | {'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
    links = [{'id': str(i), 'source': source} for i in range(6)]
    def records():
        return [{'text_id': 'genshin:' + link['id'], 'source_text': 'A sentence', 'player_voice': None,
                 'audio': None, 'voice_status': 'unavailable'} for link in links]

    old = records()
    for row in old:
        row.update(audio=audio, voice_status='voiced')
    assert retained_performances(tmp_path, original, 'cn', 'en', links, old, set()) == 0
    assert publisher.extract(audio, tmp_path / 'tools') == wem
    _, _, new, _, _ = fixture(tmp_path, monkeypatch, '1.1.0', b'new')
    now = records()
    now[1]['source_text'] = 'Rewritten dialogue'
    now[2]['player_voice'] = 'male'
    links[3]['source'] = source.replace('synthetic', 'another')
    now[4].update(audio=audio | {'publisher': new}, voice_status='voiced')
    now[5]['voice_status'] = 'unvoiced'
    assert retained_performances(tmp_path, new, 'global', 'en', links, now, set()) == 0
    assert retained_performances(tmp_path, new, 'cn', 'en', links, now, {identity}) == 0
    assert retained_performances(tmp_path, new, 'cn', 'en', links, now, set()) == 1
    assert now[0]['audio'] == audio | {'publisher': new, 'original_publisher': original}
    assert publisher.extract(now[0]['audio'], tmp_path / 'tools') == wem
    assert [r['voice_status'] for r in now[1:]] == ['unavailable'] * 3 + ['voiced', 'unvoiced']


def test_genshin_archived_data_retries_and_cannot_displace_a_newer_preparation(tmp_path, monkeypatch):
    from backend import genshin_history as history
    source, identity, earlier, _, _ = fixture(tmp_path, monkeypatch, '1.0.0', b'earlier')
    _, _, later, _, _ = fixture(tmp_path, monkeypatch, '2.0.0', b'later')
    links = [{'id': '42', 'source': source}]
    def rows(stamp):
        return [{'text_id': 'genshin:42', 'source_text': 'A sentence', 'player_voice': None,
                 'voice_status': 'voiced' if stamp else 'unavailable', 'audio': None if not stamp else {
                     'publisher': stamp, 'package': 'same.pck', 'source': source}}]
    history.retained_performances(tmp_path, later, 'cn', 'en', links, rows(later), set())
    calls = []
    def archive(data_dir, region, locale, version, *, mirror=False):
        calls.append((locale, mirror))
        if len(calls) <= 2:
            raise TimeoutError()
        history.retained_performances(data_dir, earlier, region, locale, links, rows(earlier), set(), archive=history.ARCHIVES[version]['metadata'])
    monkeypatch.setattr(history, '_seed_archive', archive)
    assert not history.prepare_archive(tmp_path, 'cn', 'en', '4.8.0')
    assert history.prepare_archive(tmp_path, 'cn', 'en', '4.8.0')
    assert history.prepare_archive(tmp_path, 'cn', 'en', '4.8.0')
    assert calls == [('en', False), ('en', True), ('en', False)]
    missing = rows(None)
    assert history.retained_performances(tmp_path, 'new', 'cn', 'en', links, missing, set()) == 1
    assert missing[0]['audio']['original_publisher'] == later


def test_genshin_regions_retain_their_own_originals_offline(tmp_path, monkeypatch):
    clips = []
    for channel in ('genshin-global', 'genshin-cn'):
        source, identity, stamp, wem, _ = fixture(tmp_path, monkeypatch, '1.0.0', channel.encode(), channel=channel)
        binding = publisher.inventory(tmp_path, stamp, 'en')[identity] | {
            'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
        assert publisher.voices.snapshot_available(tmp_path / 'tools', stamp, 'genshin')
        assert not publisher.voices.snapshot_available(tmp_path / 'tools', stamp, 'starrail')
        assert publisher.extract(binding, tmp_path / 'tools') == wem
        clips.append((binding, wem))
    assert clips[0][0]['publisher'] != clips[1][0]['publisher']
    sophon.manifest.cache_clear()
    publisher.voices._table.cache_clear()
    publisher.voices._files.cache_clear()
    def offline(*args, **kwargs):
        pytest.fail('An already cached regional recording went online')
    monkeypatch.setattr(sophon, 'download', offline)
    for binding, wem in clips:
        assert publisher.extract(binding, tmp_path / 'tools') == wem


def test_genshin_global_text_needs_matching_regional_release_or_all_original_resources(tmp_path, monkeypatch):
    builds = {key: {'channel': key, 'version': '2.0.0', 'manifests': {'game': (key,)}} for key in publisher.ROOTS}
    monkeypatch.setattr(sophon, 'release', builds.__getitem__)
    class Marker:
        def __init__(self, data):
            self.size = len(data)
            self.digest = hashlib.md5(data).hexdigest()
            self.data = data
        def read(self, _cache, start, size):
            return self.data[start:start + size]
    assets = {**{key: Marker(b'index') for key in publisher.INDEXES},
              'AssetBundles/blocks/ab/cd.blk': Marker(b'dialogue'),
              **{'AssetBundles/' + field: Marker(str(i).encode()) for i, field in enumerate(publisher.MARKERS, 1)}}
    manifests = {c: {root + k: v for k, v in assets.items()} for c, root in publisher.ROOTS.items()}
    monkeypatch.setattr(sophon, 'manifest', lambda directory, channel, spec, suffixes: manifests[channel])
    def cn_only(game, title):
        if title != 'CNRELWin2.0.0_R1_S2_D3':
            raise PreparationFailure('publisher_unavailable', 'Missing regional extraction')
        return 'a' * 40
    monkeypatch.setattr(publisher, 'matching_release_commit', cn_only)
    global_build = builds['genshin-global']
    assert publisher._catalog(tmp_path, global_build, 'global') == 'a' * 40
    cn = manifests['genshin-cn']
    for key in ('AssetBundles/blocks/ab/cd.blk', 'data_versions_streaming', 'ctable_streaming.dat', 'svc_catalog'):
        path = publisher.ROOTS['genshin-cn'] + key
        cn[path] = Marker(b'replaced')
        with pytest.raises(PreparationFailure, match='Global'):
            publisher._catalog(tmp_path, global_build, 'global')
        cn[path] = assets[key]
    cn[publisher.ROOTS['genshin-cn'] + 'AssetBundles/blocks/extra.blk'] = Marker(b'extra')
    with pytest.raises(PreparationFailure, match='Global'):
        publisher._catalog(tmp_path, global_build, 'global')
    monkeypatch.setattr(publisher, 'matching_release_commit', lambda game, title: title)
    assert publisher._catalog(tmp_path, global_build, 'global') == 'OSRELWin2.0.0_R1_S2_D3'


def test_mismatched_or_truncated_chunk_cannot_replace_good_data(tmp_path, monkeypatch):
    source, identity, stamp, wem, objects = fixture(tmp_path, monkeypatch, '2.0.0', b'synthetic')
    binding = publisher.inventory(tmp_path, stamp, 'en')[identity] | {
        'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
    last = next(url for url in objects if not url.split('/')[-1].startswith('manifest_') and
                not (tmp_path / 'tools/sophon/chunks' / url.rsplit('_', 1)[1]).exists())
    objects[last] = objects[last][:-1]
    with pytest.raises(ValueError):
        publisher.extract(binding, tmp_path / 'tools')
    assert not (tmp_path / 'tools/sophon/chunks' / last.rsplit('_', 1)[1]).exists()


def test_interrupted_publisher_download_retries_only_the_unfinished_chunk(tmp_path, monkeypatch):
    from http.client import IncompleteRead
    source, identity, stamp, wem, objects = fixture(tmp_path, monkeypatch, '2.1.0', b'synthetic')
    binding = publisher.inventory(tmp_path, stamp, 'en')[identity] | {
        'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
    calls = []
    def intermittent(url, limit):
        calls.append(url)
        if len(calls) == 1:
            raise IncompleteRead(b'ab')
        return objects[url]
    monkeypatch.setattr(sophon, 'download', intermittent)
    assert publisher.extract(binding, tmp_path / 'tools') == wem
    assert len(calls) == 2 and calls[0] == calls[1]


def test_catalog_requires_region_and_three_revision_markers(monkeypatch):
    sha = 'a' * 40
    rows = [{'title': 'CNRELWin1.2.0_R10_S20_D31', 'id': 'b' * 40},
            {'title': 'CNRELWin1.2.0_R10_S20_D30', 'id': sha}]
    monkeypatch.setattr(dialogue_catalog, 'download', lambda *args, **kwargs: json.dumps(rows))
    assert dialogue_catalog.matching_release_commit('genshin', rows[1]['title']) == sha
    with pytest.raises(PreparationFailure):
        dialogue_catalog.matching_release_commit('genshin', 'OSRELWin1.2.0_R10_S20_D30')


def test_starrail_release_checks_all_revisions_before_reusing_hotfix_comparison():
    marker = bytearray(66)
    marker[:8] = b'SRMI\x00\x03\x00\x01'
    struct.pack_into('<I', marker, 8, 66)
    struct.pack_into('<I', marker, 24, 16566615)
    assert starrail_publisher.revision_marker(marker) == 16566615
    with pytest.raises(ValueError):
        starrail_publisher.revision_marker(marker[:-1])
    reviewed = (16566615, 16566615, 16566587, 16566615)
    assert starrail_publisher.release_title(starrail_publisher.VERIFIED_46, '4.6.0', reviewed) == starrail_publisher.VERIFIED_46_TEXT
    assert starrail_publisher.release_title('different manifest', '4.6.0', reviewed) == 'OSPRODWin4.6.0_D16566615_A16566615_L16566587'
    assert starrail_publisher.release_title('next manifest', '4.7.0', (20, 19, 18, 19)) == 'OSPRODWin4.7.0_D20_A19_L18'
    with pytest.raises(ValueError):
        starrail_publisher.release_title('next manifest', '4.7.0', (20, 19, 18, 21))


def test_starrail_marker_binds_its_own_resource_index_by_path_digest_and_size(tmp_path):
    files = {}
    for revision, suffix in enumerate(starrail_publisher.MARKERS, 1):
        directory, marker_name = ('StarRail_Data/StreamingAssets/' + suffix).rsplit('/', 1)
        index_name = marker_name[2:-6]
        raw = bytearray(66)
        raw[:8] = b'SRMI\x00\x03\x00\x01'
        digest = hashlib.md5(index_name.encode()).hexdigest()
        struct.pack_into('<I', raw, 8, len(raw))
        struct.pack_into('<I4IQ', raw, 24, revision,
                         *(int(digest[i:i + 8], 16) for i in range(0, 32, 8)), 100)
        files[directory + '/' + marker_name] = SimpleNamespace(size=66, read=lambda _d, _o, _n, data=bytes(raw): data)
        path = f'{directory}/{index_name}_{digest}.bytes'
        files[path] = SimpleNamespace(size=100, digest=digest)
    assert starrail_publisher.release_revisions(tmp_path, files) == (1, 2, 3, 4)
    for wrong in (SimpleNamespace(size=100, digest='0' * 32), SimpleNamespace(size=99, digest=digest), None):
        files[path] = wrong
        with pytest.raises(ValueError, match='index does not match'):
            starrail_publisher.release_revisions(tmp_path, files)


def test_starrail_cannot_replay_another_game_or_another_dub(tmp_path, monkeypatch):
    voices = publisher.voices
    source, identity, stamp, wem, _ = fixture(tmp_path, monkeypatch, '1.2.0', b'star rail', game='starrail')
    tools = tmp_path / 'tools'
    entry = voices.inventory(tmp_path, stamp, 'en', 'starrail')[identity]
    audio = entry | {'file_id': f'{identity:016x}', 'source': source, 'locale': 'en'}
    assert voices.extract(audio, tools, 'starrail') == wem
    assert voices.snapshot_available(tools, stamp, 'starrail')
    assert not voices.snapshot_available(tools, stamp, 'genshin')
    with pytest.raises(ValueError):
        voices.extract(audio | {'locale': 'ko'}, tools, 'starrail')


def test_optional_starrail_chapters_require_the_active_release_path_size_and_digest(tmp_path, monkeypatch):
    # An identical name from another launcher build is insufficient.
    stamp = starrail_publisher.VERIFIED_46
    prefix = 'StarRail_Data/Persistent/Audio/AudioPackage/Windows/Korean/'
    path = prefix + 'External_del_4.6_chapter5_0.pck'
    _, size, digest = starrail_publisher.CHAPTER_PACKAGES['Korean'][0]
    calls = []
    selected = {path: SimpleNamespace(size=size, digest=digest)}

    def files(directory, channel, spec, names):
        calls.append(names)
        return selected.copy()

    monkeypatch.setattr(sophon, 'manifest', files)
    assert starrail_publisher.optional_files(tmp_path, 'next-release', 'ko') == {}
    assert starrail_publisher.optional_files(tmp_path, stamp, 'ja') == {}
    assert calls == []
    assert starrail_publisher.optional_files(tmp_path, stamp, 'ko') == selected
    assert calls == [(path,)]
    for index, bad in enumerate(({path: SimpleNamespace(size=size, digest='0' * 32)},
                                 {path: SimpleNamespace(size=size + 1, digest=digest)},
                                 {prefix + 'External_del_4.6_chapter5_1.pck': selected[path]})):
        selected = bad
        with pytest.raises(ValueError, match='differ'):
            starrail_publisher.optional_files(tmp_path / str(index), stamp, 'ko')
