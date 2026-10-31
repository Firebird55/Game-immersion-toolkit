"""Static runtime regressions that a development server cannot detect.

Authored public bytes only. These prove manifest/HTTP isolation and old-chunk
availability, not a real profile, native capture or all frontend equivalence.
"""
from contextlib import contextmanager
from dataclasses import replace
import hashlib
import http.client
import json
from pathlib import Path
import threading
from types import SimpleNamespace

import pytest

from backend.desktop_frontend import (API_BASE, FRONTEND_ORIGIN, WEBSOCKET_URL, DesktopFrontendServer,
                                      FrontendBuild, FrontendError, build_identity)
from backend.runtime_bundle import EXPERIMENT_CHILDREN, RuntimeLayout


def build(root: Path, extra=None, *, omit=()):
    root.mkdir()
    content = {'index.html': (b'<!doctype html><title>owned fixture</title>', 'text/html; charset=utf-8'),
               'assets/entry-12345678.js': (b'export const fixture=true;', 'text/javascript; charset=utf-8'),
               'mobile-capture/worker.mjs': (b'postMessage("owned fixture");', 'text/javascript; charset=utf-8'),
               'mobile-capture/index.html': (b'<!doctype html><title>mobile fixture</title>', 'text/html; charset=utf-8'),
               'mobile-capture/core.wasm': (b'\0asm\1\0\0\0', 'application/wasm')}
    content.update(extra or {})
    for name in omit:
        content.pop(name)
    files = {}
    for name, (data, mime) in content.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        files[name] = {'bytes': len(data), 'mime': mime, 'sha256': hashlib.sha256(data).hexdigest()}
    value = {'schema': 'proxy-desktop-frontend-v1', 'runtime': 'static-local-no-node', 'source_commit': 'a' * 40,
             'version': '0.22.0', 'source_fingerprint': 'b' * 64, 'lock_sha256': 'c' * 64,
             'frontend_origin': FRONTEND_ORIGIN, 'api_base': API_BASE, 'websocket_url': WEBSOCKET_URL,
             'entry': 'index.html', 'routes': ['/'], 'build_id': build_identity(files), 'files': files}
    (root / 'desktop-manifest.json').write_text(json.dumps(value), encoding='utf-8')
    return value


@contextmanager
def host(root, retained=()):
    server = DesktopFrontendServer(root, 0, retained_roots=retained)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_port
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def request(port, path='/', *, method='GET', headers=()):
    connection = http.client.HTTPConnection('127.0.0.1', port, timeout=3)
    try:
        connection.putrequest(method, path, skip_host=True)
        for key, value in headers or [('Host', f'127.0.0.1:{port}')]:
            connection.putheader(key, value)
        connection.endheaders()
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def test_serves_own_bytes_queries_head_worker_wasm_csp_and_etags_without_data_writes(tmp_path, monkeypatch):
    root = tmp_path / 'Application 中文'; build(root)
    before = {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()}
    unrelated = tmp_path / 'unrelated'; unrelated.mkdir(); monkeypatch.chdir(unrelated)
    with host(root) as port:
        status, headers, data = request(port, '/?view=reader')
        assert status == 200 and b'owned fixture' in data
        assert headers['Cache-Control'] == 'no-store'
        assert "'wasm-unsafe-eval'" in headers['Content-Security-Policy']
        assert "'unsafe-eval'" not in headers['Content-Security-Policy']
        assert request(port, '/', method='HEAD')[2] == b''
        assert b'mobile fixture' in request(port, '/mobile-capture/?pc=1&game=zzz')[2]
        status, headers, data = request(port, '/mobile-capture/core.wasm')
        assert status == 200 and headers['Content-Type'] == 'application/wasm' and data.startswith(b'\0asm')
        assert request(port, '/mobile-capture/worker.mjs')[1]['Content-Type'].startswith('text/javascript')
        _, headers, _ = request(port, '/assets/entry-12345678.js')
        assert 'immutable' in headers['Cache-Control']
        assert request(port, '/assets/entry-12345678.js', headers=[('Host', '127.0.0.1'), ('If-None-Match', headers['ETag'])])[0] == 304
        (root / 'assets/entry-12345678.js').write_bytes(b'changed after startup')
        assert request(port, '/assets/entry-12345678.js')[0] == 503
        (root / 'assets/entry-12345678.js').write_bytes(before[Path('assets/entry-12345678.js')])
    assert {p.relative_to(root): p.read_bytes() for p in root.rglob('*') if p.is_file()} == before
    assert list(unrelated.iterdir()) == []


@pytest.mark.parametrize('headers', [
    [('Host', 'example.test')], [('Host', '127.0.0.1'), ('Host', 'localhost')],
    [('Host', '127.0.0.1'), ('Origin', 'null')],
    [('Host', '127.0.0.1'), ('Origin', 'http://127.0.0.1:3000'), ('Origin', 'https://example.test')],
    [('Host', '127.0.0.1'), ('Origin', 'http://localhost.example.test:3000')],
])
def test_exact_local_access_rejects_host_and_origin_before_static_dispatch(tmp_path, headers):
    root = tmp_path / 'app'; build(root)
    with host(root) as port:
        assert request(port, headers=headers)[0] == 403


def test_no_api_proxy_directory_listing_private_files_or_mutating_routes(tmp_path):
    root = tmp_path / 'app'; build(root)
    (tmp_path / 'private.db').write_bytes(b'private fixture must not be served')
    with host(root) as port:
        for name in ('/api/snapshot', '/desktop-manifest.json', '/assets/', '/../private.db', '/%2e%2e/private.db', '/assets/%zz', '/%00'):
            assert request(port, name)[0] == 404
        assert request(port, '/', method='POST')[0] == 405


def test_retains_old_hashes_but_does_not_resurrect_old_mutable_routes(tmp_path):
    old, current = tmp_path / 'old', tmp_path / 'current'
    build(old, {'assets/prior-abcdefgh.js': (b'owned prior chunk', 'text/javascript; charset=utf-8'),
                '_next/static/chunks/XKyaHtl9.js': (b'owned bare chunk', 'text/javascript; charset=utf-8'),
                'mobile-capture/retired.mjs': (b'old mutable module', 'text/javascript; charset=utf-8')})
    build(current)
    with host(current, (old,)) as port:
        assert request(port, '/assets/prior-abcdefgh.js')[2] == b'owned prior chunk'
        assert request(port, '/_next/static/chunks/XKyaHtl9.js')[2] == b'owned bare chunk'
        assert request(port, '/mobile-capture/retired.mjs')[0] == 404
    conflict = tmp_path / 'collision'; build(conflict, {'assets/entry-12345678.js': (b'wrong same URL', 'text/javascript; charset=utf-8')})
    with pytest.raises(FrontendError, match='collide'):
        DesktopFrontendServer(current, 0, retained_roots=(conflict,))


def test_manifest_and_tree_tampering_fail_before_opening_listener(tmp_path):
    root = tmp_path / 'app'; value = build(root)
    (root / 'unlisted.txt').write_bytes(b'unlisted')
    with pytest.raises(FrontendError, match='closed manifest'):
        FrontendBuild(root)
    (root / 'unlisted.txt').unlink()
    value['files']['index.html']['sha256'] = '0' * 64
    (root / 'desktop-manifest.json').write_text(json.dumps(value))
    with pytest.raises(FrontendError, match='build identity'):
        FrontendBuild(root)


@pytest.mark.parametrize('change', ['empty-private-directory', 'missing-fingerprint', 'wrong-wasm-mime'])
def test_incomplete_identity_and_nonpublic_or_mistyped_tree_fail_closed(tmp_path, change):
    root = tmp_path / 'app'; value = build(root)
    if change == 'empty-private-directory':
        (root / 'data').mkdir()
    elif change == 'missing-fingerprint':
        del value['source_fingerprint']
    else:
        value['files']['mobile-capture/core.wasm']['mime'] = 'text/html; charset=utf-8'
        value['build_id'] = build_identity(value['files'])
    (root / 'desktop-manifest.json').write_text(json.dumps(value))
    with pytest.raises(FrontendError):
        FrontendBuild(root)


def test_linked_frontend_or_private_native_resource_is_rejected(tmp_path):
    root = tmp_path / 'app'; build(root)
    link = tmp_path / 'linked'
    try:
        link.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip('Host cannot create a symbolic-link fixture')
    with pytest.raises(FrontendError, match='links'):
        FrontendBuild(link)
    forbidden = tmp_path / 'native'
    build(forbidden, {'assets/oneocr.onemodel': (b'owned negative fixture', 'application/octet-stream')})
    with pytest.raises(FrontendError, match='nonpublic'):
        FrontendBuild(forbidden)


def immutable_slot(tmp_path, name, extra=None, *, omit=()):
    """Authored frontend subset, with an independently retained runtime pin.

    No native executable/provenance eligibility or real slot migration is
    supplied by this fixture.
    """
    application = tmp_path / ('slot-' + name)
    resources = application / '_internal'
    resources.mkdir(parents=True)
    frontend = resources / 'desktop'
    build(frontend, extra, omit=omit)
    hashes = {path.relative_to(resources).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
              for path in frontend.rglob('*') if path.is_file()}
    manifest = {'schema': 'proxy-runtime-bundle-v1', 'profile': 'runtime-experiment',
        'version': '0.22.0', 'source_commit': 'a' * 40, 'build_id': 'authored-' + name,
        'resources': hashes, 'children': list(EXPERIMENT_CHILDREN)}
    raw = json.dumps(manifest).encode()
    (resources / 'runtime-manifest.json').write_bytes(raw)
    private = tmp_path / ('private-' + name)
    layout = RuntimeLayout(mode='bundle', application_root=application, resource_root=resources,
        executable=application / 'ProxyTranscriptRuntime.exe',
        settings_root=private, data_root=private / 'data-v1', cache_root=private / 'cache-v1',
        work_root=private / 'cache-v1/work', tool_root=private / 'tools-v1',
        state_root=private / 'host-v1', default_export_root=private / 'exports',
        version=manifest['version'], source_commit=manifest['source_commit'],
        build_id=manifest['build_id'], resources=hashes, children=EXPERIMENT_CHILDREN,
        profile=manifest['profile'])
    return layout, hashlib.sha256(raw).hexdigest()


@contextmanager
def slot_host(current, retired=()):
    server = DesktopFrontendServer.from_experimental_slots(*current, retired_slots=retired)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
        assert not thread.is_alive()


def test_pinned_slots_retain_vite_next_get_head_etag_and_reject_mutable_or_unknown_old_paths(tmp_path):
    retired = immutable_slot(tmp_path, 'old', {
        'index.html': (b'old authored index', 'text/html; charset=utf-8'),
        'assets/lazy-abcdefgh.js': (b'owned lazy Vite chunk', 'text/javascript; charset=utf-8'),
        '_next/static/chunks/OldChunk.js': (b'owned Next chunk', 'text/javascript; charset=utf-8'),
        'mobile-capture/old.mjs': (b'old mutable module', 'text/javascript; charset=utf-8')})
    current = immutable_slot(tmp_path, 'current')
    with slot_host(current, (retired,)) as server:
        port = server.server_port
        assert port not in (0, 3000, 8766)
        assert b'owned fixture' in request(port)[2]
        path = '/assets/lazy-abcdefgh.js'
        status, headers, body = request(port, path + '?cache=old')
        assert status == 200 and body == b'owned lazy Vite chunk'
        assert headers['Content-Type'] == 'text/javascript; charset=utf-8'
        assert 'immutable' in headers['Cache-Control']
        status, head, body = request(port, path, method='HEAD')
        assert status == 200 and not body and head['Content-Length'] == str(len(b'owned lazy Vite chunk'))
        assert request(port, path, headers=[('Host', '127.0.0.1'), ('If-None-Match', headers['ETag'])])[0] == 304
        assert request(port, '/_next/static/chunks/OldChunk.js')[2] == b'owned Next chunk'
        for path in ('/mobile-capture/old.mjs', '/assets/unknown-abcdefgh.js', '/desktop-manifest.json',
                     '/../private.db', '/assets/%2e%2e/private.db', '/assets/lazy-abcdefgh.js:stream'):
            assert request(port, path)[0] == 404
        assert request(port, '/assets/lazy-abcdefgh.js', method='POST')[0] == 405
        # Manifest pins are construction checks, not a live root selector. New
        # manifest contents cannot amend the server's captured resource map.
        root = retired[0].resource_root
        unbound = root / 'desktop/assets/unbound-abcdefgh.js'
        unbound.write_bytes(b'unbound post-start bytes')
        (root / 'runtime-manifest.json').write_text('{"retained_root":"untrusted replacement"}')
        (root / 'desktop/desktop-manifest.json').write_text(json.dumps({'files': {
            'assets/unbound-abcdefgh.js': {'bytes': unbound.stat().st_size,
                'sha256': hashlib.sha256(unbound.read_bytes()).hexdigest(), 'mime': 'text/javascript; charset=utf-8'}}}))
        assert request(port, '/assets/unbound-abcdefgh.js')[0] == 404
        assert request(port, '/assets/lazy-abcdefgh.js')[2] == b'owned lazy Vite chunk'
        (retired[0].resource_root / 'desktop/assets/lazy-abcdefgh.js').write_bytes(b'changed retired bytes')
        assert request(port, '/assets/lazy-abcdefgh.js')[0] == 503


@pytest.mark.parametrize('change', ['pin', 'layout', 'production', 'source', 'desktop-pin',
    'resource-pin', 'missing-resource', 'extra-file', 'extra-directory', 'duplicate-runtime-key'])
def test_slot_binding_refuses_untrusted_or_changed_subset_before_listener(tmp_path, monkeypatch, change):
    current = immutable_slot(tmp_path, 'current')
    layout, trusted_pin = immutable_slot(tmp_path, 'old')
    manifest_path = layout.resource_root / 'runtime-manifest.json'
    if change == 'pin': trusted_pin = '0' * 64
    elif change == 'layout': layout = replace(layout, build_id='unbound-owner-value')
    elif change == 'production': layout = replace(layout, profile='runtime')
    elif change == 'source': layout = {'resource_root': str(layout.resource_root)}
    elif change in ('desktop-pin', 'resource-pin', 'missing-resource'):
        resources = dict(layout.resources)
        name = 'desktop/desktop-manifest.json' if change == 'desktop-pin' else 'desktop/assets/entry-12345678.js'
        if change == 'missing-resource': del resources[name]
        else: resources[name] = '0' * 64
        manifest = json.loads(manifest_path.read_bytes()); manifest['resources'] = resources
        raw = json.dumps(manifest).encode(); manifest_path.write_bytes(raw)
        trusted_pin = hashlib.sha256(raw).hexdigest()
        layout = replace(layout, resources=resources)
    elif change == 'extra-file': (layout.resource_root / 'desktop/unlisted.txt').write_bytes(b'unlisted')
    elif change == 'extra-directory': (layout.resource_root / 'desktop/private-data').mkdir()
    else:
        raw = manifest_path.read_bytes().replace(b'{', b'{"profile":"runtime",', 1)
        manifest_path.write_bytes(raw); trusted_pin = hashlib.sha256(raw).hexdigest()
    def forbidden_listener(*_args, **_kwargs):
        pytest.fail('Rejected slot must not open a listener')
    monkeypatch.setattr('backend.desktop_frontend.ThreadingHTTPServer.__init__', forbidden_listener)
    with pytest.raises(FrontendError):
        DesktopFrontendServer.from_experimental_slots(*current, retired_slots=((layout, trusted_pin),))


@pytest.mark.parametrize('case_alias', [False, True])
def test_cross_slot_immutable_conflict_is_refused_before_listener(tmp_path, monkeypatch, case_alias):
    current = immutable_slot(tmp_path, 'current')
    name = 'assets/ENTRY-12345678.js' if case_alias else 'assets/entry-12345678.js'
    retired = immutable_slot(tmp_path, 'conflict', {name: (b'conflicting old chunk', 'text/javascript; charset=utf-8')},
        omit=('assets/entry-12345678.js',) if case_alias else ())
    monkeypatch.setattr('backend.desktop_frontend.ThreadingHTTPServer.__init__',
        lambda *_a, **_k: pytest.fail('Conflicting slots must not open a listener'))
    with pytest.raises(FrontendError, match='collide'):
        DesktopFrontendServer.from_experimental_slots(*current, retired_slots=(retired,))


def test_slot_adapter_bound_retention_limit_and_frozen_cli_gate_remain_closed(tmp_path, monkeypatch):
    from backend.desktop_frontend import frontend_root
    current = immutable_slot(tmp_path, 'current')
    with pytest.raises(FrontendError, match='Too many'):
        DesktopFrontendServer.from_experimental_slots(*current, retired_slots=(current,) * 17)
    args = SimpleNamespace(root=None, retained_root=[current[0].resource_root / 'desktop'])
    with pytest.raises(FrontendError, match='reviewed update supervisor'):
        frontend_root(args, current[0])


def test_retired_slot_link_and_post_start_reparse_refuse_original_bytes(tmp_path):
    current = immutable_slot(tmp_path, 'current')
    retired = immutable_slot(tmp_path, 'old', {'assets/lazy-abcdefgh.js': (b'owned prior chunk', 'text/javascript; charset=utf-8')})
    target = retired[0].resource_root / 'desktop/assets/lazy-abcdefgh.js'
    outside = tmp_path / 'outside.js'; outside.write_bytes(b'owned prior chunk')
    with slot_host(current, (retired,)) as server:
        try:
            target.unlink(); target.symlink_to(outside)
        except OSError:
            pytest.skip('Host cannot create a symbolic-link fixture')
        assert request(server.server_port, '/assets/lazy-abcdefgh.js')[0] == 503
    with pytest.raises(FrontendError, match='links'):
        DesktopFrontendServer.from_experimental_slots(*current, retired_slots=(retired,))
