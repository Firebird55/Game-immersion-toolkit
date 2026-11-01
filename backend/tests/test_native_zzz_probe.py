"""Reject invalid native-probe evidence before invoking any executable."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('native_zzz_probe', ROOT / 'scripts/probe-native-zzz.py')
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)


def fixture(tmp_path):
    (tmp_path / 'authored.txt').write_bytes(b'authored')
    value = {'schema': 'toolkit-native-resources-v1', 'source_dirty': False,
             'source_commit': 'a' * 40, 'platform': 'win-x64', 'files': [
        {'path': 'authored.txt', 'bytes': 8, 'sha256': probe.digest(b'authored')}]}
    (tmp_path / 'resource-manifest.json').write_text(json.dumps(value))
    return value


def test_probe_requires_exact_resource_bytes(tmp_path):
    fixture(tmp_path)
    _, files = probe.read_resources(tmp_path)
    assert files == {'authored.txt': tmp_path / 'authored.txt'}
    (tmp_path / 'authored.txt').write_bytes(b'tampered')
    with pytest.raises(ValueError, match='differs'):
        probe.read_resources(tmp_path)


@pytest.mark.parametrize('change', ['dirty', 'duplicate', 'outside'])
def test_probe_refuses_dirty_duplicate_and_escaping_resource_inventory(tmp_path, change):
    value = fixture(tmp_path)
    if change == 'dirty': value['source_dirty'] = True
    elif change == 'duplicate': value['files'].append(value['files'][0])
    else: value['files'][0]['path'] = '../outside'
    (tmp_path / 'resource-manifest.json').write_text(json.dumps(value))
    with pytest.raises((ValueError, RuntimeError)):
        probe.read_resources(tmp_path)
