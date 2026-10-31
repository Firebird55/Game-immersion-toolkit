"""Missing, changed or unsafe supplier notices must never become build inputs."""
from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import io
import json
from pathlib import Path
import tarfile
import urllib.error

import pytest

spec = spec_from_file_location('qt_resources', Path(__file__).resolve().parents[2] / 'scripts/build-qt-resources.py')
qt = module_from_spec(spec)
spec.loader.exec_module(qt)


def fixture(cache, *, unsafe=None, omit_license=False):
    cache.mkdir()
    archive = cache / 'qt-fixture.tar.xz'
    with tarfile.open(archive, 'w:xz') as source:
        files = {'qt-fixture/src/data/qt_attribution.json': b'{"Copyright": "Authored fixture"}',
                 'qt-fixture/src/example.cpp': b'// Authored source fixture'}
        if not omit_license:
            files['qt-fixture/LICENSES/LGPL-3.0-only.txt'] = b'Authored license fixture; not actual LGPL terms.'
        if unsafe:
            files[unsafe] = b'Not a safe archive path'
        for name, data in files.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            source.addfile(entry, io.BytesIO(data))
    return {'version': 'fixture', 'components': [{'name': 'qt-fixture', 'archive': archive.name,
        'url': 'https://invalid.example/never-requested', 'sha256': qt.digest(archive)}]}


def test_sources_and_full_notices_survive_resource_collection(tmp_path):
    cache, output = tmp_path / 'cache', tmp_path / 'resources'
    pins = fixture(cache)
    receipt = qt.build(output, cache, pins)
    root = output / qt.PREFIX / 'qt-fixture'
    assert (root / 'qt-fixture.tar.xz').read_bytes() == (cache / 'qt-fixture.tar.xz').read_bytes()
    index = json.loads((root / 'notices/index.json').read_text())
    by_origin = {item['source_path']: root / 'notices' / name for name, item in index.items()}
    assert by_origin['LICENSES/LGPL-3.0-only.txt'].read_bytes().startswith(b'Authored license fixture')
    assert json.loads(by_origin['src/data/qt_attribution.json'].read_bytes())['Copyright'] == 'Authored fixture'
    assert not (root / 'notices/src/example.cpp').exists()
    assert receipt['rights_review'] == 'pending-exact-output'
    assert len(receipt['files']) == 5
    for file in receipt['files']:
        data = (output / file['path']).read_bytes()
        assert hashlib.sha256(data).hexdigest() == file['sha256']
        assert len(data) == file['bytes']
    # Exercise the production collector/private-file gate, not merely the
    # resource manifest. Public source paths must not create live data trees.
    runtime_spec = spec_from_file_location('desktop_runtime', qt.ROOT / 'scripts/build-desktop-runtime.py')
    runtime = module_from_spec(runtime_spec)
    runtime_spec.loader.exec_module(runtime)
    collected = tmp_path / 'collected'
    runtime.extra_resources(output, collected)
    assert len(runtime.tree(collected)) == len(receipt['files'])


@pytest.mark.parametrize('fault', ['changed', 'missing-license', 'escape'])
def test_invalid_supplier_sources_produce_no_resources(tmp_path, fault):
    cache, output = tmp_path / 'cache', tmp_path / 'resources'
    pins = fixture(cache, omit_license=fault == 'missing-license',
        unsafe='qt-fixture/../../LICENSE' if fault == 'escape' else None)
    if fault == 'changed':
        (cache / 'qt-fixture.tar.xz').write_bytes(b'Changed archive')
    with pytest.raises(ValueError):
        qt.build(output, cache, pins)
    assert not output.exists()


def test_component_specific_terms_and_vendor_attribution_are_retained(tmp_path):
    archive = tmp_path / 'qt-fixture.tar.xz'
    contents = {'qt-fixture/LICENSES/GPL-3.0-only.txt': b'Authored GPL fixture.',
                'qt-fixture/doc/src/legal/licenses.qdoc': b'Authored Mesa and LLVM attribution fixture.'}
    with tarfile.open(archive, 'w:xz') as source:
        for name, data in contents.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(data)
            source.addfile(entry, io.BytesIO(data))
    required = ['LICENSES/GPL-3.0-only.txt', 'doc/src/legal/licenses.qdoc']
    records = dict(qt.notices(archive, 'qt-fixture', required))
    assert records == {name.removeprefix('qt-fixture/'): data for name, data in contents.items()}
    # Translations and documentation do not inherit QtBase's LGPL alternative.
    with pytest.raises(ValueError, match='required full license'):
        qt.notices(archive, 'qt-fixture')


def download_pin(data):
    return {'archive': 'qt-fixture.tar.xz', 'url': 'https://invalid.example/qt-fixture.tar.xz',
            'sha256': hashlib.sha256(data).hexdigest()}


def test_interrupted_download_retries_atomically(tmp_path, monkeypatch):
    data = b'Authored supplier input'
    pin = download_pin(data)
    attempts, pauses = [], []

    class Interrupted(io.BytesIO):
        url = pin['url']

        def read(self, size):
            if self.tell():
                raise TimeoutError('authored transient interruption')
            return super().read(size)

    def download(*args, **kwargs):
        attempts.append(1)
        response = Interrupted(data[:5]) if len(attempts) == 1 else io.BytesIO(data)
        response.url = pin['url']
        return response

    monkeypatch.setattr(qt.urllib.request, 'urlopen', download)
    monkeypatch.setattr(qt.time, 'sleep', pauses.append)
    result = qt.acquire(pin, tmp_path)
    assert result.read_bytes() == data
    assert len(attempts) == 2 and pauses == [2]
    assert not result.with_name(result.name + '.part').exists()
    qt.acquire(pin, tmp_path)
    assert len(attempts) == 2  # A verified cache hit performs no network call.


def test_network_retry_is_bounded(tmp_path, monkeypatch):
    attempts = []

    def unavailable(*args, **kwargs):
        attempts.append(1)
        raise urllib.error.URLError('authored timeout')

    monkeypatch.setattr(qt.urllib.request, 'urlopen', unavailable)
    monkeypatch.setattr(qt.time, 'sleep', lambda _: None)
    with pytest.raises(urllib.error.URLError):
        qt.acquire(download_pin(b'fixture'), tmp_path)
    assert len(attempts) == 3
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('fault', ['checksum', 'preexisting-partial', 'not-found'])
def test_bad_input_is_never_retried_or_installed(tmp_path, monkeypatch, fault):
    pin = download_pin(b'expected')
    partial = tmp_path / (pin['archive'] + '.part')
    if fault == 'preexisting-partial':
        partial.write_bytes(b'prior incomplete input')
    attempts = []

    def download(*args, **kwargs):
        attempts.append(1)
        if fault == 'not-found':
            raise urllib.error.HTTPError(pin['url'], 404, 'not found', {}, None)
        response = io.BytesIO(b'changed')
        response.url = pin['url']
        return response

    monkeypatch.setattr(qt.urllib.request, 'urlopen', download)
    with pytest.raises((ValueError, FileExistsError, urllib.error.HTTPError)):
        qt.acquire(pin, tmp_path)
    assert len(attempts) == 1
    assert not (tmp_path / pin['archive']).exists()
    if fault == 'preexisting-partial':
        assert partial.read_bytes() == b'prior incomplete input'
    else:
        assert not partial.exists()
