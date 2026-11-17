"""Owned updater envelopes, current inventories and retained voice generations."""
import base64
import io
import json
import struct
from urllib.error import URLError

import pytest
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from backend import hoyo_publisher_voice as voice, language_worker, sophon_assets, zzz_assets, zzz_hotfix as live, zzz_publisher
from backend.xxhash64 import xxhash64
from backend.voice_assets import voice_hash


@pytest.fixture(autouse=True)
def owned_streams(monkeypatch):
    # Existing owned envelopes use one deterministic transport for metadata and
    # raw assets. Separate streaming fixtures below observe every bounded read.
    monkeypatch.setattr(live, '_stream_response', lambda url, size: io.BytesIO(live._request(url, {}, size)))


class Source:
    def __init__(self, name, data):
        self.name, self.data, self.size = name, data, len(data)

    def read(self, _directory, start, length):
        return self.data[start:start + length]


def encoded(value):
    return json.dumps(value, separators=(',', ':')).encode()


def inventory(rows):
    return encoded({'remoteParentDir': '', 'files': rows, 'basePackages': [], 'baseOnlyPackages': [], 'baseOnlyTitles': []})


def row(name, data, patch=True):
    return {'remoteName': name, 'fileSize': len(data), 'md5': str(xxhash64(data)), 'isPatch': patch}


def snapshot(revision, bodies, channel='zzz-global'):
    edition = live.EDITIONS[channel]
    roots = {kind: f'https://{edition["host"]}/{directory}/9.0_live/output_{revision}_abcdef/{client}/StandaloneWindows64/{edition["area"]}/'
             for kind, directory, client in [('design', 'design_data', 'client'), ('resource', 'game_res', 'client'),
                                              ('silence', 'design_data', 'client_silence')]}
    indexes = {name: {'name': live.INDEXES[name][1], 'size': len(raw), 'hash': str(xxhash64(raw))}
               for name, raw in bodies.items()}
    return {'channel': channel, 'version': '9.0.0', 'build': 'unchanged-launcher',
            'manifests': {'game': ['game'], 'en-us': ['en']},
            'hotfix': {'roots': roots, 'indexes': indexes, 'revisions': {'design': str(revision)},
                       'audio_revision': str(revision), 'base_revision': '1000_abcdef'}}


@pytest.mark.parametrize('unavailable', [False, True])
@pytest.mark.parametrize('channel', ['zzz-global', 'zzz-cn'])
def test_public_gateway_parameters_and_separate_revisions_are_source_driven(monkeypatch, unavailable, channel):
    key = RSA.generate(1024)
    edition = live.EDITIONS[channel]
    server = 'prod_gf_eu' if channel == 'zzz-global' else 'prod_gf_cn'
    values = {'GameDispatchChannelName': edition['prefix'], 'GameDispatchDefaultName': server,
              'GameDispatchURLTemplate': '?version={0}{1}&channel_id=1&platform=3',
              'GameGatewayURLTemplate': '?version={0}{1}&language=1&seed={2}',
              'ProtoDispatchKey': 'owned-fixture',
              'endpoints': [f'https://globaldp-prod-{edition["dispatch"]}0{number}.{edition["domain"]}/query_dispatch'
                            for number in (1, 2)]}
    def settings(region):
        assert region == edition['region']
        return values, key
    monkeypatch.setattr(live, '_settings', settings)
    base = b'1000_abcdef'
    bodies = {name: (base if name == 'base' else b'owned fixture') for name in live.INDEXES}
    first = snapshot(2000, bodies, channel)
    cdn = {}
    for kind, field, revision in [('design', 'design_data', 'data_revision'), ('resource', 'game_res', 'res_revision'),
                                    ('silence', 'silence_data', 'silence_revision')]:
        specs = [{'fileName': spec['name'], 'fileSize': spec['size'], 'fileMD5': spec['hash']}
                 for name, spec in first['hotfix']['indexes'].items() if live.INDEXES[name][0] == kind]
        suffix = 'StandaloneWindows64/' + edition['area'] + '/'
        cdn[field] = {'base_url': first['hotfix']['roots'][kind].removesuffix(suffix),
                      revision: '1111' if kind == 'silence' else '2000', 'md5_files': json.dumps(specs)}
    cdn['game_res']['audio_revision'] = '1555'
    payload = encoded({'retcode': 0, 'cdn_conf_ext': cdn, 'client_secret_key': 'must-never-persist'})
    cipher = PKCS1_v1_5.new(key.public_key())
    encrypted = b''.join(cipher.encrypt(payload[i:i + 117]) for i in range(0, len(payload), 117))
    seen = []
    def request(url, headers, maximum):
        seen.append((url, headers))
        if unavailable and url.startswith(values['endpoints'][0]):
            raise URLError('owned unavailable endpoint')
        if '/query_dispatch?' in url:
            return encoded({'retcode': 0, 'region_list': [{'retcode': 0, 'name': server,
                'dispatch_url': f'https://{server.replace("_", "-")}.{edition["domain"]}/query_gateway'}]})
        if '/query_gateway?' in url:
            return encoded({'content': base64.b64encode(encrypted).decode(), 'sign': 'not-an-authentication-proof'})
        assert url.endswith('/base_revision')
        return base
    monkeypatch.setattr(live, '_request', request)
    build = live.discover({k: v for k, v in first.items() if k != 'hotfix'})
    assert build['hotfix']['revisions'] == {'design': '2000', 'resource': '2000', 'silence': '1111'}
    assert build['hotfix']['audio_revision'] == '1555'
    assert 'client_secret_key' not in json.dumps(build)
    assert seen[-2][1]['version'] == edition['prefix'] + '9.0.0' and seen[-2][1]['seed'] == 'owned-fixture'
    assert not any('account' in name for _, headers in seen for name in headers)
    values['endpoints'] = ['https://untrusted.example/query_dispatch']
    with pytest.raises(ValueError):
        live.discover({k: v for k, v in first.items() if k != 'hotfix'})
    assert len(seen) == (4 if unavailable else 3)


def test_known_inventory_fields_allow_the_publishers_string_size_and_extra_metadata():
    assert live._spec({'fileName': 'data_version', 'fileSize': '23', 'fileMD5': '42', 'optional': 'future'}) == {
        'name': 'data_version', 'size': 23, 'hash': '42'}
    assert live._spec({'fileName': 'res_version', 'fileSize': 5 * 1024**2, 'fileMD5': '42'})['size'] == 5 * 1024**2
    with pytest.raises(ValueError):
        live._spec({'fileName': 'res_version', 'fileSize': live.MAX_INDEX + 1, 'fileMD5': '42'})
    query, headers = live._query('?version={0}&sdk_version=99.0', 'OSPRODWin9.0.0')
    assert headers['sdk_version'] == '99.0' and query.startswith('?version=OSPRODWin9.0.0')
    for suffix in ('&host=other', '&cookie=value', '&version=duplicate', '&bad-name=value'):
        with pytest.raises(ValueError):
            live._query('?version={0}' + suffix, 'OSPRODWin9.0.0')


@pytest.mark.parametrize('path', ['../outside.blk', '/absolute.blk', 'Blocks/1.blk?x', 'Blocks/../1.blk'])
def test_current_inventory_rejects_escaped_or_unbounded_paths(tmp_path, monkeypatch, path):
    body = inventory([row(path, b'fixture')])
    build = snapshot(2000, {'design': body})
    monkeypatch.setattr(live, '_request', lambda *_: body)
    with pytest.raises(ValueError):
        live.rows(tmp_path, build, 'design')


def test_metadata_inventory_checks_every_original_base_and_uses_the_selected_patch(tmp_path, monkeypatch):
    base_data, changed = b'original baseline', b'changed tables'
    bodies = {'design': inventory([row('Blocks/Data/1.blk', base_data, False), row('Blocks/Data/2.blk', changed)]),
              'catalog': inventory([row('Blocks/3.blk', b'catalogue')])}
    build = snapshot(2000, bodies)
    sources = {live.BASE + name: Source(live.BASE + name, b'1000') for name in
               ('audio_revision', 'data_revision', 'res_revision', 'silence_revision')}
    sources[live.BASE + 'Blocks/Data/1.blk'] = Source(live.BASE + 'Blocks/Data/1.blk', base_data)
    def request(url, headers, maximum):
        if url.endswith('/data_version'):
            return bodies['design']
        if url.endswith('/res_version'):
            return bodies['catalog']
        return changed if url.endswith('/2.blk') else b'catalogue'
    monkeypatch.setattr(live, '_request', request)
    files, _ = live.metadata_files(tmp_path, build, sources)
    assert files[live.BASE + 'Blocks/Data/2.blk'].read(tmp_path, 1, 4) == changed[1:5]
    source = files[live.BASE + 'Blocks/Data/1.blk']
    assert source.read(tmp_path, 0, len(base_data)) == base_data
    live._verified_base.cache_clear()
    sources[live.BASE + 'Blocks/Data/1.blk'].data = b'corrupt baseline'
    with pytest.raises(ValueError):
        source.read(tmp_path, 0, 4)
    sources[live.BASE + 'audio_revision'].data = b'9999'
    with pytest.raises(ValueError):
        live.metadata_files(tmp_path, build, sources)


def test_full_original_checksum_precedes_cache_publication_and_offline_reads(tmp_path, monkeypatch):
    original = b'owned full asset'
    file = live.File(live.PERSISTENT + 'Blocks/4.blk', len(original), xxhash64(original),
                     'https://autopatchos.zenlesszonezero.com/game_res/9.0_live/output_2000_abcdef/client/StandaloneWindows64/oversea/Blocks/4.blk')
    monkeypatch.setattr(live, '_request', lambda *_: b'x' * len(original))
    with pytest.raises(ValueError):
        file.read(tmp_path, 0, 4)
    assert not list((tmp_path / 'zzz-files').iterdir())
    monkeypatch.setattr(live, '_request', lambda *_: original)
    assert file.read(tmp_path, 3, 4) == original[3:7]
    monkeypatch.setattr(live, '_request', lambda *_: pytest.fail('network used offline'))
    assert file.read(tmp_path, 0, len(original)) == original
    cached, = (tmp_path / 'zzz-files').iterdir()
    cached.write_bytes(b'x' * len(original))
    with pytest.raises(pytest.fail.Exception):
        file.read(tmp_path, 0, 4)


def test_authoritative_audio_inventory_excludes_removed_packages_and_other_dubs(tmp_path, monkeypatch):
    rows = [row('Audio/Windows/Full/En/current.pck', b'base', False),
            row('Audio/Windows/Full/En/Patch.pck', b'update'),
            row('Audio/Windows/Full/Jp/Patch.pck', b'other dub'),
            row('Audio/Windows/Full/Patch.pck', b'common')]
    body = inventory(rows)
    build = snapshot(2000, {'audio': body})
    prefix = live.BASE + 'Audio/Windows/Full/En/'
    base = {prefix + name: Source(prefix + name, b'base') for name in ('current.pck', 'removed.pck')}
    game = {live.BASE + name: Source(live.BASE + name, b'1000') for name in
            ('audio_revision', 'data_revision', 'res_revision', 'silence_revision')}
    monkeypatch.setattr(sophon_assets, 'manifest', lambda *_: game)
    monkeypatch.setattr(live, '_request', lambda *_: body)
    result = live.voice_files(tmp_path, build, 'en', base)
    assert set(result) == {prefix + 'current.pck', live.PERSISTENT + 'Audio/Windows/Full/En/Patch.pck',
                           live.PERSISTENT + 'Audio/Windows/Full/Patch.pck'}


def test_optional_base_block_uses_its_own_base_generation_not_the_patch_root(tmp_path, monkeypatch):
    raw = b'optional original'
    body = inventory([row('Blocks/44.blk', raw, False)])
    build = snapshot(2000, {'catalog': body})
    asset = live.resource(build, json.loads(body)['files'][0])
    assert '/output_1000_abcdef/' in asset.url and '/output_2000_' not in asset.url
    assert asset.name == live.BASE + 'Blocks/44.blk'
    monkeypatch.setattr(live, '_request', lambda *_: raw)
    assert asset.read(tmp_path, 1, 4) == raw[1:5]


def test_mainland_never_accepts_global_roots_or_dispatchers():
    global_build = snapshot(2000, {})
    for kind, root in global_build['hotfix']['roots'].items():
        with pytest.raises(ValueError):
            live._cdn(root.removesuffix('StandaloneWindows64/oversea/'), kind, '9.0.0', 'zzz-cn')
    with pytest.raises(ValueError):
        live._endpoint('https://globaldp-prod-os01.zenlesszonezero.com/query_dispatch', channel='zzz-cn')
    with pytest.raises(ValueError):
        live._endpoint('https://prod-gf-jp.zenlesszonezero.com/query_gateway', gateway=True, channel='zzz-cn')


def test_same_launcher_release_adopts_changed_text_and_voice_and_retains_old_recording_offline(tmp_path, monkeypatch):
    source = 'English(EN)/ex/VO_Message/Actor/Message_Sentence.wem'
    def archive(tag):
        clip = b'RIFF' + struct.pack('<I', 5) + b'WAVE' + tag.encode()
        header = b'AKPK' + struct.pack('<6I', 48, 1, 0, 0, 0, 28)
        return header + struct.pack('<IQ4I', 1, voice_hash(source), 1, len(clip), 56, 0) + clip
    versions = {}
    responses = {}
    for revision, tag in [(2000, 'a'), (3000, 'b')]:
        media = archive(tag)
        body = inventory([row('Audio/Windows/Full/En/Patch.pck', media)])
        build = snapshot(revision, {'audio': body})
        versions[tag] = build
        root = build['hotfix']['roots']['resource']
        responses[root + 'audio_version'] = body
        responses[root + 'Audio/Windows/Full/En/Patch.pck'] = media
    current = ['a']
    monkeypatch.setattr(sophon_assets, 'release', lambda _: {k: v for k, v in versions['a'].items() if k != 'hotfix'})
    monkeypatch.setattr(live, 'discover', lambda _: versions[current[0]])
    def manifest(_cache, _channel, spec, _suffixes):
        if spec == ('en',):
            return {}
        return {live.BASE + name: Source(live.BASE + name, b'1000') for name in
                ('audio_revision', 'data_revision', 'res_revision', 'silence_revision')}
    monkeypatch.setattr(sophon_assets, 'manifest', manifest)
    monkeypatch.setattr(live, '_request', lambda url, *_: responses[url])
    def catalogue(build, _directory, _locales, _namespace, _progress):
        return ([{'text_id': 'sentence', 'source': 'VO_Message/Actor/Message_Sentence', 'dialogue_kind': 'message'}],
                {'en': {'sentence': 'Text ' + current[0]}}, {}, None, {})
    monkeypatch.setattr(zzz_publisher, '_read_catalogue', catalogue)
    snapshots = []
    for tag in ('a', 'b'):
        current[0] = tag
        target = tmp_path / ('prepared-' + tag + '.json')
        language_worker.build('zzz', None, tmp_path, 'en', (), target)
        snapshots.append(json.loads(target.read_bytes()))
    assert snapshots[0]['fingerprint'] != snapshots[1]['fingerprint']
    assert snapshots[0]['records'][0]['texts']['en'] == 'Text a'
    assert snapshots[1]['records'][0]['texts']['en'] == 'Text b'
    voice._files.cache_clear()
    voice._table.cache_clear()
    monkeypatch.setattr(live, '_request', lambda *_: pytest.fail('network used after restart'))
    monkeypatch.setattr(sophon_assets, 'release', lambda _: pytest.fail('discovery used for historical audio'))
    for tag, prepared in zip(('a', 'b'), snapshots):
        audio = prepared['records'][0]['audio']
        assert zzz_assets.extract_voice(None, audio, tmp_path / 'tools', None).endswith(tag.encode())
        assert voice.snapshot_available(tmp_path / 'tools', prepared['fingerprint'], 'zzz')
        with pytest.raises(ValueError):
            zzz_assets.extract_voice(None, {**audio, 'locale': 'ja'}, tmp_path / 'tools', None)


def test_mainland_hant_keeps_its_own_text_dub_and_missing_translation_after_region_switch(tmp_path, monkeypatch):
    from backend.publisher_regions import select_region
    from backend.hoyo_dialogue import voice_namespace
    builds, responses = {}, {}
    for channel, dub, folder, tag in [('zzz-global', 'en', 'En', 'a'), ('zzz-cn', 'zh-Hans', 'Cn', 'b')]:
        source = voice_namespace('zzz', dub) + '/ex/VO_Message/Actor/Message_Sentence.wem'
        clip = b'RIFF' + struct.pack('<I', 5) + b'WAVE' + tag.encode()
        media = b'AKPK' + struct.pack('<6I', 48, 1, 0, 0, 0, 28) + struct.pack('<IQ4I', 1, voice_hash(source), 1, len(clip), 56, 0) + clip
        body = inventory([row('Audio/Windows/Full/' + folder + '/Patch.pck', media)])
        builds[channel] = snapshot(2000, {'audio': body}, channel)
        builds[channel]['manifests']['zh-cn'] = ['zh-cn']
        root = builds[channel]['hotfix']['roots']['resource']
        responses[root + 'audio_version'] = body
        responses[root + 'Audio/Windows/Full/' + folder + '/Patch.pck'] = media
    monkeypatch.setattr(sophon_assets, 'release', lambda channel: {k: v for k, v in builds[channel].items() if k != 'hotfix'})
    monkeypatch.setattr(live, 'discover', lambda build: builds[build['channel']])
    def manifest(_cache, _channel, spec, _suffixes):
        if spec != ('game',):
            return {}
        return {live.BASE + name: Source(live.BASE + name, b'1000') for name in
                ('audio_revision', 'data_revision', 'res_revision', 'silence_revision')}
    monkeypatch.setattr(sophon_assets, 'manifest', manifest)
    monkeypatch.setattr(live, '_request', lambda url, *_: responses[url])
    def catalogue(build, _directory, locales, namespace, _progress):
        cn = build['channel'] == 'zzz-cn'
        assert namespace == ('Chinese(PRC)' if cn else 'English(EN)')
        assert locales == ({'zh-Hant', 'en'} if cn else {'en'})
        return ([{'text_id': 'sentence', 'source': 'VO_Message/Actor/Message_Sentence', 'dialogue_kind': 'message'}],
                {'zh-Hant': {'sentence': '繁體測試'}} if cn else {'en': {'sentence': 'Owned Global text'}}, {}, None, {})
    monkeypatch.setattr(zzz_publisher, '_read_catalogue', catalogue)
    snapshots = []
    for region, locale in [('global', 'en'), ('cn', 'zh-Hant')]:
        select_region(tmp_path / 'tools', 'zzz', region)
        output = tmp_path / (region + '.json')
        language_worker.build('zzz', None, tmp_path, locale, ('en',) if region == 'cn' else (), output)
        snapshots.append(json.loads(output.read_bytes()))
    cn = snapshots[1]
    assert cn['publisher_region'] == 'cn' and cn['source_locale'] == 'zh-Hant'
    assert cn['records'][0]['texts'] == {'zh-Hant': '繁體測試'}
    assert cn['records'][0]['audio_locale'] == 'zh-Hans' and cn['records'][0]['voice_status'] == 'voiced'
    assert cn['missing_translation_locales'] == ['en'] and 'zh-Hant' in zzz_assets.SUPPORTED_LOCALES
    assert cn['fingerprint'] != snapshots[0]['fingerprint']
    voice._files.cache_clear();voice._table.cache_clear();live._verified_file.cache_clear()
    monkeypatch.setattr(live, '_request', lambda *_: pytest.fail('network used offline'))
    monkeypatch.setattr(sophon_assets, 'release', lambda *_: pytest.fail('discovery used for old region'))
    for prepared, tag in zip(snapshots, ('a', 'b')):
        assert zzz_assets.extract_voice(None, prepared['records'][0]['audio'], tmp_path / 'tools', None).endswith(tag.encode())
