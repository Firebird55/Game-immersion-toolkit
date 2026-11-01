"""Reject invalid native-probe evidence before invoking any executable."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_probe_normalizes_owned_temporary_root_before_fixed_game_commands(tmp_path, monkeypatch):
    """Runner temp aliases must not weaken the real runtime path requirement."""
    from backend.prebuilt_node_reader import ZzzReader
    temporary = tmp_path / 'temporary'
    (temporary / 'child').mkdir(parents=True)
    class TemporaryAlias:
        def __enter__(self): return str(temporary / 'child' / '..')
        def __exit__(self, *_): return False
    monkeypatch.setattr(probe.tempfile, 'TemporaryDirectory', lambda **_: TemporaryAlias())
    resource_roots = [tmp_path / 'zzz', tmp_path / 'node']
    for root in resource_roots:
        root.mkdir(); (root / 'resource-manifest.json').write_text('{}')
    monkeypatch.setattr(probe, 'read_resources', lambda _: (
        {'platform': probe.host_platform(), 'source_commit': 'a' * 40}, {}))
    monkeypatch.setattr(probe, 'production_zzz_reader', lambda *, layout: ZzzReader(
        layout.resource_root / 'node', layout.resource_root, 'authored', layout.work_root))
    calls = []
    def execute(command, **kwargs):
        calls.append(command)
        assert kwargs['cwd'] == kwargs['cwd'].resolve()
        if len(calls) == 1:
            return SimpleNamespace(returncode=0, stdout=b'{"checks":[]}')
        error = (b'No matching scene paths' if len(calls) == 2 else
                 b'Installed cinematic resource catalog was not found')
        return SimpleNamespace(returncode=1, stderr=error)
    monkeypatch.setattr(probe.subprocess, 'run', execute)
    result = probe.probe(*resource_roots)
    assert result['status'] == 'pass' and len(calls) == 3
    assert result['checks'][:2] == ['dialogue-compiler-free-entrypoint', 'cinematic-compiler-free-entrypoint']
