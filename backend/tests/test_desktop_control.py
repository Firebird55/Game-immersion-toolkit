"""Host-only update capabilities never travel through the browser interface."""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import threading
from types import SimpleNamespace

import pytest

from backend.desktop_control import HostControlError, configure_updates, host_status, request_update


def test_authenticated_control_uses_bounded_private_host_address(tmp_path):
    token = secrets.token_urlsafe(32)
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass
        def handle_request(self):
            assert self.headers['X-Toolkit-Control'] == token
            assert token not in self.path
            raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            calls.append((self.command, self.path, json.loads(raw) if raw else None))
            body = json.dumps({'state': 'checking', 'started': True, 'enabled': False}).encode()
            self.send_response(200)
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        do_GET = do_POST = handle_request
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    thread = threading.Thread(target=server.serve_forever)
    thread.start()
    (tmp_path / 'desktop-host-control.json').write_text(json.dumps({
        'schema': 'toolkit-host-control-v1', 'port': server.server_port, 'token': token}))
    layout = SimpleNamespace(state_root=tmp_path)
    try:
        assert host_status(layout=layout)['state'] == 'checking'
        assert request_update(layout=layout)['started']
        assert configure_updates(False, layout=layout)['enabled'] is False
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
    assert calls == [('GET', '/update-status', None), ('POST', '/update-update', {}),
                     ('POST', '/update-preferences', {'enabled': False})]


@pytest.mark.parametrize('record', [None, {}, {'schema': 'toolkit-host-control-v1',
    'port': 'https://untrusted.invalid', 'token': 'private-value'}, {'schema': 'unknown', 'port': 9001, 'token': 'x' * 43}])
def test_control_rejects_unavailable_or_untrusted_routing_without_leaking_tokens(tmp_path, record):
    if record is not None:
        (tmp_path / 'desktop-host-control.json').write_text(json.dumps(record))
    with pytest.raises(HostControlError) as error:
        host_status(layout=SimpleNamespace(state_root=tmp_path))
    assert 'private-value' not in str(error.value) and 'untrusted.invalid' not in str(error.value)


def test_update_preferences_reject_nonboolean_before_network():
    with pytest.raises(HostControlError):
        configure_updates('false')
