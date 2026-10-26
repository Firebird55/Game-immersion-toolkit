"""The updater may execute code only after integrity and provenance checks."""
import hashlib
import json
from pathlib import Path
import zipfile

import pytest

from backend import toolkit_update as update


def release(tmp_path, extra=None):
    proof = {'version': '1.2.3', 'repository': update.REPOSITORY, 'sourceCommit': 'a' * 40}
    archive = tmp_path / 'Game-immersion-toolkit-1.2.3.zip'
    provenance = tmp_path / 'PROVENANCE.json'; provenance.write_text(json.dumps(proof))
    with zipfile.ZipFile(archive, 'w') as bundle:
        bundle.writestr('Game-immersion-toolkit-1.2.3/package.json', json.dumps({'name': 'game-immersion-toolkit', 'version': '1.2.3'}))
        bundle.writestr('Game-immersion-toolkit-1.2.3/PROVENANCE.json', json.dumps(proof))
        if extra:
            bundle.writestr(extra, 'must not escape')
    checksums = tmp_path / 'SHA256SUMS'
    checksums.write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name for p in (archive, provenance)))
    return archive, checksums, provenance


@pytest.mark.parametrize('failure', [None, 'checksum', 'commit', 'path'])
def test_only_complete_verified_release_can_be_extracted(tmp_path, failure):
    paths = release(tmp_path, 'Game-immersion-toolkit-1.2.3/../../outside' if failure == 'path' else None)
    if failure == 'checksum':
        paths[0].write_bytes(paths[0].read_bytes() + b'tampered')
    args = (*paths, tmp_path / 'output', 'v1.2.3', ('b' if failure == 'commit' else 'a') * 40)
    if failure:
        with pytest.raises(ValueError):
            update.verify_and_extract(*args)
        assert not (tmp_path / 'outside').exists()
    else:
        source = update.verify_and_extract(*args)
        assert update.read_json(source / 'package.json')['version'] == '1.2.3'


def test_offline_update_keeps_current_runtime_and_reports_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(update, 'request_json', lambda _: (_ for _ in ()).throw(OSError('offline')))
    monkeypatch.setattr(update.subprocess, 'run', lambda *args, **kwargs: pytest.fail('Offline update cannot install'))
    update.update_once(tmp_path, '1.0.0')
    status = update.read_json(tmp_path / 'data/toolkit-updates/status.json')
    assert status['state'] == 'error' and 'retained' in status['message']
    with update.update_lock(tmp_path / 'data/toolkit-updates/install.lock') as acquired:
        assert acquired, 'Failure must release the cross-process lock'


def test_older_release_never_downgrades_or_installs(tmp_path, monkeypatch):
    monkeypatch.setattr(update, 'request_json', lambda _: {'tag_name': 'v1.0.0'})
    monkeypatch.setattr(update, 'download', lambda *args: pytest.fail('No downgrade download'))
    update.update_once(tmp_path, '1.2.3')
    assert update.read_json(tmp_path / 'data/toolkit-updates/status.json')['state'] == 'current'
