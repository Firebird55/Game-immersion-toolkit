"""App-private localhost transport for the shared Python core and desktop reader.

The Android host supplies storage, frame/OCR and WebView lifecycle. No desktop
window/audio/credential adapters, development server or remote PC are imported.
"""
from __future__ import annotations

from contextlib import contextmanager
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
from urllib.parse import unquote, urlsplit

from .prepared_library import MAX_LIBRARY
from .prepared_session import PreparedCaptureSession

MAX_FRAME = 10 * 1024**2
_host = None
_host_lock = threading.RLock()


class AndroidHost:
    def __init__(self, root, frontend, native=None, *, port=0):
        self.session = PreparedCaptureSession(root)
        self.frontend = Path(frontend).absolute()
        self.native = native
        self.cookie = secrets.token_hex(32)
        self.pending_lock = threading.Lock()
        self.import_lock = threading.RLock()
        self.import_jobs = {}
        self.server = ThreadingHTTPServer(('127.0.0.1', port), self._handler())
        self.server.daemon_threads = True
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, name='toolkit-android-http', daemon=True)
        self.thread.start()

    def _import_job(self, identity, *, register=False):
        if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', identity):
            raise ValueError('A valid private import ID is required')
        with self.import_lock:
            if identity not in self.import_jobs:
                if len(self.import_jobs) >= 128:
                    raise ValueError('Reopen the app before starting another library operation')
                self.import_jobs[identity] = {'state': 'pending', 'cancel': threading.Event(), 'working': False,
                    'generation': self.session.generation}
            job = self.import_jobs[identity]
            if register:
                if job['state'] != 'pending' or job['working']:
                    raise ValueError('The import ID was already used or cancelled')
                if sum(item['working'] for item in self.import_jobs.values()) >= 2:
                    raise ValueError('A previous library upload is still settling')
                if any(item['working'] and item['state'] not in {'cancelled', 'failed'} for item in self.import_jobs.values()):
                    raise ValueError('Another library import is in progress')
                job.update(state='reading', working=True)
            return job

    def cancel_import(self, identity):
        with self.import_lock:
            job = self._import_job(identity)
            if job['state'] == 'committed':
                return {'state': 'already_committed', 'cancelled': False, 'already_committed': True, 'import_id': identity,
                    'source_generation': self.session.generation}, 409
            job['cancel'].set();job['state'] = 'cancelled'
            return {'state': 'cancelled', 'cancelled': True, 'already_committed': False, 'import_id': identity,
                'source_generation': job['generation']}, 200

    @contextmanager
    def publish_import(self, job):
        # The same lock decides cancellation and pointer publication. Once this
        # block commits, a late cancel must report committed, never rollback.
        with self.import_lock:
            if job['cancel'].is_set():
                raise InterruptedError('Library import cancelled')
            yield lambda: job.update(state='committed')

    def close(self):
        self.session.stop('Android host closed')
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)

    def platform(self):
        return {'platform': 'android', 'library_import': True,
            'capture_source': 'remote-stream' if self.native else 'authored-observations',
            'message': 'Private prepared libraries and original audio are processed on this Android device.',
            'protected_accounts': False, 'ocr': 'bundled-mlkit' if self.native else 'not-attached',
            'local_game_capture': False, 'max_frame_bytes': MAX_FRAME, 'max_frame_dimension': 4096}

    def accept_ocr(self, generation, sequence, raw):
        value = json.loads(raw)
        width, height, blocks = value['width'], value['height'], value['blocks']
        if (type(width) is not int or type(height) is not int or not 0 < width <= 4096
                or not 0 < height <= 4096 or not isinstance(blocks, list) or len(blocks) > 128):
            raise ValueError('Invalid native OCR frame')
        settings = self.session.settings.get()
        game = self.session.index.game if self.session.index else 'zzz'
        channels = {'dialogue': getattr(settings, game + '_region', settings.region),
                    'cinematic': getattr(settings, game + '_cinematic_region', settings.cinematic_region)}
        result = []
        texts = []
        for block in blocks:
            if (not isinstance(block, dict) or not isinstance(block.get('text'), str)
                    or len(block['text']) > 8192 or not isinstance(block.get('rect'), list)
                    or len(block['rect']) != 4 or any(type(n) is not int for n in block['rect'])):
                raise ValueError('Invalid native OCR block')
            texts.append(block['text'])
        for channel, region in channels.items():
            groups = []
            for block in blocks:
                left, top, right, bottom = block['rect']
                # Only whole recognized blocks inside the calibrated region.
                if (region.left * width <= left < right <= (region.left + region.width) * width
                        and region.top * height <= top < bottom <= (region.top + region.height) * height):
                    groups.append(block['text'])
            result.extend(self.session.observe(generation, sequence, groups, channel=channel))
        result.extend(self.session.observe(generation, sequence, texts, channel='fullframe'))
        return result

    def _handler(self):
        host = self
        class Handler(BaseHTTPRequestHandler):
            server_version = 'ToolkitAndroid/1'
            protocol_version = 'HTTP/1.1'
            def setup(self):
                super().setup()
                self.connection.settimeout(15)
            def log_message(self, *args):
                pass  # Frames, URLs, catalogs and account data never become logs.
            def _headers(self, status, size, content_type, *, cookie=False):
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(size))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-src https://vdo.ninja; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                if cookie:
                    self.send_header('Set-Cookie', f'toolkit_session={host.cookie}; HttpOnly; SameSite=Strict; Path=/')
                self.end_headers()
            def _json(self, value, status=200):
                raw = json.dumps(value, ensure_ascii=False).encode()
                self._headers(status, len(raw), 'application/json; charset=utf-8');self.wfile.write(raw)
            def _authorize(self, path):
                if self.headers.get('Host') != urlsplit(host.origin).netloc:
                    return False
                origin = self.headers.get('Origin')
                if origin and origin != host.origin:
                    return False
                if not path.startswith('/api/'):
                    return True
                try:
                    cookie = SimpleCookie(self.headers.get('Cookie', ''))
                    return secrets.compare_digest(cookie['toolkit_session'].value, host.cookie)
                except (KeyError, ValueError):
                    return False
            def _body(self, limit):
                if self.headers.get('Transfer-Encoding') or not self.headers.get('Content-Length', '0').isdigit():
                    raise ValueError('A bounded request length is required')
                size = int(self.headers.get('Content-Length', '0'))
                if size > limit:
                    raise ValueError('Request is too large')
                raw = self.rfile.read(size)
                if len(raw) != size:
                    raise InterruptedError('Request was interrupted')
                return raw
            def _handle(self):
                path = urlsplit(self.path).path
                if not self._authorize(path):
                    self._json({'detail': 'App-local request required'}, 403);return
                if path == '/api/platform' and self.command == 'GET':
                    self._json(host.platform());return
                if path in {'/api/snapshot', '/api/status'} and self.command == 'GET':
                    self._json(host.session.snapshot());return
                if path == '/api/settings':
                    if self.command == 'GET':
                        self._json(host.session.settings.get().model_dump(mode='json'));return
                    if self.command == 'PATCH':
                        self._json(host.session.update_settings(json.loads(self._body(1024**2))));return
                if path == '/api/capture/start' and self.command == 'POST':
                    generation = host.session.start()
                    self._json({**host.session.snapshot(), 'generation': generation});return
                if path in {'/api/capture/stop', '/api/capture/source'} and self.command == 'POST':
                    self._body(4096)
                    host.session.stop('Screen source changed' if path.endswith('source') else 'Capture paused')
                    self._json({**host.session.snapshot(), 'generation': host.session.generation});return
                if path == '/api/library/import' and self.command == 'POST':
                    if self.headers.get('Transfer-Encoding') or not self.headers.get('Content-Length', '').isdigit():
                        raise ValueError('A bounded library length is required')
                    size = int(self.headers['Content-Length'])
                    if not 0 < size <= MAX_LIBRARY:
                        raise ValueError('Library is too large or empty')
                    identity = self.headers.get('X-Toolkit-Import-Id')
                    job = host._import_job(identity, register=True)
                    try:
                        with tempfile.TemporaryDirectory(prefix='upload-', dir=host.session.root) as folder:
                            upload = Path(folder) / 'library.zip'
                            with upload.open('xb') as destination:
                                remaining = size
                                while remaining:
                                    if job['cancel'].is_set():
                                        raise InterruptedError('Library import cancelled')
                                    block = self.rfile.read(min(1024**2, remaining))
                                    if not block:
                                        raise InterruptedError('Library upload interrupted')
                                    destination.write(block);remaining -= len(block)
                            self._json(host.session.import_library(upload, cancelled=job['cancel'].is_set,
                                publish_guard=lambda: host.publish_import(job)));return
                    finally:
                        with host.import_lock:
                            job['working'] = False
                            if job['state'] not in {'committed', 'cancelled'}:
                                job['state'] = 'failed'
                if path == '/api/library/import/cancel' and self.command == 'POST':
                    result, status = host.cancel_import(json.loads(self._body(4096)).get('import_id'))
                    self._json(result, status);return
                if path == '/api/capture/frame' and self.command == 'POST':
                    generation, sequence = (int(self.headers.get(name, '-1')) for name in ('X-Toolkit-Generation', 'X-Toolkit-Frame'))
                    raw = self._body(MAX_FRAME)
                    if generation != host.session.generation or not host.session.running:
                        self._json({'detail': 'Screen source changed', 'generation': host.session.generation}, 409);return
                    if self.headers.get('Content-Type') not in {'image/jpeg', 'image/png'} or not raw or sequence < 0 or host.native is None:
                        raise ValueError('Native frame OCR is unavailable or the image is invalid')
                    locale = host.session.index.source_locale
                    host.native.submit(raw, generation, sequence, locale)
                    self._json({'accepted': True, 'generation': generation, 'frame': sequence}, 202);return
                line_match = re.fullmatch(r'/api/lines/([1-9][0-9]*)/(favorite|audio)', path)
                if line_match:
                    identity, operation = int(line_match[1]), line_match[2]
                    if operation == 'favorite' and self.command == 'PATCH':
                        value = json.loads(self._body(4096)).get('favorite')
                        if type(value) is not bool:
                            raise ValueError('Invalid favorite value')
                        line = host.session.history.set_favorite(identity, value)
                        if line is None:
                            self._json({'detail': 'Line not found'}, 404);return
                        host.session.state_version += 1
                        self._json(host.session._line(line));return
                    if operation == 'audio' and self.command == 'GET':
                        audio = host.session.audio_path(identity)
                        if audio is None:
                            self._json({'detail': 'Original recording unavailable'}, 404);return
                        self._headers(200, audio.stat().st_size, 'audio/wav' if audio.suffix == '.wav' else 'audio/mpeg')
                        with audio.open('rb') as source:
                            while block := source.read(1024**2):
                                self.wfile.write(block)
                        return
                if path.startswith('/api/'):
                    self._json({'detail': 'This host capability is not available'}, 501);return
                if self.command != 'GET':
                    self._json({'detail': 'Method unavailable'}, 405);return
                decoded = unquote(path)
                if '\\' in decoded or '\0' in decoded or '..' in decoded.split('/') or '%' in decoded:
                    raise ValueError('Invalid static path')
                file = host.frontend / decoded.lstrip('/') if decoded != '/' else host.frontend / 'index.html'
                if not file.is_file() or not file.resolve().is_relative_to(host.frontend.resolve()):
                    self._json({'detail': 'Reader resource not found'}, 404);return
                raw = file.read_bytes()
                if file.suffix == '.html':
                    raw = raw.replace(b'<head>', b'<head><meta name="toolkit-host-platform" content="android">')
                self._headers(200, len(raw), mimetypes.guess_type(file.name)[0] or 'application/octet-stream', cookie=path == '/')
                self.wfile.write(raw)
            def _dispatch(self):
                try:
                    self._handle()
                except (ValueError, KeyError, TypeError, OSError, InterruptedError):
                    self.close_connection = True
                    try:
                        self._json({'detail': 'The local request did not complete. Check the current library before retrying.'}, 400)
                    except OSError:
                        pass
            do_GET = do_POST = do_PATCH = _dispatch
        return Handler


def start(root, frontend, native=None):
    global _host
    with _host_lock:
        if _host is None:
            # A stable app-local origin preserves the shared reader's existing
            # localStorage keys through offline restarts and app upgrades.
            pointer = Path(root) / 'reader-origin.json'
            port = json.loads(pointer.read_text())['port'] if pointer.is_file() else 0
            if type(port) is not int or port != 0 and not 1024 <= port <= 65535:
                raise ValueError('Invalid app-local reader origin')
            _host = AndroidHost(root, frontend, native, port=port)
            pending = pointer.with_suffix('.pending')
            pending.write_text(json.dumps({'port': _host.server.server_port}), encoding='utf8')
            pending.replace(pointer)
        return _host.origin + '/'


def pause():
    with _host_lock:
        if _host:
            _host.session.stop('App paused; reconnect the screen source to continue')


def accept_ocr(generation, sequence, raw):
    with _host_lock:
        return json.dumps(_host.accept_ocr(generation, sequence, raw)) if _host else '[]'
