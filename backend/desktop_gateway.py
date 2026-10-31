"""One stable desktop/LAN origin in front of owned, loopback-only services.

The source and frozen hosts use this same gateway. Runtime activation changes
only the private upstream ports: in-flight HTTP responses finish, WebSockets
reconnect, and the browser origin and pairing session remain unchanged.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import deque
from contextlib import asynccontextmanager
from http.cookies import SimpleCookie, CookieError
import ipaddress
import json
import logging
import os
from pathlib import Path
import re
import secrets
import socket
import sys
import threading
import time

import httpx
import psutil
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from starlette.routing import Route, WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect
from websockets.exceptions import WebSocketException
from starlette.middleware.cors import CORSMiddleware

from .local_access import COMPANION_ORIGINS

LOG = logging.getLogger(__name__)
COOKIE = 'toolkit_device'
HOP_HEADERS = {'connection', 'keep-alive', 'proxy-authenticate', 'proxy-authorization',
               'te', 'trailer', 'transfer-encoding', 'upgrade'}
PRIVATE_ROUTES = ('/api/runtime', '/api/lexirise/key')
ASSET_TYPES = {'.js': 'text/javascript', '.css': 'text/css', '.woff2': 'font/woff2',
               '.woff': 'font/woff', '.ttf': 'font/ttf', '.png': 'image/png',
               '.webp': 'image/webp', '.svg': 'image/svg+xml', '.ico': 'image/x-icon'}


def network_addresses():
    """Numeric interface addresses only; never trust DNS or forwarded headers."""
    return {address.address for addresses in psutil.net_if_addrs().values()
            for address in addresses if address.family == socket.AF_INET
            and ipaddress.ip_address(address.address).is_private
            and not ipaddress.ip_address(address.address).is_loopback
            and not ipaddress.ip_address(address.address).is_link_local}


def is_local(scope):
    try:
        return ipaddress.ip_address(scope.get('client', ('', 0))[0]).is_loopback
    except ValueError:
        return False


def allowed_request(scope, addresses):
    headers = scope.get('headers', [])
    hosts = [value.decode('latin1') for key, value in headers if key.lower() == b'host']
    origins = [value.decode('latin1') for key, value in headers if key.lower() == b'origin']
    if len(hosts) != 1 or len(origins) > 1:
        return False
    match = re.fullmatch(r'(localhost|[0-9.]+)(?::([0-9]{1,5}))?', hosts[0], re.I)
    if not match or (match[2] and not 1 <= int(match[2]) <= 65535):
        return False
    host = match[1].lower()
    local = is_local(scope)
    if host not in addresses and not (local and host in {'localhost', '127.0.0.1'}):
        return False
    expected = 'http://' + hosts[0]
    if origins and origins[0] != expected and not (local and origins[0] in COMPANION_ORIGINS):
        return False
    # Remote browser writes and WebSockets must demonstrate the same origin.
    return bool(origins or local or (scope['type'] == 'http' and scope['method'] in {'GET', 'HEAD'}))


class Pairing:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.code = ''
        self.expires = 0
        self.sessions = {}
        self.attempts = deque()

    def invitation(self):
        if self.clock() >= self.expires:
            self.code = f'{secrets.randbelow(1_000_000):06d}'
            self.expires = self.clock() + 600
        return self.code

    def pair(self, code, peer):
        now = self.clock()
        while self.attempts and self.attempts[0][0] <= now - 300:
            self.attempts.popleft()
        if len(self.attempts) >= 30 or sum(address == peer for _, address in self.attempts) >= 6:
            return None, 429
        self.attempts.append((now, peer))
        if not self.code or now >= self.expires or not secrets.compare_digest(str(code), self.code):
            return None, 403
        self.sessions = {token: expiry for token, expiry in self.sessions.items() if expiry > now}
        if len(self.sessions) >= 32:
            self.sessions.pop(next(iter(self.sessions)))
        token = secrets.token_urlsafe(32)
        self.sessions[token] = now + 86400
        return token, 200

    def authenticated(self, headers):
        cookies = [value.decode('latin1') for key, value in headers if key.lower() == b'cookie']
        if len(cookies) != 1:
            return False
        try:
            cookie = SimpleCookie(cookies[0]).get(COOKIE)
            return bool(cookie and self.sessions.get(cookie.value, 0) > self.clock())
        except CookieError:
            return False


class RuntimeRoutes:
    def __init__(self, state_path, *, api_port=8766, frontend_port=3000):
        self.path = Path(state_path)
        self.public_ports = {api_port, frontend_port} - {0}
        self.active = None
        self.websockets = set()

    def refresh(self):
        try:
            if self.path.stat().st_size > 1024 * 1024:
                raise ValueError('Runtime state too large')
            value = json.loads(self.path.read_text(encoding='utf-8-sig'))['active']
            ports = tuple(value[key] for key in ('apiPort', 'frontendPort'))
            if any(type(port) is not int or not 1024 < port < 65536 or port in self.public_ports for port in ports):
                raise ValueError('Invalid runtime route')
        except (OSError, ValueError, KeyError, TypeError):
            if self.active is None:
                raise ValueError('No valid owned runtime route is available.') from None
            return False
        changed = self.active is not None and self.active[0] != ports[0]
        self.active = ports
        return changed

    async def watch(self):
        while True:
            if self.refresh():
                LOG.info('Runtime activated; reconnecting transcript readers.')
                await asyncio.gather(*(ws.close(code=1012) for ws in tuple(self.websockets)), return_exceptions=True)
            await asyncio.sleep(.2)


PAIR_PAGE = '''<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<title>Connect to desktop · Game immersion toolkit</title>
<style>html{color-scheme:dark;font:18px system-ui;background:#0d1117;color:#eef2f6}
body{margin:0;min-height:100dvh;display:grid;place-items:center}main{padding:24px;max-width:26rem}
h1{font-size:1.5rem}input,button{font:inherit;box-sizing:border-box;width:100%;padding:12px;margin:8px 0;border-radius:8px}
input{border:1px solid #637084;background:#151d27;color:inherit;letter-spacing:.3em}button{border:0;background:#ccff36;color:#152000}
p{line-height:1.5;color:#bbc7d5}#message{min-height:1.5em}</style>
<main><h1>Connect to desktop</h1><p>Enter the code from <strong>Share</strong> in the desktop transcript.</p>
<form><label for="code">Connection code</label><input id="code" name="code" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required autofocus>
<button>Connect</button></form><p id="message" role="status"></p></main>
<script src="/connect.js"></script></html>'''
PAIR_SCRIPT = '''document.querySelector('form').onsubmit=async e=>{e.preventDefault();const button=document.querySelector('button'),message=document.querySelector('#message');button.disabled=true;try{const response=await fetch('/api/connection/pair',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({code:document.querySelector('#code').value})});if(response.ok){location.replace('/');return;}message.textContent=response.status===429?'Too many attempts. Try again in five minutes.':'Check the code on the desktop and try again.';}catch{message.textContent='Desktop unavailable. Check your Wi-Fi connection.';}finally{button.disabled=false;}};'''
PAGE_HEADERS = {'Content-Security-Policy': "default-src 'none'; script-src 'self'; style-src 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'",
                'Cache-Control': 'no-store', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff'}


class DesktopGateway:
    def __init__(self, routes, *, assets=None, frontend_port=3000, api_port=8766, addresses=network_addresses,
                 transport=None, browser_probe_token=None, browser_probe_result=None):
        self.routes, self.assets = routes, Path(assets).resolve() if assets else None
        self.frontend_port, self.api_port = frontend_port, api_port
        self.addresses, self.pairing = addresses, Pairing()
        self.transport = transport
        self.client = None
        self.browser_probe_token = browser_probe_token
        self.browser_probe_result = browser_probe_result
        self.browser_probe_stages = set()
        application = Starlette(routes=[Route('/{path:path}', self.http, methods=['GET', 'HEAD', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS']),
                                        WebSocketRoute('/{path:path}', self.websocket)], lifespan=self.lifespan)
        # Installed readers retain their original localhost origins. LAN readers
        # use one origin and never receive a wildcard/remote CORS grant.
        self.app = CORSMiddleware(application, allow_origins=list(COMPANION_ORIGINS),
                                  allow_methods=['GET', 'HEAD', 'POST', 'PATCH', 'PUT', 'DELETE', 'OPTIONS'],
                                  allow_headers=['Content-Type', 'Range', 'X-Proxy-Transcript',
                                                 'X-Proxy-Transcript-Account', 'X-Proxy-Transcript-Export-Scope'],
                                  expose_headers=['Content-Range'])

    @asynccontextmanager
    async def lifespan(self, _app):
        self.routes.refresh()
        async with httpx.AsyncClient(trust_env=False, timeout=httpx.Timeout(120, connect=5),
                                     transport=self.transport, limits=httpx.Limits(max_connections=64)) as self.client:
            watcher = asyncio.create_task(self.routes.watch())
            try:
                yield
            finally:
                watcher.cancel()
                await asyncio.gather(watcher, return_exceptions=True)

    def trusted(self, scope):
        return is_local(scope) or self.pairing.authenticated(scope.get('headers', []))

    def upstream_port(self, scope):
        api = scope['path'].startswith('/api/') or scope.get('server', ('', 0))[1] == self.api_port
        return self.routes.active[0 if api else 1]

    @staticmethod
    def upstream_headers(headers):
        # All validation occurs at this boundary. Backends remain inaccessible
        # from the LAN and see only the gateway's own trusted loopback identity.
        excluded = HOP_HEADERS | {'host', 'origin', 'cookie', 'forwarded', 'x-forwarded-for',
                                 'x-forwarded-host', 'x-forwarded-proto', 'authorization'}
        nominated = {part.strip().lower() for part in headers.get('connection', '').split(',')}
        return [(name, value) for name, value in headers.items() if name.lower() not in excluded | nominated]

    async def http(self, request):
        if not allowed_request(request.scope, self.addresses()):
            return JSONResponse({'detail': 'Open the desktop address directly.'}, status_code=403)
        local, path = is_local(request.scope), request.url.path
        if path == '/api/native-browser-probe':
            # This endpoint exists only in an explicitly requested native probe.
            # A normal/LAN reader cannot create acceptance evidence.
            if not local or not self.browser_probe_token or not self.browser_probe_result:
                return Response(status_code=404)
            if request.method != 'POST' or request.headers.get('origin') != str(request.base_url).rstrip('/'):
                return Response(status_code=403)
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 256:
                    return Response(status_code=413)
            try:
                value = json.loads(body)
                valid = (isinstance(value, dict) and isinstance(value.get('token'), str)
                    and secrets.compare_digest(value['token'], self.browser_probe_token)
                    and type(value.get('stage')) is int and value['stage'] in {1, 2}
                    and value.get('reader_ready') is True)
            except ValueError:
                valid = False
            if not valid:
                return Response(status_code=403)
            from .bundle_host import _atomic_json
            self.browser_probe_stages.add(value['stage'])
            _atomic_json(Path(self.browser_probe_result), {'stages': sorted(self.browser_probe_stages)})
            return Response(status_code=204, headers={'Cache-Control': 'no-store'})
        if path == '/api/connection':
            if request.method != 'GET':
                return Response(status_code=405)
            return JSONResponse({'paired': self.trusted(request.scope), 'local': local,
                **({'urls': [f'http://{address}:{self.frontend_port}' for address in sorted(self.addresses())],
                    'code': self.pairing.invitation(), 'expires_in': max(0, int(self.pairing.expires - self.pairing.clock()))} if local else {})},
                headers={'Cache-Control': 'no-store'})
        if path == '/api/connection/pair' and request.method == 'POST':
            body = bytearray()
            async for chunk in request.stream():
                body.extend(chunk)
                if len(body) > 128:
                    return Response(status_code=413)
            try:
                value = json.loads(body)
                code = value.get('code', '') if isinstance(value, dict) else ''
            except ValueError:
                code = ''
            token, status = self.pairing.pair(code, request.client.host)
            response = JSONResponse({'paired': bool(token)}, status_code=status, headers={'Cache-Control': 'no-store'})
            if token:
                response.set_cookie(COOKIE, token, max_age=86400, httponly=True, samesite='strict', path='/')
            return response
        if not self.trusted(request.scope):
            if path == '/connect.js' and request.method == 'GET':
                return Response(PAIR_SCRIPT, media_type='text/javascript', headers=PAGE_HEADERS)
            if path in {'/', '/connect'} and request.method in {'GET', 'HEAD'}:
                return HTMLResponse(PAIR_PAGE, headers=PAGE_HEADERS)
            return JSONResponse({'detail': 'Connect this device using the code on the desktop.'}, status_code=401)
        if not local and (path.startswith(PRIVATE_ROUTES) or
                          (path.startswith('/api/lexirise/accounts') and request.method not in {'GET', 'HEAD'})):
            return JSONResponse({'detail': 'Manage accounts and runtime ownership on the desktop.'}, status_code=403)
        asset = self.cached_asset(path) if request.method in {'GET', 'HEAD'} else None
        if asset:
            return FileResponse(asset, media_type=ASSET_TYPES[asset.suffix], headers={'Cache-Control': 'public, max-age=31536000, immutable'})
        upstream_port = self.upstream_port(request.scope)
        target = httpx.URL(f'http://127.0.0.1:{upstream_port}').copy_with(
            raw_path=request.scope['raw_path'] + (b'?' + request.scope['query_string'] if request.scope['query_string'] else b''))
        try:
            # An empty async stream makes httpx send a chunked body even for a
            # bodyless GET. HTTP/1.0 services may close with those unread chunk
            # bytes still queued, resetting an otherwise successful response.
            has_body = bool(request.headers.get('transfer-encoding') or
                            request.headers.get('content-length', '0') != '0')
            upstream = await self.client.send(self.client.build_request(request.method, target,
                headers=self.upstream_headers(request.headers),
                content=request.stream() if has_body else None), stream=True)
        except httpx.HTTPError:
            return JSONResponse({'detail': 'Desktop is starting or reconnecting.'}, status_code=503, headers={'Retry-After': '1'})
        headers = {key: value for key, value in upstream.headers.items()
                   if key.lower() not in HOP_HEADERS | {'set-cookie', 'access-control-allow-origin', 'access-control-allow-credentials'}}
        headers['X-Proxy-Transcript-Router'] = '1'
        headers['X-Proxy-Transcript-Upstream-Port'] = str(upstream_port)
        return StreamingResponse(upstream.aiter_raw(), status_code=upstream.status_code, headers=headers,
                                 background=BackgroundTask(upstream.aclose))

    def cached_asset(self, path):
        if not self.assets or not path.startswith('/_next/static/'):
            return None
        relative = path[len('/_next/static/'):]
        if not relative or '\\' in relative or ':' in relative or any(part in {'', '.', '..'} for part in relative.split('/')):
            return None
        candidate = self.assets / relative
        if candidate.suffix not in ASSET_TYPES or not candidate.resolve().is_relative_to(self.assets):
            return None
        if any(item.is_symlink() or item.is_junction() for item in (candidate, *candidate.parents)):
            return None
        return candidate if candidate.is_file() else None

    async def websocket(self, socket):
        if (not allowed_request(socket.scope, self.addresses()) or not self.trusted(socket.scope)
                or socket.url.path != '/api/ws'):
            await socket.close(code=1008)
            return
        port = self.upstream_port(socket.scope)
        try:
            async with connect(f'ws://127.0.0.1:{port}/api/ws', proxy=None, max_size=8 * 1024 * 1024,
                               open_timeout=5, close_timeout=2) as upstream:
                await socket.accept()
                self.routes.websockets.add(socket)

                async def outgoing():
                    while True:
                        message = await socket.receive()
                        if message['type'] == 'websocket.disconnect':
                            return
                        await upstream.send(message.get('text') if message.get('text') is not None else message['bytes'])

                async def incoming():
                    async for message in upstream:
                        await (socket.send_text(message) if isinstance(message, str) else socket.send_bytes(message))

                tasks = {asyncio.create_task(outgoing()), asyncio.create_task(incoming())}
                try:
                    await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
                finally:
                    for task in tasks:
                        task.cancel()
                    await asyncio.gather(*tasks, return_exceptions=True)
        except (OSError, WebSocketException, TimeoutError, WebSocketDisconnect):
            pass
        finally:
            self.routes.websockets.discard(socket)
            try:
                await socket.close(code=1012)
            except (RuntimeError, OSError):
                pass


def main():
    import uvicorn
    parser = argparse.ArgumentParser(description='Share the desktop transcript on the local network.')
    parser.add_argument('--state', type=Path, required=True)
    parser.add_argument('--assets', type=Path)
    parser.add_argument('--api-port', type=int, default=8766)
    parser.add_argument('--frontend-port', type=int, default=3000)
    parser.add_argument('--shutdown-stdin', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--browser-probe-result', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    routes = RuntimeRoutes(args.state, api_port=args.api_port, frontend_port=args.frontend_port)
    routes.refresh()
    probe_token = os.environ.pop('TOOLKIT_NATIVE_BROWSER_PROBE', '')
    if args.browser_probe_result and not re.fullmatch(r'[a-f0-9]{64}', probe_token):
        parser.error('Native browser probe requires an ephemeral challenge.')
    gateway = DesktopGateway(routes, assets=args.assets, api_port=args.api_port, frontend_port=args.frontend_port,
        browser_probe_token=probe_token, browser_probe_result=args.browser_probe_result)
    sockets = []
    try:
        for host, port in [('127.0.0.1', args.api_port), ('0.0.0.0', args.frontend_port)]:
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sockets.append(listener)
            if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
                listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            listener.bind((host, port))
            listener.listen(128)
        gateway.api_port, gateway.frontend_port = [listener.getsockname()[1] for listener in sockets]
        routes.public_ports = {gateway.api_port, gateway.frontend_port}
        server = uvicorn.Server(uvicorn.Config(gateway.app, proxy_headers=False, access_log=False,
                                              timeout_graceful_shutdown=5, log_level='info'))
        async def run():
            if args.shutdown_stdin:
                loop = asyncio.get_running_loop()
                def stop_on_input():
                    sys.stdin.readline()
                    loop.call_soon_threadsafe(setattr, server, 'should_exit', True)
                threading.Thread(target=stop_on_input, daemon=True).start()
            serving = asyncio.create_task(server.serve(sockets=sockets))
            while not server.started and not serving.done():
                await asyncio.sleep(.02)
            if server.started:
                print(json.dumps({'ready': True, 'apiPort': gateway.api_port, 'frontendPort': gateway.frontend_port}), flush=True)
                LOG.info('Transcript ready at http://127.0.0.1:%s; open Share to connect another device.', gateway.frontend_port)
            await serving
        asyncio.run(run())
    finally:
        for listener in sockets:
            listener.close()


if __name__ == '__main__':
    main()
