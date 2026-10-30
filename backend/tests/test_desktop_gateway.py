"""The LAN boundary must never turn loopback APIs into anonymous network APIs."""
import json

import httpx
import pytest
from starlette.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.desktop_gateway import DesktopGateway, Pairing, RuntimeRoutes, allowed_request

ADDRESS = '192.168.1.20'
BASE = f'http://{ADDRESS}:3000'


@pytest.fixture
def gateway(tmp_path):
    state = tmp_path / 'runtime.json'
    state.write_text(json.dumps({'active': {'apiPort': 18766, 'frontendPort': 13000}}))
    calls = []

    def upstream(request):
        calls.append(request)
        return httpx.Response(206, stream=httpx.ByteStream(b'original voice'), headers={
            'Content-Type': 'audio/wav', 'Content-Range': 'bytes 0-13/14'})

    instance = DesktopGateway(RuntimeRoutes(state), addresses=lambda: {ADDRESS},
                              transport=httpx.MockTransport(upstream))
    return instance, calls


def client_for(instance, local=False, **kwargs):
    return TestClient(instance.app, base_url='http://127.0.0.1:3000' if local else BASE,
                      client=('127.0.0.1' if local else '192.168.1.30', 23456), **kwargs)


def test_phone_pairing_shares_reader_audio_and_favorites_without_revealing_code(gateway):
    instance, calls = gateway
    with client_for(instance, local=True) as client:
        invitation = client.get('/api/connection').json()
        assert invitation['urls'] == [BASE]
        assert len(invitation['code']) == 6
    with client_for(instance) as client:
        assert 'Connect to desktop' in client.get('/').text
        assert client.get('/api/connection').json() == {'local': False, 'paired': False}
        assert client.get('/api/lines').status_code == 401
        response = client.post('/api/connection/pair', json={'code': invitation['code']}, headers={'Origin': BASE})
        assert response.status_code == 200
        assert 'HttpOnly' in response.headers['set-cookie']
        assert 'SameSite=strict' in response.headers['set-cookie']
        voice = client.get('/api/lines/42/audio', headers={'Range': 'bytes=0-13', 'Origin': BASE})
        assert voice.status_code == 206 and voice.content == b'original voice'
        assert voice.headers['content-range'] == 'bytes 0-13/14'
        assert voice.headers['x-proxy-transcript-upstream-port'] == '18766'
        assert calls[-1].headers['Range'] == 'bytes=0-13'
        assert calls[-1].url.host == '127.0.0.1' and calls[-1].url.port == 18766
        assert 'cookie' not in calls[-1].headers and 'origin' not in calls[-1].headers
        assert client.patch('/api/lines/42/favorite', json={'favorite': True}, headers={'Origin': BASE}).status_code == 206
        assert calls[-1].read() == b'{"favorite":true}'
        # An atomic route change preserves the phone's authentication cookie.
        instance.routes.path.write_text(json.dumps({'active': {'apiPort': 18767, 'frontendPort': 13001}}))
        instance.routes.refresh()
        assert client.get('/api/lines').status_code == 206
        assert calls[-1].url.port == 18767
        assert client.get('/').status_code == 206
        assert calls[-1].url.port == 13001


def test_installed_localhost_reader_keeps_cors_access(gateway):
    instance, calls = gateway
    with client_for(instance, local=True) as client:
        origin = 'http://localhost:3000'
        response = client.options('/api/settings', headers={'Origin': origin,
            'Access-Control-Request-Method': 'PATCH', 'Access-Control-Request-Headers':
                'content-type,x-proxy-transcript,x-proxy-transcript-account,x-proxy-transcript-export-scope'})
        assert response.status_code == 200
        assert response.headers['access-control-allow-origin'] == origin
        response = client.patch('/api/settings', json={}, headers={'Origin': origin,
            'X-Proxy-Transcript': 'setup', 'X-Proxy-Transcript-Account': 'mock-account',
            'X-Proxy-Transcript-Export-Scope': 'mock-export'})
        assert response.status_code == 206
        assert response.headers['access-control-allow-origin'] == origin
        assert 'origin' not in calls[-1].headers
        assert calls[-1].headers['x-proxy-transcript-account'] == 'mock-account'
        assert calls[-1].headers['x-proxy-transcript-export-scope'] == 'mock-export'
        assert calls[-1].headers['x-proxy-transcript'] == 'setup'
        assert client.get('/api/lines', headers={'Origin': 'https://evil.example'}).status_code == 403


@pytest.mark.parametrize('path', ['/api/lines', '/api/capture/preview.jpg', '/api/setup', '/api/lexirise/accounts'])
def test_unpaired_requests_and_forged_cookies_never_reach_backend(gateway, path):
    instance, calls = gateway
    with client_for(instance, cookies={'toolkit_device': 'forged'}) as client:
        assert client.get(path).status_code == 401
        assert client.get(path, headers={'X-Forwarded-For': '127.0.0.1'}).status_code == 401
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect('/api/ws', headers={'Origin': BASE}):
                pytest.fail('Unpaired WebSocket accepted')
        assert error.value.code == 1008
    assert not calls


@pytest.mark.parametrize('headers', [
    {'Origin': 'https://evil.example'}, {'Origin': 'null'}, {'Origin': ''},
    {'Host': 'desktop.evil.example:3000'}, {'Host': '192.168.1.20.evil.example:3000'},
    {'Host': '127.0.0.1:3000'}, {'Host': '192.168.1.99:3000'},
    {'Host': '192.168.1.20:65536'}, {'Host': '192.168.1.20:0'},
])
def test_remote_host_origin_checks_precede_pairing_and_backend(gateway, headers):
    instance, calls = gateway
    with client_for(instance) as client:
        assert client.get('/api/connection', headers=headers).status_code == 403
        assert client.post('/api/connection/pair', json={'code': instance.pairing.invitation()}, headers=headers).status_code == 403
    assert not calls


def test_raw_duplicate_headers_and_remote_originless_writes_are_rejected():
    scope = {'type': 'http', 'method': 'POST', 'client': ('192.168.1.30', 23456),
             'headers': [(b'host', b'192.168.1.20:3000'), (b'origin', BASE.encode())]}
    assert allowed_request(scope, {ADDRESS})
    for extra in [(b'host', b'192.168.1.20:3000'), (b'origin', BASE.encode())]:
        assert not allowed_request({**scope, 'headers': [*scope['headers'], extra]}, {ADDRESS})
    assert not allowed_request({**scope, 'headers': scope['headers'][:1]}, {ADDRESS})


def test_connected_phone_cannot_replace_account_keys_or_change_runtime_ownership(gateway):
    instance, calls = gateway
    with client_for(instance) as client:
        assert client.post('/api/connection/pair', json={'code': instance.pairing.invitation()}, headers={'Origin': BASE}).status_code == 200
        for path in ['/api/runtime/quiesce', '/api/runtime%2Factivate', '/api/lexirise/key', '/api/lexirise/accounts/select']:
            assert client.post(path, headers={'Origin': BASE, 'X-Proxy-Transcript': 'update'}).status_code == 403
        assert client.post('/api/capture/stop', headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.post('/api/capture/stop').status_code == 403
    assert not calls


def test_expired_codes_session_expiry_and_rate_limits():
    now = [0]
    pairing = Pairing(clock=lambda: now[0])
    code = pairing.invitation()
    token, status = pairing.pair(code, 'phone')
    assert status == 200
    headers = [(b'cookie', ('toolkit_device=' + token).encode())]
    now[0] = 601
    assert pairing.pair(code, 'phone')[1] == 403
    assert pairing.authenticated(headers)
    new_code = pairing.invitation()
    assert pairing.pair(new_code, 'phone')[1] == 200
    for _ in range(6):
        pairing.pair('wrong', 'attacker')
    assert pairing.pair(new_code, 'attacker')[1] == 429
    now[0] = 86401
    assert not pairing.authenticated(headers)


def test_large_pairing_request_and_protected_files_are_not_served(gateway, tmp_path):
    instance, calls = gateway
    instance.assets = tmp_path / 'assets'
    instance.assets.mkdir()
    (tmp_path / 'private.js').write_text('private')
    (instance.assets / 'old-reader.js').write_text('retained reader')
    with client_for(instance, local=True) as client:
        assert client.post('/api/connection/pair', content=b'x' * 129).status_code == 413
        assert client.get('/_next/static/old-reader.js').text == 'retained reader'
    assert instance.cached_asset('/_next/static/../private.js') is None
    assert instance.cached_asset('/_next/static/..\\private.js') is None
    assert instance.cached_asset('/_next/static/C:/private.js') is None


def test_broken_route_update_keeps_previous_target(gateway):
    instance, calls = gateway
    with client_for(instance, local=True) as client:
        client.get('/api/health')
        for value in ['{incomplete', json.dumps({'active': {'apiPort': 8766, 'frontendPort': 3000}}),
                      json.dumps({'active': {'apiPort': '18766', 'frontendPort': 13000}})]:
            instance.routes.path.write_text(value)
            assert client.get('/api/health').status_code == 206
            assert calls[-1].url.port == 18766
