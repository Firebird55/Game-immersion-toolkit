"""Owned key rotations exercise the real original-manifest and receipt path."""
import hashlib
import io
import json
import struct
from types import SimpleNamespace
from zipfile import ZipFile, BadZipFile
import zlib

from Crypto.Cipher import AES
import pytest

from backend import nte_community_metadata as community
from backend import nte_publisher as publisher, nte_release as release


OLD = bytes(range(65, 81))
NEW = bytes(range(97, 113))
IV = b'fixture-iv-value'


def source(key=NEW):
    return b'let key = b"' + key + b'";\nlet iv = b"' + IV + b'";\n'


def xml(version='9.0.1'):
    return (f'<ResList version="{version}" tag="baseTag">'
            '<Res filename="Client/WindowsNoEditor/HT/Content/owned.pak" filesize="64" '
            f'md5="{hashlib.md5(b"owned archive").hexdigest()}"/>'
            '<Res filename="Client/Original.exe" filesize="128" '
            f'md5="{hashlib.md5(b"owned native").hexdigest()}"/></ResList>').encode()


def archive(data, key=NEW):
    header = bytearray(16)
    header[:12] = b'PatcherXML0\0'
    struct.pack_into('<I', header, 12, len(data))
    packed = zlib.compress(data)
    encrypted = AES.new(key, AES.MODE_CBC, IV).encrypt(packed.ljust((len(packed)+15)//16*16, b'\0'))
    stream = io.BytesIO()
    with ZipFile(stream, 'w') as out:
        out.writestr('ResList.bin', header + encrypted)
    return stream.getvalue()


def fixture(monkeypatch, *, key=NEW, data=None, description=None):
    data = xml() if data is None else data
    packed = archive(data, key)
    cfg = (f'<Config><ResVersion>9.0.1</ResVersion><Extra><listHash>'
           f'{hashlib.md5(data).hexdigest()}</listHash></Extra></Config>').encode()
    official, external = [], []
    def original(url, *, limit):
        official.append(url)
        if '/publish_PC/' in url and url.endswith('/config.xml'):
            import base64
            target = base64.b64encode(b'{\"branchName\":\"PC_9\"}').decode()
            return f'<Config><ResConfig>{target}</ResConfig></Config>'.encode()
        assert url.startswith('https://ntecdn1.perfectworld.com/clientRes/')
        return cfg if url.endswith('/config.xml') else packed
    def candidate(url, limit):
        external.append(url)
        if url.startswith('https://api.github.com/repos/Tobiichi-Origuchi/nte_patcher/commits?'):
            return json.dumps([{'sha': 'a'*40}]).encode()
        assert url == ('https://raw.githubusercontent.com/Tobiichi-Origuchi/nte_patcher/'
                       + 'a'*40 + '/tests/test_integration.rs')
        return source() if description is None else description
    monkeypatch.setattr(release, 'download', original)
    monkeypatch.setattr(release, '_parameters', lambda _: (OLD, IV))
    monkeypatch.setattr(community, 'download', candidate)
    return data, official, external


def test_healthy_primary_never_refreshes_community_metadata(tmp_path, monkeypatch):
    _, _, external = fixture(monkeypatch, key=OLD)
    output = {}
    result = release.discover('nte-global', community_cache=tmp_path, metadata_out=output)
    assert result[1] == '9.0.1' and external == [] and output == {}
    assert list(tmp_path.rglob('*')) == []


def test_rotated_updater_key_is_original_verified_immutable_and_reused_offline(tmp_path, monkeypatch):
    data, _, external = fixture(monkeypatch)
    output = {}
    result = release.discover('nte-global', community_cache=tmp_path, metadata_out=output,
                              allow_community_fallback=True)
    assert len(external) == 2 and '/refs/heads/' not in external[-1]
    assert output['source'] == {'family': 'updater-global', 'revision': 'a'*40,
                                'sha256': hashlib.sha256(source()).hexdigest()}
    with ZipFile(io.BytesIO(archive(data))) as original:
        assert output['original']['sha256'] == hashlib.sha256(original.read('ResList.bin')).hexdigest()
    receipt = {key: output[key] for key in ('source', 'proof_sha256')}
    proof = community.check_receipt(receipt, output['original'], tmp_path)
    assert proof['verification']['sha256'] == hashlib.sha256(release._json_manifest((result[2], result[3]['ResList.bin']))).hexdigest()
    monkeypatch.setattr(community, 'download', lambda *_: pytest.fail('Verified source cache queried latest'))
    again = {}
    assert release.discover('nte-global', community_cache=tmp_path, metadata_out=again,
                            allow_community_fallback=True) == result
    assert again == output
    before = {p: p.read_bytes() for p in tmp_path.rglob('*.json')}
    with pytest.raises(ValueError):
        community.check_receipt(receipt, {**output['original'], 'region': 'nte-cn'}, tmp_path)
    assert {p: p.read_bytes() for p in before} == before


@pytest.mark.parametrize('failure', ['wrong-key', 'duplicate-key', 'version', 'timeout', 'corrupt-zip'])
def test_bad_candidates_or_original_acquisition_never_publish_a_proof(tmp_path, monkeypatch, failure):
    data = xml('9.0.2') if failure == 'version' else None
    description = source(OLD) if failure == 'wrong-key' else source()+source() if failure == 'duplicate-key' else None
    _, _, external = fixture(monkeypatch, data=data, description=description)
    if failure == 'timeout':
        monkeypatch.setattr(release, 'download', lambda *_a, **_k: (_ for _ in ()).throw(TimeoutError('owned timeout')))
    if failure == 'corrupt-zip':
        monkeypatch.setattr(release, 'download', lambda url, **_: b'<Config><ResVersion>9.0.1</ResVersion></Config>'
                            if url.endswith('/config.xml') else b'bad original ZIP')
    with pytest.raises((ValueError, TimeoutError, OSError, BadZipFile)):
        release.discover('nte-global', community_cache=tmp_path, metadata_out={}, allow_community_fallback=True)
    assert not list(tmp_path.glob('proofs/**/*.json'))
    if failure in ('timeout', 'corrupt-zip'):
        assert external == []


def test_historical_source_rejects_substitution_and_arbitrary_repository(tmp_path):
    retained = {'family': 'updater-global', 'revision': 'a'*40, 'sha256': hashlib.sha256(source()).hexdigest()}
    community.load('updater-global', tmp_path, retained=retained, fetch=lambda *_: source())
    assert community.load('updater-global', tmp_path, retained=retained,
                          fetch=lambda *_: pytest.fail('Historical source queried network')).data == source()
    with pytest.raises(ValueError):
        community.load('other-repository', tmp_path)
    with pytest.raises(ValueError):
        community.load('updater-cn', tmp_path, retained=retained)
    (tmp_path/'sources/updater-global'/(retained['sha256']+'.data')).write_bytes(source(OLD))
    with pytest.raises(ValueError):
        community.load('updater-global', tmp_path, retained=retained, fetch=lambda *_: source(OLD))


@pytest.mark.parametrize('response', [b'[{"sha":"'+b'a'*40+b'","sha":"'+b'b'*40+b'"}]',
                                      b'[]', b'[{"sha":"main"}]', b' '* (community.LIMIT+1)],
                         ids=['duplicate-commit', 'empty', 'branch-name', 'oversized'])
def test_unbounded_or_ambiguous_commit_discovery_is_rejected(tmp_path, response):
    with pytest.raises(ValueError):
        community.load('updater-global', tmp_path, fetch=lambda *_: response)
    assert not list(tmp_path.rglob('*'))


def test_cn_candidate_uses_its_own_allowlisted_source_and_original_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(release, '_parameters', lambda _: (OLD, IV))
    description = b'iv = b"'+IV+b'"\ndecode_patcherxml0(raw, "'+NEW+b'")\n'
    requests = []
    def fetch(url, limit):
        requests.append(url)
        if url.startswith('https://api.github.com/repos/kuaichu/game-cdn-archive/commits?'):
            return json.dumps([{'sha': 'b'*40}]).encode()
        assert url == ('https://raw.githubusercontent.com/kuaichu/game-cdn-archive/'
                       + 'b'*40 + '/scripts/nte_downloader.py')
        return description
    monkeypatch.setattr(community, 'download', fetch)
    out = {}
    result = release._manifest(archive(xml()), 'nte-cn', 'PC_9', '9.0.1', {},
                               hashlib.md5(xml()).hexdigest(), tmp_path, out, allow_community_fallback=True)
    assert result[0] and len(requests) == 2
    assert out['source']['family'] == 'updater-cn' and out['original']['region'] == 'nte-cn'
    wrong = community.Candidate({'family': 'updater-global', 'revision': 'a'*40,
                                'sha256': hashlib.sha256(source()).hexdigest()}, source())
    with pytest.raises(ValueError):
        community.remember(wrong, out['original'], 'publisher-manifest', b'owned verified bytes', tmp_path)


def test_optin_research_recipe_binds_fallback_and_final_discovery_reuses_it(tmp_path, monkeypatch):
    fixture(monkeypatch)
    # Follow the original branch redirect rather than assuming publish_PC is final.
    actual = release.download
    def download(url, *, limit):
        if '/publish_PC/' in url and url.endswith('/config.xml'):
            import base64
            target = base64.b64encode(b'{"branchName":"PC_9"}').decode()
            return f'<Config><ResConfig>{target}</ResConfig></Config>'.encode()
        return actual(url, limit=limit)
    monkeypatch.setattr(release, 'download', download)
    monkeypatch.setattr(publisher, '_reader_identity', lambda: 'f'*64)
    monkeypatch.setattr(publisher.metadata, 'load', lambda **_: SimpleNamespace(revision='b'*40, digest='c'*64))
    monkeypatch.setattr(publisher.metadata, 'load_localization', lambda **_: SimpleNamespace(revision='d'*40, digest='e'*64))
    publisher._current.cache_clear()
    try:
        stamp, value = publisher._current(tmp_path, 1, 'nte-global', True)
        assert value['updater_metadata']['source']['family'] == 'updater-global'
        assert publisher.snapshot(tmp_path, stamp) == value
        monkeypatch.setattr(community, 'download', lambda *_: pytest.fail('Current source proof should be reused'))
        assert publisher._discovery('nte-global', parameter_cache=tmp_path/'nte-publisher/format/community',
                                    allow_community_fallback=True)['updater_metadata'] == value['updater_metadata']
        original = publisher._path(tmp_path, stamp).read_bytes()
        # Retained playback/source lookup reads the immutable recipe, not discovery.
        monkeypatch.setattr(release, 'download', lambda *_a, **_k: pytest.fail('Historical recipe performed discovery'))
        assert publisher.snapshot(tmp_path, stamp)['updater_metadata'] == value['updater_metadata']
        assert publisher._path(tmp_path, stamp).read_bytes() == original
    finally:
        publisher._current.cache_clear()


def test_default_rotated_updater_never_skips_unresolved_official_key_route(tmp_path, monkeypatch):
    _, _, external = fixture(monkeypatch)
    with pytest.raises(release.UpdaterParameterMismatch):
        release.discover('nte-global', community_cache=tmp_path, metadata_out={})
    assert external == [] and list(tmp_path.rglob('*')) == []
