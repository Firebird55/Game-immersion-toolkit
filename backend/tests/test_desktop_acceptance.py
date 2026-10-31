"""Synthetic acceptance evidence tests the gate, never claims a native pass."""
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path

import pytest

from backend.tests.test_desktop_packaging import payload, packaging

spec = spec_from_file_location('desktop_acceptance', Path(__file__).resolve().parents[2] / 'scripts/accept-desktop-runtime.py')
acceptance = module_from_spec(spec)
spec.loader.exec_module(acceptance)


def authored_evidence(tmp_path):
    root, provenance, receipt = payload(tmp_path)
    receipt['profile'] = 'runtime'
    manifest = root / '_internal/runtime-manifest.json'
    value = json.loads(manifest.read_text())
    value['profile'] = 'runtime'
    manifest.write_text(json.dumps(value))
    for item in receipt['files']:
        path = root / item['path']
        item.update(bytes=path.stat().st_size, sha256=packaging.digest(path))
    receipt['directories'] = sorted(p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_dir())
    provenance.write_text(json.dumps(receipt))
    identity = {key: receipt[key] for key in ('source_commit', 'build_id')}
    identity.update(target='windows-x64', runtime_receipt_sha256=packaging.digest(provenance))
    review = dict(schema='toolkit-desktop-input-review-v1', **identity, approved=True,
        file_inventory_sha256=acceptance.inventory_digest(receipt), checks={key: True for key in acceptance.INPUT_CHECKS},
        capabilities={'fixture-ocr': 'available', 'fixture-game': 'requires-installed-pack'})
    native = dict(schema='toolkit-desktop-native-probe-v1', **identity,
        passed=True, execution='actual-frozen-process', checks={key: True for key in acceptance.NATIVE_CHECKS})
    review_path, native_path = tmp_path / 'authored-review.json', tmp_path / 'authored-native.json'
    review_path.write_text(json.dumps(review))
    native_path.write_text(json.dumps(native))
    return root, provenance, review_path, native_path


def test_target_acceptance_preserves_bytes_and_incomplete_r19(tmp_path):
    root, provenance, review, native = authored_evidence(tmp_path)
    before = {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    result = acceptance.accept(root, provenance, 'windows-x64', review, [native], tmp_path / 'accepted.json')
    assert result['release_eligible'] is True
    assert result['r19_complete'] is False
    assert result['signing'] == 'unsigned'
    assert packaging.validate(root, result, 'windows-x64')
    assert before == {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    assert json.loads(provenance.read_text())['native_acceptance'] == 'unavailable'


@pytest.mark.parametrize('mutation', ['receipt', 'target', 'source', 'build', 'unavailable', 'headless-only', 'simulated', 'sources', 'inventory', 'extra-file'])
def test_partial_or_stale_evidence_cannot_promote(tmp_path, mutation):
    root, provenance, review_path, native_path = authored_evidence(tmp_path)
    native, review = json.loads(native_path.read_text()), json.loads(review_path.read_text())
    if mutation == 'receipt':
        native['runtime_receipt_sha256'] = '0' * 64
    elif mutation == 'target':
        native['target'] = 'linux-x64'
    elif mutation == 'source':
        native['source_commit'] = 'b' * 40
    elif mutation == 'build':
        native['build_id'] = 'different'
    elif mutation == 'unavailable':
        native['checks']['tray_icon'] = 'unavailable'
    elif mutation == 'headless-only':
        del native['checks']['browser_open']
    elif mutation == 'simulated':
        native['execution'] = 'mocked-process'
    elif mutation == 'sources':
        review['checks']['corresponding_sources'] = False
    elif mutation == 'inventory':
        review['file_inventory_sha256'] = '0' * 64
    elif mutation == 'extra-file':
        (root / 'unreviewed.dll').write_bytes(b'fixture')
    native_path.write_text(json.dumps(native))
    review_path.write_text(json.dumps(review))
    with pytest.raises(packaging.PackageError):
        acceptance.accept(root, provenance, 'windows-x64', review_path, [native_path], tmp_path / 'accepted.json')
    assert not (tmp_path / 'accepted.json').exists()
