"""Exact supplier/package/notice closure without executing supplier code."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest


def builder():
    path = Path(__file__).resolve().parents[2] / 'scripts/build-nte-toolchain.py'
    spec = importlib.util.spec_from_file_location('managed_reader_notices', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def digest(data):
    return hashlib.sha256(data).hexdigest()


def inputs(module):
    assembly, notice = b'authored managed assembly', b'authored complete notice'
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, 'w') as archive:
        archive.writestr('lib/runtime.dll', assembly)
        archive.writestr('LICENSE', notice)
    package = stream.getvalue()
    values = {'https://supplier.test/package': package, 'https://supplier.test/notice': notice}
    components = [{
        'name': f'Component{n}', 'sha256': digest(assembly), 'package': 'Authored',
        'url': 'https://supplier.test/package', 'package_sha256': digest(package),
        'matching_members': ['lib/runtime.dll'],
        'notices': [{'kind': 'package', 'member': 'LICENSE', 'sha256': digest(notice)},
                    {'kind': 'url', 'url': 'https://supplier.test/notice', 'sha256': digest(notice)}],
    } for n in range(29)]
    components.append({'name': 'CUE4Parse', 'sha256': digest(assembly),
                       'notices': [components[0]['notices'][1]]})
    return {'schema': 'toolkit-ue-managed-components-v1',
            'supplier_sha256': module.DEPENDENCIES['UEExtractor.dll'],
            'components': components}, values


def test_complete_notices_preserve_bytes_and_package_provenance(monkeypatch):
    module = builder()
    specification, values = inputs(module)
    monkeypatch.setattr(module, 'download', lambda url, **_: values[url])
    output = module.managed_notices(specification)
    assert len(output) == 60
    assert output['notices/Component0-01.txt'] == values['https://supplier.test/notice']
    assert json.loads(output['notices/MANAGED-COMPONENTS.json']) == specification
    assert all(name.startswith('notices/') and name.endswith(('.txt', '.json')) for name in output)


@pytest.mark.parametrize('fault', ['supplier', 'missing-component', 'duplicate-component',
                                  'missing-notice', 'package', 'assembly', 'notice', 'custom', 'path'])
def test_incomplete_or_mismatched_notice_closure_is_rejected(monkeypatch, fault):
    module = builder()
    specification, values = inputs(module)
    row = specification['components'][0]
    if fault == 'supplier': specification['supplier_sha256'] = '0' * 64
    elif fault == 'missing-component': specification['components'].pop()
    elif fault == 'duplicate-component': specification['components'][1] = copy.deepcopy(row)
    elif fault == 'missing-notice': row['notices'] = []
    elif fault == 'package': values[row['url']] = b'changed package'
    elif fault == 'assembly': row['sha256'] = '0' * 64
    elif fault == 'notice': row['notices'][0]['sha256'] = '0' * 64
    elif fault == 'custom': del row['package']
    elif fault == 'path': row['name'] = '../injected'
    monkeypatch.setattr(module, 'download', lambda url, **_: values[url])
    with pytest.raises(ValueError): module.managed_notices(specification)


def test_reviewed_inventory_covers_every_embedded_assembly_and_incorporated_notice():
    module = builder()
    lock = json.loads(module.MANAGED_COMPONENTS.read_text())
    rows = {row['name']: row for row in lock['components']}
    assert len(rows) == 30
    assert sum(bool(row.get('package')) for row in rows.values()) == 29
    assert all(row['notices'] and row['notice_revision'] for row in rows.values())
    assert len(rows['CUE4Parse']['notices']) == 2  # Apache LICENSE + incorporated-code NOTICE
    assert any(n.get('url', '').endswith('/COPYRIGHT') for n in rows['FixedMathSharp']['notices'])
    assert any(n.get('url', '').endswith('/NOTICE') for n in rows['Fmod5Sharp']['notices'])
    assert all('/' + row['notice_revision'] + '/' in notice['url']
               for row in rows.values() for notice in row['notices'] if notice['kind'] == 'url')


@pytest.mark.parametrize('platform', ['win-x64', 'linux-x64', 'darwin-arm64'])
def test_collector_binds_same_managed_bytes_to_selected_platform_without_claiming_native_acceptance(tmp_path, monkeypatch, platform):
    module = builder()
    data = b'authored shared managed assembly'
    monkeypatch.setattr(module, 'DEPENDENCIES', {'UEExtractor.dll': digest(data)})
    monkeypatch.setattr(module, 'verified', lambda *a, **kw: b'authored full notice')
    monkeypatch.setattr(module, 'extract', lambda *a, **kw: data)
    monkeypatch.setattr(module, 'managed_notices', lambda: {'notices/MANAGED-COMPONENTS.json': b'{}'})
    monkeypatch.setattr(module.subprocess, 'check_output', lambda args, **kw: 'a' * 40 if args[1] == 'rev-parse' else '')
    output = tmp_path / 'new-resources'
    receipt = module.build(output, platform=platform)
    manifest = json.loads((output / module.PREFIX / 'dependencies.json').read_text())
    assert receipt['platform'] == manifest['platform'] == platform
    assert (output / module.PREFIX / 'UEExtractor.dll').read_bytes() == data
    assert receipt['native_acceptance'] == manifest['native_acceptance'] == 'pending'
    assert receipt['rights_review'] == manifest['rights_review'] == 'pending'
    for row in receipt['files']:
        assert digest((output / row['path']).read_bytes()) == row['sha256']
