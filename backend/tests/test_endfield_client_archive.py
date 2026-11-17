"""Original archive boundaries, complete-member controls and changed declarations."""
import io
import struct
import zipfile

import pytest

from backend.endfield_client_archive import Archive


NAME = 'Endfield_Data/Plugins/x86_64/OwnedSound.dll'


def fixture(*, zip64=False):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(NAME, b'owned complete native member' * 20)
        archive.writestr('unrelated/readme.txt', b'not a native import')
    raw = output.getvalue()
    if zip64:
        row = struct.unpack_from('<4s4H2IH', raw, len(raw) - 22)
        offset = len(raw) - 22
        raw = (raw[:-22] + struct.pack('<4sQ2H2I4Q', b'PK\x06\x06', 44, 45, 45,
                0, 0, row[4], row[4], row[5], row[6]) +
               struct.pack('<4sIQI', b'PK\x06\x07', 0, offset, 1) +
               struct.pack('<4s4H2IH', b'PK\x05\x06', 0, 0, 0xffff, 0xffff, 0xffffffff, 0xffffffff, 0))
    return raw


def reader(raw, splits=()):
    edges = [0, *splits, len(raw)]
    parts = [raw[a:b] for a, b in zip(edges, edges[1:])]
    calls = []
    artifacts = [{'url': f'https://publisher.invalid/owned.zip.{n:03}', 'md5': 'a' * 32,
                  'bytes': len(part)} for n, part in enumerate(parts, 1)]
    def read(number, offset, size):
        calls.append((number, offset, size))
        return parts[number][offset:offset + size]
    return Archive(artifacts, read), calls


@pytest.mark.parametrize('zip64', [False, True])
def test_owned_member_has_complete_crc_after_split_range_reads(zip64):
    raw = fixture(zip64=zip64)
    archive, calls = reader(raw, (23, 103, len(raw) - 37))
    plan = archive.tail()
    assert plan['entries'] == 2 and 0 < plan['bytes'] < len(raw)
    member = archive.native_member('OwnedSound')
    assert archive.extract(member) == b'owned complete native member' * 20
    assert len({number for number, _, _ in calls}) == 4
    assert all(size <= len(raw) for _, _, size in calls)


def test_artifact_order_and_original_identity_are_required_before_reads():
    archive, _ = reader(fixture(), (150,))
    for changes in ({'bytes': 0}, {'md5': 'not a digest'}, {'url': 'https://publisher.invalid/wrong.zip.001'},
                    {'url': 'https://publisher.invalid/owned.zip.001?token=unbound'}):
        artifacts = [dict(row) for row in archive.artifacts]
        artifacts[1].update(changes)
        with pytest.raises(ValueError):
            Archive(artifacts, lambda *_: pytest.fail('must fail before original reads'))


def test_short_range_and_missing_current_import_never_select_another_member():
    raw = fixture()
    archive, _ = reader(raw)
    with pytest.raises(ValueError, match='does not declare'):
        archive.native_member('OtherSound')
    with pytest.raises(ValueError):
        archive.native_member('../OwnedSound')
    short = Archive(archive.artifacts, lambda *_: b'')
    with pytest.raises(ValueError, match='range length'):
        short.tail()


def test_limits_are_checked_before_member_payload_io():
    archive, calls = reader(fixture())
    member = archive.native_member('OwnedSound')
    count = len(calls)
    with pytest.raises(ValueError, match='approved'):
        archive.extract(member, maximum=member.size - 1)
    assert len(calls) == count


@pytest.mark.parametrize('mutation', ['crc', 'name', 'method', 'encrypted', 'overlap', 'trailing', 'terminal'])
def test_changed_directory_or_local_envelope_is_rejected(mutation):
    raw = bytearray(fixture())
    cd = raw.index(b'PK\x01\x02')
    if mutation == 'crc':
        raw[cd + 16] ^= 1
    elif mutation == 'name':
        raw[30] ^= 1
    elif mutation == 'method':
        struct.pack_into('<H', raw, cd + 10, 99)
    elif mutation == 'encrypted':
        struct.pack_into('<H', raw, cd + 8, 1)
    elif mutation == 'overlap':
        second = raw.index(b'PK\x01\x02', cd + 4)
        struct.pack_into('<I', raw, second + 42, 1)
    elif mutation == 'trailing':
        raw += b'not authored terminal data'
    elif mutation == 'terminal':
        struct.pack_into('<H', raw, len(raw) - 22 + 8, 30000)
    archive, _ = reader(bytes(raw))
    with pytest.raises((ValueError, UnicodeError)):
        archive.extract(archive.native_member('OwnedSound'))


def test_changed_complete_payload_fails_crc_without_being_returned():
    raw = bytearray(fixture())
    archive, _ = reader(bytes(raw))
    member = archive.native_member('OwnedSound')
    raw[30 + len(NAME) + member.compressed - 2] ^= 0x40
    broken, _ = reader(bytes(raw))
    with pytest.raises((ValueError, __import__('zlib').error)):
        broken.extract(broken.native_member('OwnedSound'))


def test_nonzero_disk_zip64_is_not_interpreted_as_logical_concatenation():
    raw = bytearray(fixture(zip64=True))
    at = raw.index(b'PK\x06\x06')
    struct.pack_into('<I', raw, at + 16, 1)
    archive, _ = reader(bytes(raw))
    with pytest.raises(ValueError):
        archive.tail()
