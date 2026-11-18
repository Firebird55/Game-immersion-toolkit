"""Android wheel failures which a desktop import cannot detect."""
import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import struct
import tarfile
import zipfile

import pytest


spec = importlib.util.spec_from_file_location('android_python_dependencies',
    Path(__file__).resolve().parents[2] / 'scripts/build-android-python-dependencies.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def authored_elf(machine=183, alignment=16384, python='libpython3.12.so'):
    names = [python, 'libc.so', 'libm.so', 'libdl.so']
    strings, offsets = bytearray(b'\0'), []
    for name in names:
        offsets.append(len(strings)); strings.extend(name.encode() + b'\0')
    data = bytearray(1024)
    data[:16] = b'\x7fELF\x02\x01\x01' + bytes(9)
    struct.pack_into('<HHIQQQIHHHHHH', data, 16, 3, machine, 1, 0, 64, 0, 0, 64, 56, 2, 0, 0, 0)
    struct.pack_into('<IIQQQQQQ', data, 64, 1, 5, 0, 0, 0, len(data), len(data), alignment)
    entries = [(1, offset) for offset in offsets] + [(5, 768), (10, len(strings)), (0, 0)]
    struct.pack_into('<IIQQQQQQ', data, 120, 2, 6, 512, 512, 0, len(entries) * 16, len(entries) * 16, 8)
    for index, (kind, value) in enumerate(entries):
        struct.pack_into('<qQ', data, 512 + index * 16, kind, value)
    data[768:768 + len(strings)] = strings
    return bytes(data)


@pytest.mark.parametrize('machine', [183, 62])
def test_target_elf_is_data_and_matches_android_python_dependency_contract(machine):
    result = builder.elf_contract(authored_elf(machine=machine), machine)
    assert result['page_alignment'] == 16384
    assert result['needed'] == ['libc.so', 'libdl.so', 'libm.so', 'libpython3.12.so']


@pytest.mark.parametrize('machine', [183, 62])
def test_explicit_crypto_dependencies_reuse_the_same_strict_elf_parser(machine):
    data = bytearray(authored_elf(machine=machine))
    libc = data.index(b'libc.so\0', 768) - 768
    entries = [(1,libc),(5,768),(10,256),(0,0)]
    # Keep the actual original DT_STRTAB size, not an invented expansion.
    entries[2] = (10, len(data[768:].split(b'\0\0',1)[0]) + 1)
    for index,pair in enumerate(entries):struct.pack_into('<qQ',data,512+index*16,*pair)
    result = builder.elf_contract(bytes(data),machine,expected_dependencies=('libc.so',))
    assert result['needed'] == ['libc.so'] and result['page_alignment'] == 16384
    with pytest.raises(ValueError):builder.elf_contract(bytes(data),machine)
    with pytest.raises(ValueError):builder.elf_contract(bytes(data),62 if machine == 183 else 183,('libc.so',))
    # Missing, extra and duplicate actual dependencies fail the same contract.
    missing = bytearray(data);struct.pack_into('<qQ',missing,512,0,0)
    with pytest.raises(ValueError):builder.elf_contract(bytes(missing),machine,('libc.so',))
    with pytest.raises(ValueError):builder.elf_contract(authored_elf(machine=machine),machine,('libc.so',))
    duplicate = bytearray(data)
    for index,pair in enumerate([(1,libc),(1,libc),(5,768),entries[2],(0,0)]):
        struct.pack_into('<qQ',duplicate,512+index*16,*pair)
    with pytest.raises(ValueError):builder.elf_contract(bytes(duplicate),machine,('libc.so',))


@pytest.mark.parametrize('data', [
    b'MZ' + bytes(1022), authored_elf(machine=62), authored_elf(alignment=4096),
    authored_elf(python='libpython3.13.so'), authored_elf()[:600],
    authored_elf(python='F:/owned-build/libpython3.12.so'),
])
def test_wrong_host_abi_page_size_python_or_truncated_binary_never_enters_wheel(data):
    with pytest.raises(ValueError):
        builder.elf_contract(data, 183)


def test_native_wheel_keeps_original_python_stubs_licenses_and_complete_records(tmp_path):
    source = tmp_path / 'source'
    package = source / 'python/pydantic_core'
    package.mkdir(parents=True)
    (package / '__init__.py').write_text('from ._pydantic_core import SchemaValidator\n')
    (package / 'py.typed').touch()
    (source / 'LICENSE').write_text('Authored library license\n')
    (source / 'PKG-INFO').write_text('Metadata-Version: 2.4\nName: pydantic_core\nVersion: 2.50.1\n')
    wheel = builder.native_wheel(source, authored_elf(), tmp_path, 'arm64-v8a',
                                 {'rust/authored-crate/LICENSE': b'Authored dependency license\n'})
    assert wheel.name.endswith('cp312-cp312-android_24_arm64_v8a.whl')
    with zipfile.ZipFile(wheel) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
        record = next(name for name in files if name.endswith('.dist-info/RECORD'))
        rows = list(csv.reader(io.StringIO(files[record].decode())))
    assert 'pydantic_core/_pydantic_core.cpython-312.so' in files
    assert any(name.endswith('licenses/rust/authored-crate/LICENSE') for name in files)
    assert any(name.endswith('/py.typed') for name in files)
    assert {row[0] for row in rows} == set(files)
    for name, digest, length in rows:
        if name == record:
            assert digest == length == ''
        else:
            assert digest == 'sha256=' + base64.urlsafe_b64encode(hashlib.sha256(files[name]).digest()).decode().rstrip('=')
            assert int(length) == len(files[name])


@pytest.mark.parametrize('name', ['../outside.py', 'C:/outside.py', 'source/../../outside.py', 'source\\outside.py'])
def test_source_unpack_rejects_traversal_before_any_member_is_extracted(tmp_path, name):
    archive = tmp_path / 'source.tar.gz'
    with tarfile.open(archive, 'w:gz') as output:
        for member in ('source/good.py', name):
            item = tarfile.TarInfo(member); item.size = 1
            output.addfile(item, io.BytesIO(b'x'))
    destination = tmp_path / 'destination'
    with pytest.raises(ValueError):
        builder.unpack_tar(archive, destination)
    assert not destination.exists()


def test_wrong_cached_input_digest_is_not_repackaged(tmp_path):
    artifact = tmp_path / 'source.whl'; artifact.write_bytes(b'corrupt')
    with pytest.raises(ValueError, match='checksum'):
        builder.acquire(tmp_path, {'artifact': artifact.name, 'sha256': hashlib.sha256(b'authored').hexdigest()})
    assert artifact.read_bytes() == b'corrupt'
