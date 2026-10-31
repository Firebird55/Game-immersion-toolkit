"""The updater may execute code only after integrity and provenance checks."""
import hashlib
import json
from pathlib import Path
import zipfile
from types import SimpleNamespace

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


@pytest.fixture
def managed_updater(tmp_path, monkeypatch):
    monkeypatch.setenv('PROXY_TRANSCRIPT_HOST_MANAGED', '1')
    layout = SimpleNamespace(mode='bundle', version='1.2.3', state_root=tmp_path / 'state')
    monkeypatch.setattr(update, 'discover_layout', lambda: layout)
    monkeypatch.setattr(update.subprocess, 'Popen', lambda *_a, **_k: pytest.fail('API must not detach an updater'))
    return update.ToolkitUpdater(tmp_path / 'immutable-app')


def test_managed_api_forwards_updates_without_own_monitor_or_capability_leak(managed_updater, monkeypatch):
    updater, calls = managed_updater, []
    monkeypatch.setattr(update.desktop_control, 'host_status', lambda **kwargs: {
        'state': 'current', 'message': 'Up to date', 'enabled': True, 'supported': True,
        'installed_version': '0.0.1', 'token': 'private-test-capability', 'port': 12345})
    def request(**kwargs):
        calls.append(('request', kwargs['layout']))
        return {'started': True}
    monkeypatch.setattr(update.desktop_control, 'request_update', request)
    monkeypatch.setattr(update.desktop_control, 'configure_updates',
        lambda enabled, **kwargs: calls.append(('preferences', enabled, kwargs['layout'])))
    updater.start()
    assert updater.thread is None
    assert updater.status() == {'state': 'current', 'message': 'Up to date', 'enabled': True,
        'supported': True, 'installed_version': '1.2.3'}
    assert updater.request() is True
    updater.configure(False)
    assert calls == [('request', updater.layout), ('preferences', False, updater.layout)]
    assert not updater.root.exists(), 'The API must not write inside an immutable application'
    updater.close()


def test_host_failure_is_actionable_and_does_not_start_source_update(managed_updater, monkeypatch):
    def unavailable(**kwargs):
        raise update.desktop_control.HostControlError('Keep the desktop launcher open.')
    monkeypatch.setattr(update.desktop_control, 'host_status', unavailable)
    monkeypatch.setattr(update.desktop_control, 'request_update', unavailable)
    assert managed_updater.status() == {'state': 'error', 'message': 'Keep the desktop launcher open.',
        'installed_version': '1.2.3', 'enabled': False, 'supported': False}
    with pytest.raises(update.desktop_control.HostControlError):
        managed_updater.request()
    assert not managed_updater.root.exists()


@pytest.mark.parametrize('action,body', [('check', {}), ('preferences', {'enabled': True})])
def test_update_api_reports_host_failure_without_unhandled_error(managed_updater, monkeypatch, action, body):
    from fastapi.testclient import TestClient
    from backend import api
    def unavailable(*args, **kwargs):
        raise update.desktop_control.HostControlError('Keep the desktop launcher open.')
    monkeypatch.setattr(update.desktop_control, 'request_update', unavailable)
    monkeypatch.setattr(update.desktop_control, 'configure_updates', unavailable)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(toolkit_updater=managed_updater, standby=False), raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8766')
    assert client.post('/api/toolkit-update/' + action, json=body).status_code == 403
    response = client.post('/api/toolkit-update/' + action, json=body, headers={'X-Proxy-Transcript': 'setup'})
    assert response.status_code == 503
    assert response.json()['detail'] == 'Keep the desktop launcher open.'
