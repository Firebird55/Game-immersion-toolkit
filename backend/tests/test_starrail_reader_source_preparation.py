"""Source selection and hostile ZIP regressions use only authored fixtures."""
import base64
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import stat
import zipfile

import pytest


spec = importlib.util.spec_from_file_location('prepare_starrail_reader', Path('scripts/prepare-starrail-reader.py'))
prepare = importlib.util.module_from_spec(spec)
spec.loader.exec_module(prepare)


def zipped(files):
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        for name, value in files:
            archive.writestr(name, value)
    return output.getvalue()


@pytest.mark.parametrize('name', ['../escape.cs', 'root/../escape.cs', '/absolute.cs', 'root\\escape.cs', 'C:/escape.cs'])
def test_source_archives_reject_unsafe_paths(name):
    data = zipped([(name, b'authored fixture')])
    if '\\' in name:
        # ZipInfo normalizes Windows separators when *writing* on Windows;
        # author the hostile central/local names explicitly for the read test.
        data = data.replace(name.replace('\\', '/').encode(), name.encode())
    with pytest.raises(ValueError):
        prepare.archive(data)


def test_source_archives_reject_duplicate_case_and_links():
    with pytest.raises(ValueError):
        prepare.archive(zipped([('Root/Reader.cs', b'first'), ('root/reader.cs', b'second')]))
    entry = zipfile.ZipInfo('root/link.cs'); entry.external_attr = (stat.S_IFLNK | 0o777) << 16
    with pytest.raises(ValueError):
        prepare.archive(zipped([(entry, b'elsewhere')]))


def software_fixture(cache):
    license_data, mit, dll = b'authored GPL license', b'authored MIT license', b'authored managed assembly'
    selected = b'authored compiler input'
    blobs = {'metadata.zip': zipped([('HSRGlobalMetadata-fixture/LICENSE', license_data),
        ('HSRGlobalMetadata-fixture/HSRGlobalMetadata/Reader.cs', selected),
        ('HSRGlobalMetadata-fixture/HSRGlobalMetadata/DummyDll/Excluded.cs', b'not compiled'),
        ('HSRGlobalMetadata-fixture/HSRGlobalMetadata/DummyDll/Resources/unused.dll', b'not shipped')]),
        'decoder.zip': zipped([('iced-fixture/LICENSE.txt', mit)]),
        'iced.1.21.0.nupkg': zipped([('lib/decoder.dll', dll), ('LICENSE.txt', mit)])}
    for name, data in blobs.items():
        (cache / name).write_bytes(data)
    def pin(name):
        return {'artifact': name, 'sha256': prepare.digest(blobs[name]), 'source': 'https://invalid.test/' + name}
    pins = {'metadata': {**pin('metadata.zip'), 'revision': 'fixture', 'license_sha256': prepare.digest(license_data),
                        'files': {'Reader.cs': prepare.digest(selected)}},
            'decoder': {**pin('decoder.zip'), 'package': {**pin('iced.1.21.0.nupkg'),
                'sha512_base64': base64.b64encode(hashlib.sha512(blobs['iced.1.21.0.nupkg']).digest()).decode(),
                'dll_member': 'lib/decoder.dll', 'dll_sha256': prepare.digest(dll),
                'license_member': 'LICENSE.txt', 'license_sha256': prepare.digest(mit)}}}
    return pins


def test_preparation_is_offline_closed_and_rejects_source_mutation(tmp_path, monkeypatch):
    cache = tmp_path / 'cache'; cache.mkdir()
    pins = software_fixture(cache)
    policy = tmp_path / 'pins.json'; policy.write_text(json.dumps(pins)); monkeypatch.setattr(prepare, 'PINS', policy)
    monkeypatch.setattr(prepare.urllib.request, 'urlopen', lambda *a, **k: pytest.fail('Frozen source inputs cannot require a new publication'))
    output = tmp_path / 'prepared'
    proof = prepare.prepare(cache, output)
    assert 'source/Reader.cs' in proof['files']
    assert not any('Excluded' in name for name in proof['files'])
    with zipfile.ZipFile(output / 'corresponding-source/hsr-metadata-source.zip') as source:
        assert set(source.namelist()) == {'LICENSE', 'HSRGlobalMetadata/Reader.cs'}
    assert prepare.verify(output) == proof
    with pytest.raises(ValueError):
        prepare.prepare(cache, output)
    (output / 'source/Injected.cs').write_text('authored unexpected source')
    with pytest.raises(ValueError, match='inventory'):
        prepare.verify(output)
    (output / 'source/Injected.cs').unlink()
    (output / 'source/Reader.cs').write_text('authored changed source')
    with pytest.raises(ValueError, match='inventory'):
        prepare.verify(output)


def test_package_digest_and_binary_member_are_both_pinned(tmp_path):
    pins = software_fixture(tmp_path)
    pins['decoder']['package']['dll_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='assembly'):
        prepare.prepare(tmp_path, tmp_path / 'output', pins=pins)
    assert not (tmp_path / 'output').exists()
