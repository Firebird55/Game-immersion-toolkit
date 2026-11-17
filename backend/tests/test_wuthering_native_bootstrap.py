"""Official-source lifecycle controls with authored packages and mocked transport."""
import copy
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import struct
import zipfile
import zlib

import pytest
from Crypto.Hash import SHA256
from Crypto.PublicKey import RSA
from Crypto.Signature import pkcs1_15
from Crypto.Util.asn1 import DerSequence

from backend import wuthering_native_bootstrap as native
from backend import wuthering_metadata as metadata, wuthering_release as release, wuthering_release_pak as pak
from backend.preparation_errors import PreparationFailure
from backend.tests.test_wuthering_elf_bootstrap import original
from backend.tests.test_wuthering_metadata import protected, encrypted_package
from backend.tests.test_publisher_apk import lp, reference_digest


URL = 'https://owned.aki-game.com/client/download/original/game.apk'


def source(tmp_path, *, key=bytes(range(32)), base=0):
    directory = tmp_path / ('fixture-' + str(base))
    directory.mkdir(exist_ok=True)
    path, sha = original(directory, base=base, key=key)
    raw = path.read_bytes()
    value = dict(policy=native.POLICY, catalogue=native.CATALOGUE, catalogue_sha256='1' * 64,
                 version='1.0.0', url=URL, bytes=1_000_000, etag='"authored"', apk_sha256='2' * 64,
                 v2_digest='3' * 64, signers=['4' * 64], module=dict(name='lib/arm64-v8a/libUE4.so',
                 sha256=sha, compressed_sha256='5' * 64, compressed_bytes=1000, plain_bytes=len(raw),
                 crc32=f'{zlib.crc32(raw) & 0xffffffff:08x}'))
    return value, raw


def acquire(monkeypatch, value, raw):
    calls = []
    def get(tools, *args, **kwargs):
        calls.append(copy.deepcopy(value))
        target = native._module(tools, value)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        return copy.deepcopy(value)
    monkeypatch.setattr(native, '_acquire', get)
    monkeypatch.setattr(native, '_open', lambda *a, **k: pytest.fail('Unexpected network'))
    return calls


def owner(raw, label='archive'):
    return 'https://owned.aki-game.net/' + label + '.pak', len(raw), hashlib.md5(raw).hexdigest()


@pytest.mark.parametrize('owner_hash', ['md5', 'sha1'])
def test_native_only_default_is_verified_by_real_reader_and_never_becomes_legacy(tmp_path, monkeypatch, protected, owner_hash):
    ref, raw = source(tmp_path)
    calls = acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    info = owner(data)
    if owner_hash == 'sha1':
        info = info[0], info[1], hashlib.sha1(data).hexdigest()
    inputs = native.parameters(tmp_path, info)
    assert not inputs.bootstrap.verified and len(calls) == 1
    reads = []
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: (reads.append((at, n)) or bytes(data[at:at+n])))
    monkeypatch.setattr(metadata, 'default_parameters', lambda *a: pytest.fail('Legacy defaults read'))
    monkeypatch.setattr(release, '_archive_parameters', lambda *a, **k: pytest.fail('Initial seed read'))
    package = release._package(tmp_path, info, inputs)
    assert package.verified_default_parameter and inputs.bootstrap.verified
    assert len(reads) == 4 and package.locations(wanted={'Client/voices/a.wem'})
    assert not metadata._path(tmp_path, 'verified-parameters').exists()
    assert 'parameter' not in json.loads(metadata._read(native._registry_path(tmp_path)))
    restored = native.parameters(tmp_path, info)
    assert restored.bootstrap.verified and tuple(restored) == (bytes(range(32)),)
    assert len(calls) == 1


@pytest.mark.parametrize('digest', ['', 'a' * 64, 'g' * 40])
def test_owner_identity_must_use_the_actual_launcher_or_resource_checksum_format(digest):
    with pytest.raises(ValueError):
        native._owner(('https://owned.aki-game.net/a.pak', 1024, digest), 'global')


@pytest.mark.parametrize('damage', ['main', 'directory'])
def test_matching_mount_cannot_authorize_bad_full_indices_or_replace_prior_data(tmp_path, monkeypatch, protected, damage):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    data[128 + 40 if damage == 'main' else 512 + 20] ^= 1
    info = owner(data)
    inputs = native.parameters(tmp_path, info)
    marker = tmp_path / 'existing-study-index'
    marker.write_bytes(b'old complete library')
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data[at:at+n]))
    with pytest.raises(ValueError):
        release._package(tmp_path, info, inputs)
    assert not native._registry(tmp_path)['owners'] and not inputs.bootstrap.verified
    assert marker.read_bytes() == b'old complete library'


def test_original_default_never_authorizes_an_unrelated_nonzero_guid(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    magic = data.rfind(pak.MAGIC)
    data[magic - 17:magic - 1] = struct.pack('<4I', 1, 2, 3, 4)
    inputs = native.parameters(tmp_path, owner(data))
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data[at:at+n]))
    with pytest.raises(PreparationFailure) as failure:
        release._package(tmp_path, owner(data), inputs)
    assert failure.value.code == 'archive_parameters_missing'
    assert not native._registry(tmp_path)['owners']


def test_retained_source_a_survives_current_b_and_never_reads_current_seed(tmp_path, monkeypatch, protected):
    first, raw_a = source(tmp_path)
    calls = acquire(monkeypatch, first, raw_a)
    data_a = encrypted_package(bytes(range(32)))
    info_a = owner(data_a, 'a')
    a = native.parameters(tmp_path, info_a)
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data_a[at:at+n]))
    release._package(tmp_path, info_a, a)
    second, raw_b = source(tmp_path, key=bytes(range(32, 64)), base=0x100000)
    acquire(monkeypatch, second, raw_b)
    data_b = encrypted_package(bytes(range(32, 64)))
    info_b = owner(data_b, 'b')
    b = native.parameters(tmp_path, info_b, refresh=True)
    assert b.bootstrap.source != a.bootstrap.source
    monkeypatch.setattr(native, '_acquire', lambda *a, **k: pytest.fail('Retained A borrowed live source'))
    restored = native.parameters(tmp_path, info_a, retained=a.bootstrap.source)
    assert restored.bootstrap.verified and tuple(restored) == tuple(a)
    assert len(native._registry(tmp_path)['sources']) == 2
    assert not metadata._path(tmp_path, 'verified-parameters').exists()


@pytest.mark.parametrize('fault', ['envelope', 'module', 'reference'])
def test_corrupt_present_source_is_not_a_cold_miss_or_community_fallback(tmp_path, monkeypatch, protected, fault):
    ref, raw = source(tmp_path)
    calls = acquire(monkeypatch, ref, raw)
    info = owner(encrypted_package(bytes(range(32))))
    native.parameters(tmp_path, info)
    if fault == 'envelope':
        native._registry_path(tmp_path).write_bytes(b'broken')
    elif fault == 'module':
        native._module(tmp_path, ref).write_bytes(b'broken')
    else:
        record = native._registry(tmp_path)
        record['sources'][next(iter(record['sources']))]['policy'] = 'unowned'
        assert metadata._write(native._registry_path(tmp_path), json.dumps(record).encode())
    with pytest.raises(PreparationFailure) as failure:
        native.parameters(tmp_path, info)
    assert failure.value.code == 'publisher_bootstrap_cache_invalid'
    assert len(calls) == 1


def test_pending_protected_readback_failure_keeps_prior_source_owner_record(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    native.parameters(tmp_path, owner(encrypted_package(bytes(range(32)))))
    path = native._registry_path(tmp_path)
    before = path.read_bytes()
    record = native._registry(tmp_path)
    record['regions']['cn'] = next(iter(record['sources']))
    read = metadata._read
    monkeypatch.setattr(metadata, '_read', lambda p: None if str(p).endswith('.pending') else read(p))
    with pytest.raises(PreparationFailure) as failure:
        native._save(tmp_path, record)
    assert failure.value.code == 'publisher_key_cache_failed'
    assert path.read_bytes() == before
    assert not list(path.parent.glob('*.pending'))


def test_invalid_source_record_is_rejected_before_any_protected_write(tmp_path, monkeypatch, protected):
    monkeypatch.setattr(metadata, '_write', lambda *a: pytest.fail('Invalid provenance written'))
    with pytest.raises(ValueError):
        native._save(tmp_path, {'schema': 1, 'sources': {}, 'owners': {'foreign': 'missing'}, 'regions': {}})


def test_native_source_io_failure_is_not_reported_as_unsupported_format(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    info = owner(encrypted_package(bytes(range(32))))
    native.parameters(tmp_path, info)
    native._module(tmp_path, ref).unlink()
    with pytest.raises(PreparationFailure) as failure:
        native.parameters(tmp_path, info)
    assert failure.value.code == 'publisher_bootstrap_unavailable'


def test_parallel_source_owner_checks_serialize_without_losing_other_owners(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data[at:at+n]))
    infos = [owner(data, 'bootstrap-' + str(i)) for i in range(6)]
    def checked(info):
        inputs = native.parameters(tmp_path, info)
        release._package(tmp_path, info, inputs)
        return inputs.bootstrap.verified
    with ThreadPoolExecutor(max_workers=6) as pool:
        assert all(pool.map(checked, infos))
    record = native._registry(tmp_path)
    assert set(record['owners']) == {native._owner(info, 'global') for info in infos}
    assert len(record['sources']) == 1


def test_known_default_parallel_resource_scans_do_not_publish_bootstrap_owners(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    info = owner(data)
    inputs = native.parameters(tmp_path, info)
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data[at:at+n]))
    release._package(tmp_path, info, inputs)
    before = native._registry_path(tmp_path).read_bytes()
    monkeypatch.setattr(native, 'remember_owner', lambda *a: pytest.fail('Redundant resource bootstrap-owner publication'))
    resource_digest = hashlib.sha1(data).hexdigest()
    with ThreadPoolExecutor(max_workers=6) as pool:
        packages = list(pool.map(lambda i: release._package(tmp_path,
            ('https://owned.aki-game.net/resource-' + str(i) + '.pak', len(data), resource_digest), inputs), range(6)))
    assert all(p.verified_default_parameter for p in packages)
    assert native._registry_path(tmp_path).read_bytes() == before


def test_an_unproved_bootstrap_cannot_be_authorized_by_another_archive(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    inputs = native.parameters(tmp_path, owner(data, 'requested'))
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data[at:at+n]))
    with pytest.raises(ValueError):
        release._package(tmp_path, owner(data, 'other'), inputs)
    assert not inputs.bootstrap.verified and not native._registry(tmp_path)['owners']


def test_existing_exact_owner_does_not_rewrite_protected_state(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    info = owner(data)
    inputs = native.parameters(tmp_path, info)
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data[at:at+n]))
    release._package(tmp_path, info, inputs)
    monkeypatch.setattr(metadata, '_write', lambda *a: pytest.fail('Known owner rewritten'))
    native.remember_owner(tmp_path, inputs.bootstrap, info)


def test_normal_bootstrap_refresh_rederives_changed_output_and_preserves_a(tmp_path, monkeypatch, protected):
    first, raw_a = source(tmp_path)
    acquire(monkeypatch, first, raw_a)
    data_a = encrypted_package(bytes(range(32)))
    info_a = owner(data_a, 'a')
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data_a[at:at+n]))
    _, a = release._bootstrap_package(tmp_path, info_a, 'global')
    second, raw_b = source(tmp_path, key=bytes(range(32, 64)), base=0x100000)
    acquisitions = acquire(monkeypatch, second, raw_b)
    data_b = encrypted_package(bytes(range(32, 64)))
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data_b[at:at+n]))
    _, b = release._bootstrap_package(tmp_path, owner(data_b, 'b'), 'global')
    assert tuple(b) == (bytes(range(32, 64)),) and b.bootstrap.verified
    assert len(acquisitions) == 1
    assert native.parameters(tmp_path, info_a, retained=a.bootstrap.source).bootstrap.verified
    assert not metadata._path(tmp_path, 'verified-parameters').exists()


def test_failed_official_refresh_keeps_prior_owner_and_library(tmp_path, monkeypatch, protected):
    ref, raw = source(tmp_path)
    acquire(monkeypatch, ref, raw)
    data = encrypted_package(bytes(range(32)))
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(data[at:at+n]))
    release._bootstrap_package(tmp_path, owner(data, 'a'), 'global')
    before = native._registry_path(tmp_path).read_bytes()
    marker = tmp_path / 'prepared-library'
    marker.write_bytes(b'complete old index and original recording')
    changed = encrypted_package(bytes(range(32, 64)))
    monkeypatch.setattr(pak, 'block', lambda url, total, at, n: bytes(changed[at:at+n]))
    def unavailable(*a, **k):
        raise OSError('Original source temporarily unavailable')
    monkeypatch.setattr(native, '_acquire', unavailable)
    with pytest.raises(PreparationFailure) as failure:
        release._bootstrap_package(tmp_path, owner(changed, 'b'), 'global')
    assert failure.value.code == 'publisher_bootstrap_unavailable'
    assert native._registry_path(tmp_path).read_bytes() == before
    assert marker.read_bytes() == b'complete old index and original recording'


def manifest():
    values = ['manifest', 'package', 'com.kurogame.mingchao', 'application', 'activity', 'name',
              'com.epicgames.ue4.GameActivity', 'meta-data', 'android.app.lib_name', 'value', 'UE4',
              'http://schemas.android.com/apk/res/android']
    indices = {value: i for i, value in enumerate(values)}
    offsets, payload = [], b''
    for value in values:
        raw = value.encode()
        assert len(raw) < 128
        offsets.append(len(payload))
        payload += bytes((len(value), len(raw))) + raw + b'\0'
    pool = struct.pack('<HHI5I', 1, 28, 28 + len(values) * 4 + len(payload), len(values), 0, 256,
                       28 + len(values) * 4, 0) + struct.pack('<' + 'I' * len(values), *offsets) + payload
    def start(name, attrs=()):
        out = struct.pack('<HHI4I6H', 0x102, 16, 36 + len(attrs) * 20, 1, 0xffffffff, 0xffffffff,
                          indices[name], 20, 20, len(attrs), 0, 0, 0)
        for key, value in attrs:
            out += struct.pack('<IIIHBBI', indices[values[-1]] if key != 'package' else 0xffffffff,
                               indices[key], indices[value], 8, 0, 3, indices[value])
        return out
    def end(name):
        return struct.pack('<HHI4I', 0x103, 16, 24, 1, 0xffffffff, 0xffffffff, indices[name])
    body = (pool + start('manifest', [('package', 'com.kurogame.mingchao')]) + start('application') +
            start('activity', [('name', 'com.epicgames.ue4.GameActivity')]) +
            start('meta-data', [('name', 'android.app.lib_name'), ('value', 'UE4')]) +
            end('meta-data') + end('activity') + end('application') + end('manifest'))
    return struct.pack('<HHI', 3, 8, 8 + len(body)) + body


@pytest.fixture(scope='module')
def signing_key():
    return RSA.generate(2048)


def signed_game(module, key):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr('AndroidManifest.xml', manifest())
        archive.writestr('lib/arm64-v8a/libUE4.so', module)
        archive.writestr('assets/unretained.bin', b'not a real game asset')
    raw = output.getvalue()
    eocd = raw[-22:]
    size, offset = struct.unpack_from('<II', eocd, 12)
    body, cd = raw[:offset], raw[offset:offset + size]
    public = key.public_key().export_key(format='DER')
    tbs = DerSequence([1, b'\x30\x00', b'\x30\x00', b'\x30\x00', b'\x30\x00', public]).encode()
    certificate = DerSequence([tbs, b'\x30\x00', b'\x03\x01\x00']).encode()
    data = lp(lp(struct.pack('<I', 0x103) + lp(reference_digest([body, cd, eocd])))) + lp(lp(certificate)) + lp(b'') + bytes(4)
    signature = pkcs1_15.new(key).sign(SHA256.new(data))
    signer = lp(data) + lp(lp(struct.pack('<I', 0x103) + lp(signature))) + lp(public)
    value = lp(lp(signer))
    pair = struct.pack('<QI', len(value) + 4, 0x7109871a) + value
    size = len(pair) + 24
    block = struct.pack('<Q', size) + pair + struct.pack('<Q', size) + b'APK Sig Block 42'
    fixed = bytearray(eocd)
    struct.pack_into('<I', fixed, 16, offset + len(block))
    return body + block + cd + fixed


class Response(io.BytesIO):
    def __init__(self, raw, url, status=200, headers=None):
        super().__init__(raw)
        self.url, self.status, self.headers = url, status, headers or {}

    def geturl(self):
        return self.url


@pytest.mark.parametrize('corrupt_full_stream', [False, True])
def test_complete_original_source_pipeline_verifies_apk_manifest_member_and_output(
        tmp_path, monkeypatch, protected, signing_key, corrupt_full_stream):
    _, module = source(tmp_path)
    apk = signed_game(module, signing_key)
    catalogue = json.dumps({'primary': URL, 'version': '1.0.0'}).encode()
    full_reads = []
    def transport(url, *, method='GET', headers=None):
        if url.startswith(native.CATALOGUE + '?_t='):
            return Response(catalogue, url)
        assert url == URL
        if method == 'HEAD':
            return Response(b'', url, headers={'Content-Length': str(len(apk)), 'ETag': '"original"'})
        if (headers or {}).get('Range'):
            lo, hi = map(int, headers['Range'].removeprefix('bytes=').split('-'))
            return Response(apk[lo:hi + 1], url, 206, {'Content-Range': f'bytes {lo}-{hi}/{len(apk)}', 'ETag': '"original"'})
        full_reads.append(url)
        value = bytearray(apk)
        if corrupt_full_stream:
            value[-23] ^= 1  # Outside the selected member; whole APK digest still must fail.
        return Response(bytes(value), url, headers={'Content-Length': str(len(apk)), 'ETag': '"original"'})
    monkeypatch.setattr(native, '_open', transport)
    info = owner(encrypted_package(bytes(range(32))))
    if corrupt_full_stream:
        with pytest.raises(PreparationFailure):
            native.parameters(tmp_path, info)
        assert not native._registry_path(tmp_path).exists()
        assert not list(native._root(tmp_path).glob('pending-*'))
    else:
        result = native.parameters(tmp_path, info)
        assert tuple(result) == (bytes(range(32)),)
        assert result.bootstrap.source['apk_sha256'] == hashlib.sha256(apk).hexdigest()
        assert native._module(tmp_path, result.bootstrap.source).read_bytes() == module
        assert not list(native._root(tmp_path).rglob('*.apk'))
        assert not list(native._root(tmp_path).rglob('*.deflate'))
    assert len(full_reads) == 1
