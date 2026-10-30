"""Private host IPC for API update controls; no capability reaches a browser."""
from __future__ import annotations

import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from .runtime_bundle import discover_layout


class HostControlError(RuntimeError):
    pass


def control_request(action, payload=None, *, layout=None, timeout=3):
    if action not in {'status', 'update', 'preferences'}:
        raise HostControlError('Unsupported desktop host action.')
    layout = layout or discover_layout()
    path = layout.state_root / 'desktop-host-control.json'
    try:
        from .bundle_host import _reject_links
        _reject_links(path)
        if path.stat().st_size > 2048:
            raise ValueError('Capability file exceeds its bound.')
        value = json.loads(path.read_text(encoding='utf-8'))
        port, token = value['port'], value['token']
        if (value.get('schema') != 'toolkit-host-control-v1'
                or type(port) is not int or not 1024 < port < 65536
                or not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token)):
            raise ValueError('Invalid host capability.')
        data = None if action == 'status' else json.dumps(payload or {}).encode('utf-8')
        if data is not None and len(data) > 4096:
            raise ValueError('Control request exceeds its bound.')
        request = Request(f'http://127.0.0.1:{port}/update-{action}', data=data,
            headers={'X-Toolkit-Control': token, 'Content-Type': 'application/json'})
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(32769)
        if len(raw) > 32768:
            raise ValueError('Control response exceeds its bound.')
        result = json.loads(raw)
        if not isinstance(result, dict):
            raise ValueError('Invalid control response.')
        return result
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise HostControlError('Desktop launcher is unavailable. Keep the launcher open to manage toolkit updates.') from error


def host_status(*, layout=None):
    return control_request('status', layout=layout)


def request_update(*, layout=None):
    return control_request('update', {}, layout=layout)


def configure_updates(enabled, *, layout=None):
    if type(enabled) is not bool:
        raise HostControlError('Automatic updates must be enabled or disabled.')
    return control_request('preferences', {'enabled': enabled}, layout=layout)
