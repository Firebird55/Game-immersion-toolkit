"""Missing, changed or unsafe supplier notices must never become build inputs."""
from importlib.util import module_from_spec, spec_from_file_location
import hashlib
import io
import json
from pathlib import Path
import tarfile

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
