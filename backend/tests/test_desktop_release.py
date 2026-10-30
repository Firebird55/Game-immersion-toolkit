"""Authored release fixtures prove update validation, not native acceptance.

Network and protected storage are mocked. No account, release or real keychain
writes occur; fake approval labels exist solely inside temporary test receipts.
"""
import hashlib
import io
import json
from pathlib import Path
import threading
import zipfile

import pytest

from backend import desktop_release as release
from backend.runtime_bundle import RuntimeLayout, MANIFEST_SCHEMA
from backend.tests.test_desktop_packaging import payload, packaging
from backend.tests.test_desktop_frontend import build as frontend_build


def authored_release(tmp_path, monkeypatch):
    current = tmp_path / 'current'
    current.mkdir()
    root, receipt_path, receipt = payload(tmp_path)
    executable = 'ProxyTranscriptRuntime.exe'
    (current / executable).write_bytes((root / executable).read_bytes())
    settings = tmp_path / 'user'
    layout = RuntimeLayout(mode='bundle', application_root=current, resource_root=current / '_internal',
        executable=current / executable, settings_root=settings, data_root=settings / 'data',
        cache_root=settings / 'cache', tool_root=settings / 'tools', work_root=settings / 'work',
        state_root=settings / 'state', default_export_root=settings / 'exports', version='1.0.0', profile='runtime')
    frontend = frontend_build(root / '_internal/desktop')
    frontend['version'] = '1.2.3'
    (root / '_internal/desktop/desktop-manifest.json').write_text(json.dumps(frontend))
    manifest = dict(schema=MANIFEST_SCHEMA, source_commit='a' * 40, version='1.2.3', build_id='authored-fixture',
        profile='runtime', storage_epoch=1, host_protocol=1, children=['api', 'frontend', 'gateway'],
        resources={p.relative_to(root / '_internal').as_posix(): packaging.digest(p)
            for p in (root / '_internal/desktop').rglob('*') if p.is_file()})
    (root / '_internal/runtime-manifest.json').write_text(json.dumps(manifest))
    receipt.update({key: manifest[key] for key in ('source_commit', 'version', 'build_id', 'profile', 'storage_epoch', 'host_protocol')})
    receipt.update(r19_complete=False, release_eligible=True, redistribution_review='approved', native_acceptance='approved',
        files=[dict(path=p.relative_to(root).as_posix(), bytes=p.stat().st_size, sha256=packaging.digest(p))
            for p in sorted(root.rglob('*')) if p.is_file()],
        directories=[p.relative_to(root).as_posix() for p in sorted(root.rglob('*')) if p.is_dir()])
    receipt_path.write_text(json.dumps(receipt))
    output = tmp_path / 'distribution'
    summary = packaging.package(root, receipt_path, 'windows-x64', output)
    names = ['DESKTOP-PROVENANCE-windows-x64.json', summary['update_artifact']]
    assets = []
    responses = {}
    for name in names:
        raw = (output / name).read_bytes()
        url = release.DOWNLOAD + 'v1.2.3/' + name
        assets.append(dict(name=name, size=len(raw), digest='sha256:' + hashlib.sha256(raw).hexdigest(), browser_download_url=url))
        responses[url] = raw
    responses[release.API + '/releases/latest'] = json.dumps(dict(tag_name='v1.2.3', draft=False, prerelease=False, assets=assets)).encode()
    responses[release.API + '/git/ref/tags/v1.2.3'] = json.dumps(dict(object=dict(type='commit', sha='a' * 40))).encode()
    calls = []
    def fetch(url, limit, stop_event, destination=None):
        release._cancel(stop_event)
        calls.append(url)
        data = responses[url]
        assert len(data) <= limit
        if destination is not None:
            destination.write_bytes(data)
            return b''
        return data
    monkeypatch.setattr(release, '_fetch', fetch)
    # Authentication-like test envelope detects ticket mutations; not a crypto
    # substitute. The actual code always uses DPAPI/Keychain/SecretService.
    def protect(layout, raw, *, decrypt=False):
        if not decrypt:
            return hashlib.sha256(b'fixture-key' + raw).digest() + raw
        if hashlib.sha256(b'fixture-key' + raw[32:]).digest() != raw[:32]:
            raise RuntimeError('authored ticket authentication failed')
        return raw[32:]
    monkeypatch.setattr(release, '_protect', protect)
    return layout, summary, responses, calls


def test_update_stages_closed_native_slot_and_revalidates_offline(tmp_path, monkeypatch):
    layout, summary, responses, calls = authored_release(tmp_path, monkeypatch)
    stages = []
    selected = release.prepare_update(layout, '1.0.0', stages.append, threading.Event())
    assert selected.layout.version == '1.2.3'
    assert selected.frontend_root == selected.slot_root / '_internal/desktop'
    assert selected.layout.data_root == layout.data_root
    assert selected.layout.settings_root == layout.settings_root
    assert selected.receipt_digest == summary['runtime_receipt_sha256']
    assert not (layout.state_root / 'desktop-updates/active-slot.json').exists()
    before = len(calls)
    assert release.verify_selected(layout, selected.slot_root, selected.receipt_digest) == selected
    assert len(calls) == before  # no network or subprocess needed to restart
    assert release.prepare_update(layout, '1.0.0').slot_root == selected.slot_root
    assert not list(selected.slot_root.parent.glob('.incoming-*'))
    assert len(stages) == 3


@pytest.mark.parametrize('mutation', ['file', 'directory', 'ticket', 'missing-ticket', 'outside'])
def test_persisted_selection_cannot_bypass_integrity_or_os_ticket(tmp_path, monkeypatch, mutation):
    layout, _, _, _ = authored_release(tmp_path, monkeypatch)
    selected = release.prepare_update(layout, '1.0.0')
    slot = selected.slot_root
    if mutation == 'file':
        (slot / 'LICENSE').write_text('changed')
    elif mutation == 'directory':
        (slot / 'unexpected').mkdir()
    elif mutation == 'ticket':
        release._ticket_path(layout, selected.receipt_digest).write_bytes(b'forged')
    elif mutation == 'missing-ticket':
        release._ticket_path(layout, selected.receipt_digest).unlink()
    else:
        slot = tmp_path / 'unmanaged'
    with pytest.raises(release.DesktopReleaseError):
        release.verify_selected(layout, slot, selected.receipt_digest)


@pytest.mark.parametrize('mutation', ['asset-digest', 'wrong-tag', 'wrong-url', 'wrong-commit', 'bool-protocol', 'future-epoch', 'archive'])
def test_offered_payload_rejected_before_activation(tmp_path, monkeypatch, mutation):
    layout, summary, responses, _ = authored_release(tmp_path, monkeypatch)
    latest_url = release.API + '/releases/latest'
    latest = json.loads(responses[latest_url])
    metadata_url = latest['assets'][0]['browser_download_url']
    metadata = json.loads(responses[metadata_url])
    if mutation == 'asset-digest':
        latest['assets'][0]['digest'] = 'sha256:' + 'f' * 64
    elif mutation == 'wrong-tag':
        metadata['tag'] = 'v0.0.1'
    elif mutation == 'wrong-url':
        latest['assets'][0]['browser_download_url'] = 'https://evil.invalid/runtime.zip'
    elif mutation == 'wrong-commit':
        metadata['source_commit'] = 'b' * 40
    elif mutation == 'bool-protocol':
        metadata['host_protocol'] = True
    elif mutation == 'future-epoch':
        metadata['storage_epoch'] = 2
    else:
        responses[latest['assets'][1]['browser_download_url']] = b'corrupt'
    if mutation in ('wrong-tag', 'wrong-commit', 'bool-protocol', 'future-epoch'):
        raw = json.dumps(metadata).encode()
        responses[metadata_url] = raw
        latest['assets'][0].update(size=len(raw), digest='sha256:' + hashlib.sha256(raw).hexdigest())
    responses[latest_url] = json.dumps(latest).encode()
    with pytest.raises(release.DesktopReleaseError):
        release.prepare_update(layout, '1.0.0')
    assert not (layout.state_root / 'desktop-updates/active-slot.json').exists()
    assert not list(release._slots(layout).glob('1.2.3-*'))


def test_candidates_and_source_only_releases_do_not_offer_updates(tmp_path, monkeypatch):
    layout, _, responses, _ = authored_release(tmp_path, monkeypatch)
    latest = json.loads(responses[release.API + '/releases/latest'])
    metadata_asset = latest['assets'][0]
    metadata = json.loads(responses[metadata_asset['browser_download_url']])
    metadata.update(candidate=True, release_eligible=False)
    raw = json.dumps(metadata).encode()
    responses[metadata_asset['browser_download_url']] = raw
    metadata_asset.update(size=len(raw), digest='sha256:' + hashlib.sha256(raw).hexdigest())
    responses[release.API + '/releases/latest'] = json.dumps(latest).encode()
    assert release.prepare_update(layout, '1.0.0') is None
    latest['assets'] = []
    responses[release.API + '/releases/latest'] = json.dumps(latest).encode()
    assert release.prepare_update(layout, '1.0.0') is None


def test_cancelled_update_does_not_create_or_select_slot(tmp_path, monkeypatch):
    layout, _, _, calls = authored_release(tmp_path, monkeypatch)
    event = threading.Event(); event.set()
    with pytest.raises(release.DesktopReleaseError, match='cancelled'):
        release.prepare_update(layout, '1.0.0', stop_event=event)
    assert not calls
    assert not release._slots(layout).exists()


@pytest.mark.parametrize('name', ['../escape', 'tree/../escape', 'tree/CON', 'tree/x:stream', 'tree/x.', 'other/file'])
def test_archive_paths_cannot_escape_or_alias(tmp_path, name):
    archive = tmp_path / 'bad.zip'
    with zipfile.ZipFile(archive, 'w') as stream:
        stream.writestr(name, b'bad')
    root = tmp_path / 'tree'; root.mkdir()
    with pytest.raises((release.DesktopReleaseError, RuntimeError)):
        release._extract(archive, root, 'tree', None)
    assert not (tmp_path / 'escape').exists()


def test_protected_storage_failure_prevents_publishing_slot(tmp_path, monkeypatch):
    layout, _, _, _ = authored_release(tmp_path, monkeypatch)
    def unavailable(*args, **kwargs):
        raise RuntimeError('authored keychain unavailable')
    monkeypatch.setattr(release, '_protect', unavailable)
    with pytest.raises(release.DesktopReleaseError):
        release.prepare_update(layout, '1.0.0')
    assert not list(release._slots(layout).iterdir())


@pytest.mark.parametrize('kind', ['redirect', 'size', 'stream-overflow', 'cancel-midstream'])
def test_network_reader_enforces_supplier_bounds_and_cancellation(tmp_path, monkeypatch, kind):
    event = threading.Event()
    class Response(io.BytesIO):
        headers = {'Content-Length': '100'} if kind == 'size' else {}
        def geturl(self):
            return 'https://outside.invalid/payload' if kind == 'redirect' else 'https://release-assets.githubusercontent.com/payload'
        def read(self, size=-1):
            data = super().read(size)
            if kind == 'cancel-midstream':
                event.set()
            return data
    monkeypatch.setattr(release, 'urlopen', lambda *args, **kwargs: Response(b'123456789'))
    with pytest.raises(release.DesktopReleaseError):
        release._fetch(release.DOWNLOAD + 'v1.2.3/runtime.zip', 4, event, tmp_path / 'partial')


def test_cancel_after_verification_keeps_slot_unpublished(tmp_path, monkeypatch):
    layout, _, _, _ = authored_release(tmp_path, monkeypatch)
    event = threading.Event()
    original = release._protect
    def protected(*args, **kwargs):
        value = original(*args, **kwargs)
        event.set()
        return value
    monkeypatch.setattr(release, '_protect', protected)
    with pytest.raises(release.DesktopReleaseError, match='cancelled'):
        release.prepare_update(layout, '1.0.0', stop_event=event)
    assert not list(release._slots(layout).iterdir())
