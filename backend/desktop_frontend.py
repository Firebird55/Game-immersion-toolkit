"""Manifest-bound local desktop frontend; the user's PC needs no Node server.

This host serves immutable public application bytes only. The API/WebSocket
stay at their existing address and retain their existing middleware. It neither
owns capture nor activates an update/data migration. Source Vinext remains an
independent adapter while candidate/browser/native gates are evaluated.
"""
from __future__ import annotations

import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import stat
import sys
from urllib.parse import unquote, urlsplit

from .local_access import local_access_allowed
from .runtime_bundle import RuntimeBundleError, discover_layout, relative_resource

SCHEMA = 'proxy-desktop-frontend-v1'
MANIFEST = 'desktop-manifest.json'
FRONTEND_ORIGIN = 'http://127.0.0.1:3000'
API_BASE = 'http://127.0.0.1:8766'
WEBSOCKET_URL = 'ws://127.0.0.1:8766/api/ws'
SHA = re.compile(r'[0-9a-f]{64}')
IMMUTABLE = re.compile(r'(?:assets/.*[.-][A-Za-z0-9_-]{8,}\.(?:m?js|css|woff2?|ttf|png|svg)|_next/static/(?:(?:chunks|css|media)/(?:[^/]+/)*[A-Za-z0-9_-]{8,}\.(?:m?js|css|woff2?|ttf)|[A-Za-z0-9_-]{8,}/_(?:build|ssg)Manifest\.js))')
MIME_TYPES = {'.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8',
    '.mjs': 'text/javascript; charset=utf-8', '.css': 'text/css; charset=utf-8',
    '.json': 'application/json; charset=utf-8', '.webmanifest': 'application/manifest+json',
    '.wasm': 'application/wasm', '.gz': 'application/gzip', '.txt': 'text/plain; charset=utf-8',
    '.md': 'text/plain; charset=utf-8', '.ttf': 'font/ttf', '.woff': 'font/woff', '.woff2': 'font/woff2',
    '.png': 'image/png', '.svg': 'image/svg+xml', '.ico': 'image/x-icon'}
CSP = (
    "default-src 'self'; script-src 'self' 'wasm-unsafe-eval'; worker-src 'self' blob:; "
    "style-src 'self' 'unsafe-inline'; font-src 'self'; img-src 'self' https: data: blob:; "
    "media-src 'self' https: blob: http://127.0.0.1:8766; frame-src https://vdo.ninja; "
    "connect-src 'self' http://127.0.0.1:8766 ws://127.0.0.1:8766 https://api.lexirise.app "
    "https://cdn.jsdelivr.net https://game-immersion-pairing.boazbrak.workers.dev "
    "wss://game-immersion-pairing.boazbrak.workers.dev https://game-immersion-lexirise.boazbrak.workers.dev; "
    "object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
)


class FrontendError(RuntimeError):
    """A public build is missing, corrupt or outside its declared file tree."""


def _no_links(path: Path) -> None:
    for item in (path, *path.parents):
        if item.is_symlink() or (item.exists() and getattr(item.lstat(), 'st_file_attributes', 0)
                                 & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 0x400)):
            raise FrontendError('Frontend resources cannot use links or reparse points.')


def _name(value: str) -> str:
    if not isinstance(value, str) or not value.isascii() or any(ord(char) < 32 for char in value):
        raise FrontendError('Invalid frontend resource name.')
    try:
        relative_resource(value)
    except RuntimeBundleError as error:
        raise FrontendError('Invalid frontend resource name.') from error
    path = Path(value)
    if (not (value in {'index.html', 'proxy-transcript.png'} or value.startswith(('assets/', 'mobile-capture/', 'notices/', '_next/static/')))
            or any(part.casefold() in {'node_modules', 'data', 'work', '.git', 'diagnostics', 'server'} for part in path.parts)
            or path.suffix.casefold() in {'.py', '.pyc', '.exe', '.dll', '.dpapi', '.db', '.sqlite', '.key', '.pem', '.onnx', '.onemodel', '.pak', '.pck', '.wem', '.bnk', '.mp3', '.wav', '.map'}):
        raise FrontendError('Frontend resources contain a nonpublic file.')
    return value


def build_identity(files: dict) -> str:
    return hashlib.sha256(json.dumps(files, sort_keys=True, ensure_ascii=False,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


class FrontendBuild:
    def __init__(self, root: Path):
        raw = Path(root).absolute()
        _no_links(raw)
        self.root = raw.resolve()
        manifest = self.root / MANIFEST
        _no_links(manifest)
        try:
            identity = manifest.stat()
            if not stat.S_ISREG(identity.st_mode) or identity.st_size > 4 * 1024 * 1024:
                raise FrontendError('Frontend manifest exceeds its limit.')
            value = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise FrontendError('Frontend manifest is missing or invalid; rebuild or re-extract the candidate.') from error
        if (not isinstance(value, dict) or value.get('schema') != SCHEMA or value.get('entry') != 'index.html'
                or value.get('routes') != ['/'] or value.get('runtime') != 'static-local-no-node'
                or value.get('frontend_origin') != FRONTEND_ORIGIN or value.get('api_base') != API_BASE
                or value.get('websocket_url') != WEBSOCKET_URL
                or not re.fullmatch(r'\d+\.\d+\.\d+', str(value.get('version', '')))
                or not SHA.fullmatch(str(value.get('source_fingerprint', '')))
                or not SHA.fullmatch(str(value.get('lock_sha256', '')))
                or not re.fullmatch(r'[0-9a-f]{40}', str(value.get('source_commit', '')))):
            raise FrontendError('Frontend manifest contract is incompatible.')
        files = value.get('files')
        if not isinstance(files, dict) or not files or len(files) > 4096 or 'index.html' not in files:
            raise FrontendError('Frontend file inventory is incomplete.')
        aliases, total = set(), 0
        for name, entry in files.items():
            _name(name)
            if name.casefold() in aliases:
                raise FrontendError('Frontend resource names have a Windows case alias.')
            aliases.add(name.casefold())
            if (not isinstance(entry, dict) or set(entry) != {'sha256', 'bytes', 'mime'}
                    or not isinstance(entry['sha256'], str) or not SHA.fullmatch(entry['sha256'])
                    or type(entry['bytes']) is not int or not 0 <= entry['bytes'] <= 128 * 1024 * 1024
                    or entry['mime'] != MIME_TYPES.get(Path(name).suffix.lower())):
                raise FrontendError('Frontend file identity, size or MIME type is invalid.')
            total += entry['bytes']
        if total > 512 * 1024 * 1024 or value.get('build_id') != build_identity(files):
            raise FrontendError('Frontend build identity or total size is invalid.')
        self.value, self.files, self.build_id = value, files, value['build_id']
        actual, actual_directories = set(), set()
        for directory, children, names in os.walk(self.root, followlinks=False):
            for child in children:
                _no_links(Path(directory) / child)
                actual_directories.add((Path(directory) / child).relative_to(self.root).as_posix())
            for name in names:
                path = Path(directory) / name
                _no_links(path)
                if not stat.S_ISREG(path.stat().st_mode):
                    raise FrontendError('Frontend resources must be regular files.')
                actual.add(path.relative_to(self.root).as_posix())
        expected_directories = {parent.as_posix() for name in files for parent in Path(name).parents if parent != Path('.')}
        if actual != {*files, MANIFEST} or actual_directories != expected_directories:
            raise FrontendError('Frontend tree differs from its closed manifest inventory.')
        for name in files:
            self.read(name)

    def read(self, name: str) -> bytes:
        entry = self.files[name]
        path = self.root / name
        _no_links(path)
        if not path.resolve().is_relative_to(self.root):
            raise FrontendError('Frontend resource escapes its root.')
        try:
            with path.open('rb') as stream:
                if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
                    raise FrontendError('Frontend resource is not a regular file.')
                data = stream.read(entry['bytes'] + 1)
        except OSError as error:
            raise FrontendError('Frontend resource is unavailable; restore the verified build.') from error
        if len(data) != entry['bytes'] or hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise FrontendError('Frontend resource checksum failed; restore the verified build.')
        return data


class DesktopFrontendServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, root: Path, port=3000, *, retained_roots=()):
        self.current = FrontendBuild(root)
        self.retained = tuple(FrontendBuild(path) for path in retained_roots)
        if len(self.retained) > 16:
            raise FrontendError('Too many retained frontend builds.')
        # Identical URLs may never resolve to different immutable bytes. Mutable
        # mobile URLs intentionally select the current build, as the source host.
        immutable = {}
        for build in (self.current, *self.retained):
            for name, entry in build.files.items():
                if IMMUTABLE.fullmatch(name):
                    if name in immutable and immutable[name] != entry['sha256']:
                        raise FrontendError('Retained immutable frontend URLs collide.')
                    immutable[name] = entry['sha256']
        super().__init__(('127.0.0.1', port), DesktopFrontendHandler)

    def handle_error(self, request, client_address):
        # No private paths, query strings or request/account headers in logs.
        print('Local frontend request failed.', file=sys.stderr)


class DesktopFrontendHandler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'LocalFrontend'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def log_message(self, *_args):
        pass

    def _respond(self, status, body=b'', *, mime='text/plain; charset=utf-8', etag=None, immutable=False):
        self.send_response(status)
        self.send_header('Content-Type', mime)
        if status != 304:
            self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', CSP)
        self.send_header('Cache-Control', 'public, max-age=31536000, immutable' if immutable and not self.headers.get('Authorization') else 'no-store')
        if etag:
            self.send_header('ETag', etag)
        if status >= 400:
            self.close_connection = True
            self.send_header('Connection', 'close')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def _serve(self):
        headers = [(key.encode('latin-1'), value.encode('latin-1')) for key, value in self.headers.raw_items()]
        if not local_access_allowed(headers):
            return self._respond(403, b'Use the local companion on this PC.')
        if self.command not in {'GET', 'HEAD'}:
            return self._respond(405, b'Only static GET and HEAD requests are supported.')
        try:
            if not self.path.startswith('/') or self.path.startswith('//'):
                raise FrontendError('Invalid target.')
            path = urlsplit(self.path).path
            if re.search(r'%(?![0-9a-fA-F]{2})', path):
                raise FrontendError('Invalid escape.')
            name = unquote(path, errors='strict').lstrip('/')
            name = {'': 'index.html', 'mobile-capture/': 'mobile-capture/index.html'}.get(name, name)
            name = _name(name)
        except (FrontendError, UnicodeError, ValueError):
            return self._respond(404, b'Frontend resource not found.')
        build = self.server.current
        if name not in build.files and IMMUTABLE.fullmatch(name):
            build = next((item for item in self.server.retained if name in item.files), build)
        if name not in build.files:
            return self._respond(404, b'Frontend resource not found.')
        entry = build.files[name]
        try:
            payload = build.read(name)
        except FrontendError:
            return self._respond(503, b'Frontend resource failed verification; restore the verified candidate.')
        etag = '"' + entry['sha256'] + '"'
        if self.headers.get('If-None-Match') == etag:
            return self._respond(304, mime=entry['mime'], etag=etag, immutable=bool(IMMUTABLE.fullmatch(name)))
        return self._respond(200, payload, mime=entry['mime'], etag=etag, immutable=bool(IMMUTABLE.fullmatch(name)))

    do_GET = do_HEAD = do_POST = do_PUT = do_PATCH = do_DELETE = do_OPTIONS = _serve


def frontend_root(args, layout):
    if layout.mode == 'bundle':
        manifest = layout.resource('desktop/' + MANIFEST)
        root = manifest.parent
        if args.root is not None and args.root.resolve() != root.resolve():
            raise FrontendError('Frozen frontend must use its verified application resource tree.')
        if args.retained_root and os.environ.get('PROXY_TRANSCRIPT_HOST_MANAGED') != '1':
            raise FrontendError('Frozen retained builds require the desktop update supervisor.')
        # The host selects these only from verified installed slots. Every old
        # build still has its own closed public-only inventory and byte hashes;
        # the server exposes only immutable chunk URLs, never an old index.html.
        for retained in args.retained_root:
            FrontendBuild(retained)
        current = FrontendBuild(root)
        if {name for name in layout.resources if name.startswith('desktop/')} != {
                'desktop/' + name for name in (*current.files, MANIFEST)}:
            raise FrontendError('Frozen frontend resource inventory is incomplete.')
        for name in current.files:
            layout.resource('desktop/' + name)
    elif args.root is not None:
        root = args.root
    else:
        raise FrontendError('Source frontend host needs an explicitly built --root.')
    return root


def main():
    parser = argparse.ArgumentParser(description='Serve a verified local desktop frontend without Node/npm/Wrangler.')
    parser.add_argument('--root', type=Path)
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--retained-root', type=Path, action='append', default=[])
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('Invalid loopback frontend port.')
    try:
        root = frontend_root(args, discover_layout())
        server = DesktopFrontendServer(root, args.port, retained_roots=args.retained_root)
    except (FrontendError, RuntimeBundleError, OSError):
        raise SystemExit('Local frontend could not start; verify its built resource tree, root selection and available loopback port.') from None
    print(json.dumps({'ready': True, 'port': server.server_port, 'build_id': server.current.build_id}), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    main()
