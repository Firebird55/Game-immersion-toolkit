"""Normal Genshin updates must retain exact regional resources and old audio offline."""
import base64
import hashlib
import io
import json
import os
import struct
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from backend import genshin_hotfix as hotfix, genshin_publisher as publisher, hoyo_publisher_voice as voices
from backend.preparation_errors import PreparationFailure
from backend.tests.test_sophon_assets import field, fixture


def md5(raw):
    return hashlib.md5(raw).hexdigest()


def listing(name, raw, patch=None):
    row = {'remoteName': name, 'md5': md5(raw), 'fileSize': len(raw)}
    if patch is not None:
        row['isPatch'] = patch
    return row


def response(build, objects, *, revision=10, design=b'current text', resource=b'current resources'):
    region = 'global' if build['channel'] == 'genshin-global' else 'cn'
    branch = '.'.join(build['version'].split('.')[:2]) + '_live'
    game = f'https://{hotfix.HOSTS[region]}/client_game_res/{branch}'
    data = f'https://{hotfix.HOSTS[region]}/client_design_data/{branch}'
    base = b'2 bbbb'
    sources = {'res': resource, 'base': base, 'design': design, 'silence': b'silent text'}
    res = b''.join(field(k, v) for k, v in {1: revision, 5: b'abcd', 6: branch.encode(),
        3: '\n'.join(json.dumps(listing(name, sources[key])) for key, name in
                      [('res', 'res_versions_external'), ('base', 'base_revision')]).encode()}.items())
    encoded = {8: game.encode(), 9: data.encode(), 22: res, 14: revision, 26: b'cdef',
               18: 4, 27: b'eeee', 36: ('hk4e_global' if region == 'global' else 'hk4e_cn').encode(),
               19: json.dumps(listing('data_versions', design)).encode(),
               20: json.dumps(listing('data_versions', sources['silence'])).encode()}
    urls = {'res': game + f'/output_{revision}_abcd/client/StandaloneWindows64/res_versions_external',
            'base': game + f'/output_{revision}_abcd/client/StandaloneWindows64/base_revision',
            'design': data + f'/output_{revision}_cdef/client/General/AssetBundles/data_versions',
            'silence': data + '/output_4_eeee/client_silence/General/AssetBundles/data_versions'}
    objects.update({urls[key]: raw for key, raw in sources.items()})
    return encoded


def test_same_version_design_and_voice_updates_change_snapshot_without_changing_code(tmp_path, monkeypatch):
    build = {'channel': 'genshin-global', 'version': '9.4.0', 'manifests': {'unchanged': 'same'}}
    objects = {}
    gateway = response(build, objects)
    monkeypatch.setattr(hotfix, '_dispatch', lambda *args: gateway)
    monkeypatch.setattr(hotfix.bootstrap, 'fetch', lambda url, **kwargs: objects[url])
    old = hotfix.discover(build)
    assert hotfix.index(tmp_path, old, 'design') == b'current text'
    gateway = response(build, objects, revision=11, design=b'updated sentence', resource=b'new audio listing')
    new = hotfix.discover(build)
    assert voices.descriptor(old)[0] != voices.descriptor(new)[0]
    assert new['manifests'] == old['manifests'] and new['version'] == old['version']
    assert new['hotfix']['revisions']['audio'] == (2, 'bbbb')
    assert '/output_2_bbbb/' in hotfix.roots(new)['audio']
    assert '/output_11_abcd/' in hotfix.roots(new)['res']
    assert hotfix.index(tmp_path, new, 'design') == b'updated sentence'
    monkeypatch.setattr(hotfix.bootstrap, 'fetch', lambda *a, **k: pytest.fail('Cached historical index went online'))
    assert hotfix.index(tmp_path, old, 'design') == b'current text'
    assert hotfix.index(tmp_path, new, 'design') == b'updated sentence'


@pytest.mark.parametrize('broken', ['hash', 'host', 'version', 'edition', 'base', 'duplicate', 'unknown-field-wire'])
def test_invalid_publisher_generation_cannot_replace_verified_index(tmp_path, monkeypatch, broken):
    build = {'channel': 'genshin-cn', 'version': '9.4.0'}
    objects = {}
    gateway = response(build, objects)
    monkeypatch.setattr(hotfix, '_dispatch', lambda *a: gateway)
    monkeypatch.setattr(hotfix.bootstrap, 'fetch', lambda url, **k: objects[url])
    old = hotfix.discover(build)
    hotfix.index(tmp_path, old, 'res')
    if broken == 'hash':
        objects[next(url for url in objects if url.endswith('/res_versions_external'))] = b'replaced'
    elif broken == 'host':
        gateway[8] = b'https://untrusted.example/client_game_res/9.4_live'
    elif broken == 'version':
        gateway[9] = gateway[9].replace(b'9.4_live', b'9.5_live')
    elif broken == 'edition':
        gateway[36] = b'hk4e_global'
    elif broken == 'base':
        gateway = response(build, objects)
        objects[next(url for url in objects if url.endswith('/base_revision'))] = b'0 bad'
    elif broken == 'duplicate':
        gateway[22] += field(1, 123)
    else:
        gateway[22] = b'\x0d\x00\x00\x00\x00'
    with pytest.raises(ValueError):
        hotfix.discover(build)
    assert hotfix.index(tmp_path, old, 'res') == b'current resources'


def test_global_catalog_reuses_cn_only_with_identical_base_and_current_hotfix(monkeypatch, tmp_path):
    objects = {}
    build = {'channel': 'genshin-global', 'version': '9.4.0'}
    gateway = response(build, objects)
    monkeypatch.setattr(hotfix, '_dispatch', lambda *a: gateway)
    monkeypatch.setattr(hotfix.bootstrap, 'fetch', lambda url, **k: objects[url])
    build = hotfix.discover(build)
    cn = build | {'channel': 'genshin-cn'}
    monkeypatch.setattr(publisher, '_release', lambda region: cn)
    monkeypatch.setattr(publisher, '_narrative_payload', lambda *a: (('1', '2', '3'), {'original': (1, 'digest')}))
    def find(game, title):
        if title != 'CNRELWin9.4.0_R10_S4_D10':
            raise PreparationFailure('publisher_unavailable', 'No Global catalog')
        return 'a' * 40
    monkeypatch.setattr(publisher, 'matching_release_commit', find)
    assert publisher._catalog(tmp_path, build, 'global') == 'a' * 40
    cn = cn | {'hotfix': {**cn['hotfix'], 'indexes': {**cn['hotfix']['indexes'], 'design': ('f' * 32, 1)}}}
    with pytest.raises(PreparationFailure, match='Global'):
        publisher._catalog(tmp_path, build, 'global')


def test_regional_bootstrap_uses_its_own_keys_and_public_account_zero(monkeypatch):
    key = RSA.generate(1024)
    numbers = key.n, key.e, key.d, key.p, key.q
    xml = '<RSAKeyValue>' + ''.join('<' + name + '>' + base64.b64encode(value.to_bytes((value.bit_length()+7)//8, 'big')).decode() + '</' + name + '>'
        for name, value in zip(('Modulus', 'Exponent', 'D', 'P', 'Q'), numbers)) + '</RSAKeyValue>'
    template = 'https://cngfdispatch.yuanshen.com/query_cur_region?version={1}&lang=2&platform=3&binary=1&time=561&channel_id=1&sub_channel_id=1&account_type=1&dispatchSeed={2}&key_id=4'
    decoder = SimpleNamespace(text=lambda value: template if value == 'template' else 'a' * 16,
                              decode=lambda value: xml.encode())
    config = {'GameDispatchURL': 'template', 'ProtoDispatchKey': 'seed', 'DispatcherKey': 'key',
              'DispatcherKeyBitLength': 128, 'ChannelID': 1, 'SubChannelID': 1}
    helper_source = {'game': 'genshin', 'region': 'cn', 'policy': 'immutable-community-hybrid',
        'repository': 'CollapseLauncher/CollapseLauncher-ReleaseRepo', 'revision': 'a' * 40,
        'files': {name: {'sha256': 'b' * 64, 'bytes': 128}
                  for name in ('config_master.json', 'config_GICN.json')}}
    config['_hoyo_bootstrap_provenance'] = helper_source
    monkeypatch.setattr(hotfix.bootstrap, 'load', lambda game, region: (config, decoder))
    plain = field(3, field(36, b'hk4e_cn'))
    cipher = PKCS1_v1_5.new(key.public_key())
    def fetch(url, **kwargs):
        q = parse_qs(urlsplit(url).query)
        assert q['account_type'] == ['0'] and q['key_id'] == ['4'] and q['sub_channel_id'] == ['1']
        assert q['version'] == ['CNRELWin9.4.0'] and not {'uid', 'token', 'aid'} & set(q)
        return json.dumps({'content': base64.b64encode(cipher.encrypt(plain)).decode(), 'sign': 'opaque'}).encode()
    monkeypatch.setattr(hotfix.bootstrap, 'fetch', fetch)
    result = hotfix._dispatch('cn', '9.4.0')
    assert result == {36: b'hk4e_cn'}
    if hasattr(hotfix.bootstrap, 'provenance'):
        assert result.helper_provenance == helper_source
    for other in ['http://cngfdispatch.yuanshen.com', 'https://cngfdispatch.yuanshen.com.evil.example']:
        altered = SimpleNamespace(text=lambda value: template.replace('https://cngfdispatch.yuanshen.com', other) if value == 'template' else 'a' * 16)
        with pytest.raises(ValueError):
            hotfix._query(config, altered, 'cn', '9.4.0')


def test_new_original_recording_overlay_exports_and_reopens_old_generation_offline(tmp_path, monkeypatch):
    source, identity, base_stamp, _, _ = fixture(tmp_path, monkeypatch, '9.4.0', b'base', channel='genshin-global')
    directory = tmp_path / 'tools/sophon'
    base = json.loads((directory / 'releases' / base_stamp).read_bytes())
    objects, packages, exported = {}, {}, []
    class Response(io.BytesIO):
        status = 200
        headers = {'ETag': '"opaque-publisher-tag-1"'}
        def geturl(self):
            return self.url
    def fetch(request, timeout):
        result = Response(packages[request.full_url]); result.url = request.full_url
        return result
    monkeypatch.setattr(hotfix, 'urlopen', fetch)
    for revision, speech in [(10, b'first updated original'), (11, b'replaced original')]:
        wem = b'RIFF' + struct.pack('<I', len(speech) + 4) + b'WAVE' + speech
        table = struct.pack('<I Q4I', 1, identity, 1, len(wem), 56, 0)
        package = b'AKPK' + struct.pack('<6I', 48, 1, 0, 0, 0, len(table)) + table + wem
        resource = json.dumps(listing('English(US)/new.pck', package, True)).encode()
        gateway = response(base, objects, revision=revision, resource=resource)
        monkeypatch.setattr(hotfix, '_dispatch', lambda *a: gateway)
        monkeypatch.setattr(hotfix.bootstrap, 'fetch', lambda url, **k: objects[url])
        build = hotfix.discover(base)
        stamp, raw = voices.descriptor(build)
        voices.sophon._atomic_file(directory / 'releases' / stamp, raw)
        hotfix.index(directory, build, 'res')
        packages[hotfix.roots(build)['res'] + 'AudioAssets/English(US)/new.pck'] = package
        entry = publisher.inventory(tmp_path, stamp, 'en')[identity]
        audio = entry | {'source': source, 'file_id': f'{identity:016x}', 'locale': 'en'}
        assert publisher.extract(audio, tmp_path / 'tools') == wem
        exported.append((audio, wem))
    assert exported[0][0]['publisher'] != exported[1][0]['publisher']
    voices._table.cache_clear(); voices._files.cache_clear(); hotfix._package_blocks.cache_clear()
    monkeypatch.setattr(hotfix, 'urlopen', lambda *a, **k: pytest.fail('An immutable cached original went online'))
    monkeypatch.setattr(hotfix.bootstrap, 'fetch', lambda *a, **k: pytest.fail('An immutable cached index went online'))
    for audio, wem in exported:
        assert publisher.extract(audio, tmp_path / 'tools') == wem


def test_verified_package_checks_each_read_even_when_size_and_mtime_are_preserved(tmp_path, monkeypatch):
    raw = b'0123456789abcdef' * 4
    path = tmp_path / 'genshin-packages' / md5(raw)
    path.parent.mkdir(); path.write_bytes(raw)
    asset = hotfix.AudioFile('voice', len(raw), md5(raw), 'https://publisher.example/')
    monkeypatch.setattr(hotfix, 'BLOCK', 16)
    assert asset.read(tmp_path, 12, 20) == raw[12:32]
    stat = path.stat()
    path.write_bytes(b'x' + raw[1:]); os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    monkeypatch.setattr(hotfix, 'urlopen', lambda *a, **k: pytest.fail('Tampered bytes caused an unrequested download'))
    with pytest.raises(ValueError):
        asset.read(tmp_path, 0, 4)


@pytest.mark.parametrize('failure', ['checksum', 'truncated', 'redirect'])
def test_unverified_package_never_becomes_a_playable_cached_recording(tmp_path, monkeypatch, failure):
    original = b'original package'
    asset = hotfix.AudioFile('voice', len(original), md5(original), 'https://publisher.example/immutable')
    class Response(io.BytesIO):
        status = 200
        headers = {'ETag': '"opaque-publisher-tag-1"'}
        def geturl(self):
            return 'https://untrusted.example/' if failure == 'redirect' else asset.url
    body = b'x' * len(original) if failure == 'checksum' else original[:-1] if failure == 'truncated' else original
    monkeypatch.setattr(hotfix, 'urlopen', lambda *a, **k: Response(body))
    with pytest.raises(ValueError):
        asset.read(tmp_path, 0, 4)
    assert not (tmp_path / 'genshin-packages' / asset.digest).exists()


def test_nonpatch_audio_and_changed_movies_follow_separate_base_revision(tmp_path, monkeypatch):
    build = {'channel': 'genshin-global', 'version': '9.4.0', 'hotfix': {
        'revisions': {'res': (10, 'aaaa'), 'audio': (2, 'bbbb'), 'design': (9, 'cccc'), 'silence': (8, 'dddd')}}}
    raw = b'file'
    rows = [listing('English(US)/base.pck', raw), listing('English(US)/patched.pck', raw, True),
            listing('StandaloneWindows64/Movie.usm', raw, True)]
    monkeypatch.setattr(hotfix, 'index', lambda *a: '\n'.join(json.dumps(r) for r in rows).encode())
    files = hotfix.files(tmp_path, build, 'en', {})
    assert '/output_2_bbbb/' in next(a.url for n, a in files.items() if n.endswith('/base.pck'))
    assert '/output_10_aaaa/' in next(a.url for n, a in files.items() if n.endswith('/patched.pck'))
    movie = hotfix.movie_files(tmp_path, build, {})['Movie']
    assert movie.url.endswith('/output_10_aaaa/client/StandaloneWindows64/VideoAssets/StandaloneWindows64/Movie.usm')
