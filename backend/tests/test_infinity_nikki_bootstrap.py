import base64
import hashlib
import json
import struct
import zlib

import pytest

from backend import infinity_nikki_bootstrap as bootstrap


def deflate(raw):
    encoder = zlib.compressobj(wbits=-15)
    return encoder.compress(raw) + encoder.flush()


def nsis_fixture(names=('xstarter.exe', 'libnetwork.dll')):
    strings = bytearray()
    entries = bytearray()
    for index, name in enumerate(names):
        offset = len(strings) // 2
        strings.extend(name.encode('utf-16-le') + b'\0\0')
        entries.extend(struct.pack('<7i', 20, 0, offset, 1000 + index * 100, 0, 0, 0))
    header = bytearray(68)
    struct.pack_into('<II', header, 20, len(header), len(names))
    struct.pack_into('<II', header, 28, len(header) + len(entries), 0)
    struct.pack_into('<II', header, 36, len(header) + len(entries) + len(strings), 0)
    return bytes(header + entries + strings)


def frame(raw, packed, compressed):
    return (struct.pack('<I', 0) + b'\xef\xbe\xad\xdeNullsoftInst' +
            struct.pack('<III', len(raw), 4096 + len(packed), len(packed) | (0x80000000 if compressed else 0)))


@pytest.mark.parametrize('compressed', [True, False])
def test_named_members_follow_new_unicode_header_offsets_without_executing_script(compressed):
    header = nsis_fixture()
    packed = deflate(header) if compressed else header
    prefix = frame(header, packed, compressed)
    assert bootstrap.nsis_header_plan(prefix).data_offset == 32 + len(packed)
    owned = bootstrap.decode_nsis_header(prefix, packed)
    assert bootstrap.nsis_member_offsets(owned, ('xstarter.exe', 'libnetwork.dll')) == {
        'xstarter.exe': 1000, 'libnetwork.dll': 1100}


@pytest.mark.parametrize('case', ['duplicate', 'missing', 'string-offset', 'entry-count', 'negative-data'])
def test_nsis_index_refuses_ambiguous_or_outside_source_records(case):
    raw = bytearray(nsis_fixture(('xstarter.exe', 'xstarter.exe') if case == 'duplicate' else ('xstarter.exe',)))
    if case == 'missing': raw = bytearray(nsis_fixture(('other.exe',)))
    if case == 'string-offset': struct.pack_into('<i', raw, 68 + 8, 10000)
    if case == 'entry-count': struct.pack_into('<I', raw, 24, 100000)
    if case == 'negative-data': struct.pack_into('<i', raw, 68 + 12, -1)
    with pytest.raises(ValueError):
        bootstrap.nsis_member_offsets(bytes(raw))


def test_archive_member_bounds_check_full_deflate_eof_and_refuse_solid_or_trailing_data(monkeypatch):
    payload = b'MZ' + b'own non-executable fixture' * 10
    packed = deflate(payload)
    block = struct.pack('<I', len(packed) | 0x80000000) + packed
    assert bootstrap.decode_nsis_member(block) == payload
    assert bootstrap.decode_nsis_member(struct.pack('<I', len(payload)) + payload) == payload
    for broken in (block[:-1], block + b'other', struct.pack('<I', len(packed) + 1 | 0x80000000) + packed + b'x'):
        with pytest.raises(ValueError): bootstrap.decode_nsis_member(broken)
    monkeypatch.setattr(bootstrap, 'MAX_MEMBER', 32)
    with pytest.raises(ValueError): bootstrap.decode_nsis_member(block)


def test_pe_prefix_plans_only_the_nsis_overlay_and_rejects_outside_or_truncated_sections():
    raw = bytearray(512)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 60, 64)
    raw[64:68] = b'PE\0\0'
    struct.pack_into('<H', raw, 70, 1)
    struct.pack_into('<H', raw, 84, 2)
    struct.pack_into('<H', raw, 88, 0x10b)
    struct.pack_into('<II', raw, 90 + 16, 1024, 512)
    assert bootstrap.nsis_overlay_offset(bytes(raw), 4096) == 1536
    with pytest.raises(ValueError): bootstrap.nsis_overlay_offset(bytes(raw[:100]), 4096)
    struct.pack_into('<II', raw, 90 + 16, 4096, 512)
    with pytest.raises(ValueError): bootstrap.nsis_overlay_offset(bytes(raw), 4096)


def resource_fixture():
    from Crypto.Cipher import AES
    identity = b'\xef\xbb\xbf' + json.dumps({'launcherAppId': '12345', 'version': '9.2.7',
                                              'time': '2026-02-03 04:05:06'}).encode()
    body = json.dumps({'appConfig': {'fixture': True}, 'gameAuditConfig': {}, 'gameConfig': {}}).encode()
    key = hashlib.md5(b'123459_2_72026/02/03-04:05:06').hexdigest().encode()
    pad = 16 - len(body) % 16
    encoded = base64.b64encode(AES.new(key, AES.MODE_CBC, key[:16]).encrypt(body + bytes([pad]) * pad))
    member = b'MZ' + b'\0' * 62 + struct.pack('>I', len(encoded)) + encoded
    member += struct.pack('>I', len(identity)) + identity
    return member, identity, encoded


def test_qt_resources_use_stored_lengths_and_semantic_identity_without_link_addresses_or_keys():
    member, identity, encoded = resource_fixture()
    assert bootstrap.launcher_data_resources(member) == (identity, encoded)
    # A moved component with unrelated data before the qrc arrays still resolves.
    assert bootstrap.launcher_data_resources(member[:64] + b'unrelated' + member[64:]) == (identity, encoded)


@pytest.mark.parametrize('case', ['missing-config', 'duplicate-identity', 'duplicate-config', 'wrong-identity', 'missing-length'])
def test_ambiguous_or_unproven_qt_resources_never_become_a_partial_bootstrap(case):
    member, identity, encoded = resource_fixture()
    if case == 'missing-config': member = member.replace(encoded, b'x' * len(encoded))
    if case == 'duplicate-identity': member += struct.pack('>I', len(identity)) + identity
    if case == 'duplicate-config': member += struct.pack('>I', len(encoded)) + encoded
    if case == 'wrong-identity': member = member.replace(b'9.2.7', b'9.2.8')
    if case == 'missing-length': member = member.replace(struct.pack('>I', len(encoded)), b'\0\0\0\0')
    with pytest.raises(ValueError): bootstrap.launcher_data_resources(member)


def remote_fixture(monkeypatch):
    member, identity, _ = resource_fixture()
    packed_member = deflate(member)
    member_block = struct.pack('<I', len(packed_member) | 0x80000000) + packed_member
    raw = bytearray(128 * 1024)
    raw[:2] = b'MZ'
    struct.pack_into('<I', raw, 60, 64)
    raw[64:68] = b'PE\0\0'
    struct.pack_into('<H', raw, 70, 1)
    struct.pack_into('<H', raw, 84, 2)
    struct.pack_into('<H', raw, 88, 0x10b)
    struct.pack_into('<II', raw, 90 + 16, 64 * 1024 - 512, 512)
    header = nsis_fixture(('xstarter.exe',))
    packed_header = deflate(header)
    overlay = 64 * 1024
    prefix = frame(header, packed_header, True)
    raw[overlay:overlay + 32] = prefix
    raw[overlay + 32:overlay + 32 + len(packed_header)] = packed_header
    offset = overlay + 32 + len(packed_header) + 1000
    raw[offset:offset + len(member_block)] = member_block
    url = 'https://x6oversea-game-package.infoldgames.com/xstarter/402/synthetic.exe'
    pointer = bootstrap.release.LauncherPointer('global', url, '0' * 64)
    monkeypatch.setattr(bootstrap.release, 'discover_launcher', lambda *_args: pointer)
    return raw, pointer, identity, member, offset, len(member_block)


class RangeResponse:
    def __init__(self, url, raw, total, start=None, etag='"synthetic-v1"'):
        self.url, self.raw, self.status = url, raw, 200 if start is None else 206
        self.headers = {'Content-Length': str(total if start is None else len(raw)), 'ETag': etag}
        if start is not None:
            self.headers['Content-Range'] = f'bytes {start}-{start + len(raw) - 1}/{total}'
    def __enter__(self): return self
    def __exit__(self, *_args): pass
    def geturl(self): return self.url
    def read(self, count):
        assert self.status == 206, 'HEAD must not read an installer response body.'
        return self.raw[:count]


def test_cold_bootstrap_plans_only_metadata_then_reads_exact_member_without_an_installation(monkeypatch):
    raw, pointer, identity, member, offset, size = remote_fixture(monkeypatch)
    calls = []
    def request(req, **_kwargs):
        assert req.full_url == pointer.url
        if req.get_method() == 'HEAD':
            return RangeResponse(pointer.url, b'', len(raw))
        assert req.get_header('If-match') == '"synthetic-v1"'
        start, end = map(int, req.get_header('Range').removeprefix('bytes=').split('-'))
        calls.append((start, end + 1 - start))
        return RangeResponse(pointer.url, bytes(raw[start:end + 1]), len(raw), start)
    plan = bootstrap.plan_bootstrap(opener=request)
    assert plan.member_offset == offset and plan.member_download_bytes == size
    assert calls[-1] == (offset, 4)
    assert (offset, size) not in calls
    observed_identity, config, digest = bootstrap.load_bootstrap_config(plan, opener=request)
    assert observed_identity == identity and config['appConfig']['fixture'] is True
    assert digest == hashlib.sha256(member).hexdigest() and calls[-1] == (offset, size)


@pytest.mark.parametrize('case', ['ignored-range', 'changed-validator', 'truncated', 'redirect', 'wrong-total'])
def test_changed_or_incomplete_installer_ranges_cannot_mix_into_a_bootstrap(monkeypatch, case):
    raw, pointer, *_ = remote_fixture(monkeypatch)
    def request(req, **_kwargs):
        if req.get_method() == 'HEAD': return RangeResponse(pointer.url, b'', len(raw))
        start, end = map(int, req.get_header('Range').removeprefix('bytes=').split('-'))
        response = RangeResponse(pointer.url, bytes(raw[start:end + 1]), len(raw), start)
        if case == 'ignored-range': response.status = 200
        if case == 'changed-validator': response.headers['ETag'] = '"synthetic-v2"'
        if case == 'truncated': response.raw = response.raw[:-1]
        if case == 'redirect': response.url = 'https://example.invalid/source'
        if case == 'wrong-total': response.headers['Content-Range'] += '0'
        return response
    with pytest.raises(ValueError): bootstrap.plan_bootstrap(opener=request)
