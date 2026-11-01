import hashlib
import importlib.util
import io
import json
from pathlib import Path
import zipfile

import pytest
from backend.runtime_bundle import RuntimeBundleError


ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('cyberpunk_notices', ROOT / 'scripts/cyberpunk_redistribution.py')
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


@pytest.mark.parametrize('kind', ['changed', 'duplicate', 'missing'])
def test_supplier_evidence_cannot_hide_changed_or_ambiguous_members(kind):
    data = b'Authored full license terms'
    output = io.BytesIO()
    with zipfile.ZipFile(output, 'w') as archive:
        if kind != 'missing':
            archive.writestr('LICENSE', data if kind != 'changed' else b'changed')
        if kind == 'duplicate':
            with pytest.warns(UserWarning):
                archive.writestr('LICENSE', data)
    with zipfile.ZipFile(io.BytesIO(output.getvalue())) as archive:
        with pytest.raises(ValueError):
            notices.checked_member(archive, 'LICENSE', hashlib.sha256(data).hexdigest())


def test_retained_evidence_rejects_overwrite_and_path_escape(tmp_path):
    evidence = notices.retain(tmp_path, 'notices/LICENSE', b'Authored terms')
    assert evidence['sha256'] == hashlib.sha256(b'Authored terms').hexdigest()
    with pytest.raises(ValueError, match='Conflicting'):
        notices.retain(tmp_path, 'notices/LICENSE', b'changed')
    with pytest.raises(RuntimeBundleError):
        notices.retain(tmp_path, '../outside', b'escape')


def test_selected_packages_have_full_terms_and_unambiguous_runtime_file_pins():
    pins = json.loads(notices.PINS.read_text(encoding='utf-8'))
    paths = set()
    for package in pins['packages']:
        assert package['url'].startswith('https://api.nuget.org/v3-flatcontainer/')
        assert package['notices'] or package.get('full_terms')
        for member in package['members']:
            assert member['path'] not in paths
            paths.add(member['path'])
            assert len(member['sha256']) == 64
        for term in ([package['full_terms']] if package.get('full_terms') else []) + package.get('extra_terms', []):
            assert term['sha256'] != hashlib.sha256(b'').hexdigest()
    assert 'toolchains/cyberpunk/reader/K4os.Compression.LZ4.dll' in paths
