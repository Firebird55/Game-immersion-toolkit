"""Official identity, authored rotations and atomic index/parameter activation."""
import copy
import hashlib
import json
import struct
from types import SimpleNamespace

import pytest

from backend import endfield_client_contract as contract, endfield_client_source as source
from backend import endfield_parameters as parameters
from backend.tests.endfield_parameter_fixture import Fixture, DEFINE, VFS, MemorySource, toy_metadata, toy_pe
from backend.tests.test_endfield_vfs import PARAMETERS, index


def identity():
    base = 'https://beyond.hg-cdn.com/YDUTE5gscDZ229CW/9.8/update/6/6/Windows/9.8.7_Authored/files'
    latest = {'version': '9.8.7', 'pkg': {'file_path': base, 'game_files_md5': 'a' * 32,
              'packs': [{'url': base[:-6] + '/packs/owned.zip?auth_key=discard',
                         'md5': 'b' * 32, 'package_size': '4096'}]}}
    return source.client_identity(latest, region='global', cdn=base.split('/9.8/')[0])


def test_identity_retains_declared_artifacts_but_never_temporary_download_tokens():
    original = identity()
    assert 'discard' not in json.dumps(original)
    changed = copy.deepcopy(original)
    changed['artifacts'][0]['md5'] = 'c' * 32
    assert source.identity_stamp(changed) != source.identity_stamp(original)
    changed['region'] = 'cn'
    assert source.identity_stamp(changed) != source.identity_stamp(original)


class Response:
    status = 206
    def __init__(self, url, data, *, total=20, etag='"owned"', range_='bytes 2-5/20'):
        self.url, self.data = url, data
        self.headers = {'Content-Range': range_, 'Content-Length': str(len(data)), 'ETag': etag}
    def geturl(self): return self.url
    def read(self, _size): return self.data
    def __enter__(self): return self
    def __exit__(self, *_): pass


def test_range_cache_keeps_original_identity_and_detects_corruption(tmp_path):
    opened = []
    def fetch(request, **_):
        opened.append(request)
        return Response(request.full_url, b'body')
    reader = source.Ranges(tmp_path, identity(), 'GameAssembly.dll', opener=fetch)
    assert reader.read(2, 4) == b'body'
    assert reader.read(2, 4) == b'body' and len(opened) == 1
    assert reader.receipts[-1]['whole_file_hash_verified'] is False
    (reader.root / '2-4.bin').write_bytes(b'bad!')
    assert reader.read(2, 4) == b'body' and len(opened) == 2
    newer = copy.deepcopy(identity())
    newer['game_files_md5'] = 'd' * 32
    assert source.Ranges(tmp_path, newer, 'GameAssembly.dll').root != reader.root


@pytest.mark.parametrize('range_,data', [('bytes 3-6/20', b'body'), ('bytes 2-5/3', b'body'),
                                        ('bytes 2-5/20', b'short'), ('', b'body')])
def test_bad_ranges_are_not_cached(tmp_path, range_, data):
    reader = source.Ranges(tmp_path, identity(), 'GameAssembly.dll', opener=lambda request, **_: Response(
        request.full_url, data, range_=range_))
    with pytest.raises(ValueError):
        reader.read(2, 4)
    assert not reader.root.exists()


def test_changed_range_identity_retains_the_previously_verified_cache(tmp_path):
    responses = iter([('bytes 2-5/20', '"first"'), ('bytes 6-9/20', '"changed"')])
    def fetch(request, **_):
        range_, etag = next(responses)
        return Response(request.full_url, b'body', etag=etag, range_=range_)
    reader = source.Ranges(tmp_path, identity(), 'GameAssembly.dll', opener=fetch)
    assert reader.read(2, 4) == b'body'
    with pytest.raises(ValueError, match='identity changed'):
        reader.read(6, 4)
    assert (reader.root / '2-4.bin').read_bytes() == b'body'
    assert not (reader.root / '6-4.bin').exists()


def test_owned_metadata_fields_methods_and_literal_have_independent_bounds():
    original = source.Metadata(MemorySource(toy_metadata()))
    assert original.owner('Owned.Client') == 0
    assert original.method('Owned.Client', 'Prepare', 0)['token'] == 0x06000001
    assert original.fields('Owned.Client')['Seed']['token'] == 0x04000001
    assert original.literal(0) == 'owned'
    with pytest.raises(ValueError):
        original.literal(1)
    changed = bytearray(toy_metadata())
    struct.pack_into('<I', changed, 4, 30)
    with pytest.raises(ValueError):
        source.Metadata(MemorySource(bytes(changed)))


def test_preflight_reads_only_headers_before_large_metadata_decision(tmp_path, monkeypatch):
    monkeypatch.setattr(parameters, 'source_runtime', lambda: None)
    metadata, native = MemorySource(toy_metadata()), MemorySource(toy_pe())
    monkeypatch.setattr(parameters, 'Ranges', lambda _tools, _identity, name:
                        native if name == 'GameAssembly.dll' else metadata)
    result = parameters.preflight_client(tmp_path, identity())
    assert metadata.reads == [(0, 256)] and native.reads == [(0, 4096)]
    assert result['metadata_bytes'] == sum(row['bytes'] for row in result['ranges'])
    assert result['content_bytes'] is None and result['requires_current_index_plan'] is True
    assert result['metadata_overhead_upper_bytes'] > 0


def test_owned_pe_boundary_and_overlapping_section_rejection():
    image = source.Image(MemorySource(toy_pe()))
    entry = image.boundary(image.base + 0x1000)
    assert image.unwind_owner(entry) == image.base + 0x1000
    with pytest.raises(ValueError):
        image.offset(image.base + 0x1100, 1)
    with pytest.raises(ValueError, match='static data'):
        image.data_read(image.base + 0x1000, 4)
    with pytest.raises(ValueError, match='executable'):
        image.read_code(image.base + 0x2000, 4)
    changed = bytearray(toy_pe())
    struct.pack_into('<I', changed, 0x98 + 240 + 2 * 40 + 12, 0x2000)
    with pytest.raises(ValueError, match='Overlapping'):
        source.Image(MemorySource(bytes(changed)))


@pytest.mark.parametrize('mask,shift', [('owned mask', 0), ('a different mask length', 19), ('x', 47)])
def test_authored_key_and_mask_rotations_follow_the_same_contract(mask, shift):
    key = bytes((n + shift) & 255 for n in range(32))
    fixture = Fixture(key=key, mask=mask)
    assert contract._key(fixture.owner_reader(), fixture.code_reader()) == key


@pytest.mark.parametrize('change', ['missing-fragment', 'wrong-owner', 'wrong-conversion', 'wrong-subtraction'])
def test_incomplete_or_changed_key_contract_is_not_guessed(change):
    fixture = Fixture()
    if change == 'missing-fragment':
        rows = fixture.methods[VFS, '.cctor']
        # Remove one entire owned array-set operation, not merely its text.
        del rows[4:8]
    elif change == 'wrong-owner':
        for row in fixture.methods[VFS, '.cctor']:
            if row.owner == VFS:
                row.owner = 'Fixture.OtherOwner'
    elif change == 'wrong-conversion':
        fixture.names['System.Convert', 'TryFromBase64Chars'] = 0xdead
    else:
        fixture.methods['Fixture.PrivateTransform', 'ChangedName'][3].op_str = 'eax, edx'
    with pytest.raises((ValueError, KeyError)):
        contract._key(fixture.owner_reader(), fixture.code_reader())


def test_every_authored_map_label_and_field_offset_can_change_without_an_id_list():
    fixture = Fixture(labels={13: 'Changed Authored Video', 44: 'New Authored Type'})
    labels, protocol = contract._map(fixture.owner_reader(), fixture.code_reader())
    assert labels == fixture.labels and protocol == 3
    rows = fixture.methods[DEFINE, '.cctor']
    fixture.fields[DEFINE]['s_vfsTypeNameMap'] = 0x180
    for row in rows:
        if row.operands and row.operands[0].type == 3 and row.operands[0].mem.disp == 0x80:
            row.operands[0].mem.disp = 0x180
    assert contract._map(fixture.owner_reader(), fixture.code_reader())[0] == labels


def test_full_owned_contract_rehashes_changed_labels_instead_of_reusing_ids(monkeypatch):
    from backend import endfield_xxhash
    fixture = Fixture(labels={7: 'Owned first label', 47: 'Owned added type'})
    observed = []
    def owned_hash(data):
        observed.append(data)
        return int.from_bytes(hashlib.sha256(data).digest()[:8], 'little')
    monkeypatch.setattr(contract, 'Owners', fixture.owner_reader)
    monkeypatch.setattr(contract, 'Code', fixture.code_reader)
    monkeypatch.setattr(endfield_xxhash, 'hash64', owned_hash)
    first = contract.derive(None, None)
    assert observed == [value.encode() for value in fixture.labels.values()]
    fixture.labels[47] = 'Owned changed type'
    # Rebuild the authored producer with a changed key, mask and map text.
    fixture = Fixture(key=bytes(reversed(range(32))), mask='Changed fixture mask', labels=fixture.labels)
    monkeypatch.setattr(contract, 'Owners', fixture.owner_reader)
    monkeypatch.setattr(contract, 'Code', fixture.code_reader)
    second = contract.derive(None, None)
    assert second.key != first.key and second.directories[7] == first.directories[7]
    assert second.directories[47] != first.directories[47]


def test_different_original_field_type_cannot_supply_a_parameter():
    fixture = Fixture()
    fixture.field_types['CHACHA_KEYS'] = 'System.Int32'
    with pytest.raises(ValueError):
        contract._key(fixture.owner_reader(), fixture.code_reader())


def test_bad_crc_or_changed_client_never_replaces_active_parameters(tmp_path):
    client = identity()
    candidate = contract.Candidate(PARAMETERS.key, PARAMETERS.directories, 3)
    raw = index(64, name='authored.pck')
    assert len(parameters.activate(tmp_path, client, candidate, PARAMETERS, 102, raw, recheck=lambda: client)) == 1
    path = parameters._path(tmp_path, client)
    accepted = path.read_bytes()
    with pytest.raises(ValueError):
        parameters.activate(tmp_path, client, candidate, PARAMETERS, 102, raw[:-1] + bytes([raw[-1] ^ 1]),
                            recheck=lambda: pytest.fail('invalid index reached source recheck'))
    assert path.read_bytes() == accepted
    changed = copy.deepcopy(client)
    changed['game_files_md5'] = 'e' * 32
    with pytest.raises(ValueError, match='changed'):
        parameters.activate(tmp_path, client, candidate, PARAMETERS, 102, index(65, name='changed.pck'),
                            recheck=lambda: changed)
    assert path.read_bytes() == accepted
    assert len(parameters.activate(tmp_path, client, candidate, PARAMETERS, 102, raw,
               recheck=lambda: pytest.fail('unchanged verified index must work offline'))) == 1
    other_path = parameters._path(tmp_path, changed)
    assert not other_path.exists()


def test_a_different_parameter_object_cannot_validate_the_candidate(tmp_path):
    candidate = contract.Candidate(bytes(reversed(PARAMETERS.key)), PARAMETERS.directories, 3)
    with pytest.raises(ValueError, match='do not belong'):
        parameters.activate(tmp_path, identity(), candidate, PARAMETERS, 102, index(64),
                            recheck=lambda: pytest.fail('wrong candidate reached activation'))
    assert not parameters._path(tmp_path, identity()).exists()


def test_normal_group_uses_changed_official_key_and_directory_for_archive_reads(tmp_path, monkeypatch):
    from Crypto.Cipher import ChaCha20
    from backend import endfield_release as release, endfield_metadata
    from backend.endfield_vfs import Parameters
    client = identity()
    new_key = bytes(reversed(PARAMETERS.key))
    directories = {k: f'{n + 123:08X}' for n, k in enumerate(PARAMETERS.directories)}
    candidate = contract.Candidate(new_key, directories, 3)
    raw = index(64, name='authored.pck')
    def cipher(key):
        result = ChaCha20.new(key=key, nonce=raw[:12])
        result.seek(64)
        return result
    updated = raw[:12] + cipher(new_key).encrypt(cipher(PARAMETERS.key).decrypt(raw[12:]))
    layer = release.CDN + '/9.8/resource/Windows/main/12-3_Owned/files'
    descriptor = {'version': '9.8.7', 'client': client, 'layers': {'main': {'url': layer}}}
    encoded = json.dumps(descriptor).encode()
    stamp = release._stamp(encoded)
    release._atomic_file(tmp_path / 'endfield-releases' / stamp, encoded)
    monkeypatch.setattr(parameters, 'candidate', lambda *_: candidate)
    monkeypatch.setattr(endfield_metadata, 'parameters', lambda *_: PARAMETERS)
    monkeypatch.setattr(release, 'latest_client', lambda *_: ({}, client))
    requested = []
    def fetch(url, **_):
        requested.append(url)
        assert url == layer + '/VFS/' + directories[102] + '/' + directories[102] + '.blc'
        return updated
    monkeypatch.setattr(release, 'download', fetch)
    base, files = release.group(tmp_path, stamp, 102)
    assert base.parameters == Parameters(new_key, directories, PARAMETERS.multiplier, PARAMETERS.xor_constant)
    assert release._source(tmp_path, base, files[0]).parameters.key == new_key
    assert parameters._active(tmp_path, client)[0] == candidate and len(requested) == 1
