"""App-private localhost transport for the shared Python core and desktop reader.

The Android host supplies storage, frame/OCR and WebView lifecycle. No desktop
window/audio/credential adapters, development server or remote PC are imported.
"""
from __future__ import annotations

from contextlib import contextmanager
import base64
import hashlib
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import math
from pathlib import Path
import re
import secrets
import tempfile
import threading
import time
import weakref
from urllib.parse import parse_qs, unquote, urlsplit

from .capture_geometry import picture_bounds, region_bounds
from .models import CaptureRegion
from .prepared_library import MAX_LIBRARY, MAX_TEXT, MAX_ROWS
from .prepared_session import PreparedCaptureSession

MAX_FRAME = 10 * 1024**2
UUID_PATTERN = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}')
_host = None
_host_lock = threading.RLock()


def presentation_lines(value, width, height):
    """Optional native classifier evidence; unknown confidence fails closed."""
    spans = value.get('presentation_lines', [])
    if not isinstance(spans, list) or len(spans) > 512:
        return []
    keys = {axis + str(n) for axis in ('x', 'y') for n in range(1, 5)}
    for span in spans:
        if not isinstance(span, dict) or not isinstance(span.get('text'), str) or not 0 < len(span['text']) <= 2048:
            return []
        confidence, rectangle = span.get('confidence'), span.get('bounding_rect')
        if (type(confidence) not in (float, int) or not math.isfinite(confidence) or not 0 <= confidence <= 1
                or not isinstance(rectangle, dict) or set(rectangle) != keys):
            return []
        if any(type(n) not in (float, int) or not math.isfinite(n)
                or not 0 <= n <= (width if key.startswith('x') else height) for key, n in rectangle.items()):
            return []
    return spans


class AndroidHost:
    def __init__(self, root, frontend, native=None, *, port=0, enable_accounts=False, account_transport=None,
            authored_accounts=False):
        self.root = Path(root).absolute()
        self.receiver_owner = None
        self.account_sessions = None
        self.authored_accounts = bool(authored_accounts)
        protection = native
        if authored_accounts:
            if native is None or account_transport is not None:
                raise ValueError('Authored accounts require the isolated native startup mode.')
            native.assertAuthoredAccounts()
            from types import SimpleNamespace
            from .android_authored_accounts import transport
            protection = SimpleNamespace(protect=native.protectAuthored)
            account_transport = transport()
            enable_accounts = True
        if enable_accounts:
            if native is None:
                raise ValueError('Protected Android accounts require the native provider.')
            from .android_accounts import AndroidAccountSessions
            from .android_protected_storage import AndroidProtectedBlobs
            self.account_sessions = AndroidAccountSessions(root, protect=AndroidProtectedBlobs(protection).protect,
                on_invalidate=self._release_receiver, transport=account_transport)
            self._session = None
        else:
            self._session = PreparedCaptureSession(root, on_invalidate=self._release_receiver)
        self.frontend = Path(frontend).absolute()
        self.native = native
        self.cookie = secrets.token_hex(32)
        self.pending_lock = threading.Lock()
        self.import_lock = threading.RLock()
        self.import_jobs = {}
        self.frame_geometry = None
        self.preview_frame = None
        self.preview_lock = threading.Lock()
        self.receiver_revisions = {}
        self.receiver_owner = None
        self.document_epoch = secrets.token_hex(16)
        self.document_started = False
        self.server = ThreadingHTTPServer(('127.0.0.1', port), self._handler())
        self.server.daemon_threads = True
        self.origin = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, name='toolkit-android-http', daemon=True)
        self.thread.start()

    @property
    def session(self):
        return self.account_sessions.session if self.account_sessions else self._session

    @property
    def account_generation(self):
        return self.account_sessions.accounts.generation if self.account_sessions else 0

    def guard_account(self, value, *, session=None, selecting=False):
        if self.account_sessions is None:
            return 0
        from .android_accounts import AndroidAccountConflict
        if not isinstance(value, str) or not value.isascii() or not value.isdigit() or len(value) > 16:
            raise AndroidAccountConflict('account_generation_required', 'Refresh the current account before this operation.')
        generation = int(value)
        self.account_sessions._expect(generation)
        if (not selecting and self.account_sessions.transitioning) or session is not None and session is not self.session:
            raise AndroidAccountConflict('account_selection_pending', 'Wait for the current account selection to finish.')
        return generation

    def _import_job(self, identity, *, register=False, session=None, account_generation=None):
        if not isinstance(identity, str) or not re.fullmatch(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', identity):
            raise ValueError('A valid private import ID is required')
        with self.import_lock:
            if identity not in self.import_jobs:
                if len(self.import_jobs) >= 128:
                    raise ValueError('Reopen the app before starting another library operation')
                self.import_jobs[identity] = {'state': 'pending', 'cancel': threading.Event(), 'working': False,
                    'generation': self.session.generation, 'scope_session': weakref.ref(session or self.session),
                    'account_generation': self.account_generation if account_generation is None else account_generation}
            job = self.import_jobs[identity]
            if self.account_sessions and (job['scope_session']() is not (session or self.session)
                    or job['account_generation'] != (self.account_generation if account_generation is None else account_generation)):
                from .android_accounts import AndroidAccountConflict
                raise AndroidAccountConflict('account_import_scope_changed', 'The import belongs to an earlier account selection.')
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
            if self.account_sessions:
                self.account_sessions.guard_import(job['scope_session'](), job['account_generation'])
            yield lambda: job.update(state='committed')

    def close(self):
        self.session.stop('Android host closed')
        if self.account_sessions:
            self.account_sessions.close()
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=5)

    def platform(self):
        return {'platform': 'android', 'library_import': True,
            'capture_source': 'remote-stream' if self.native else 'authored-observations',
            'message': 'Private prepared libraries and original audio are processed on this Android device.',
            'protected_accounts': self.account_sessions is not None,
            'authored_account_fixture': self.authored_accounts,
            'account_protocol': 'scoped-accounts-v1' if self.account_sessions else None,
            'ocr': 'bundled-mlkit' if self.native else 'not-attached',
            'local_game_capture': False, 'max_frame_bytes': MAX_FRAME, 'max_frame_dimension': 4096,
            'max_library_bytes': MAX_LIBRARY, 'max_text_bytes': MAX_TEXT, 'max_library_records': MAX_ROWS,
            'document_epoch': self.document_epoch, 'receiver_control': True, 'receiver_protocol': 'leased-frames-v1'}

    def _release_receiver(self):
        self.receiver_owner = None
        self.preview_frame = None
        self.frame_geometry = None

    def _picture(self, width, height, area=None):
        game = self.session.index.game if self.session.index else 'zzz'
        settings = self.session.settings.get()
        selected = area if area is not None else getattr(settings, game + '_picture_area', 'window')
        return picture_bounds((0, 0, width, height), selected if game in {'nte', 'honkai3'} else 'window')

    def snapshot(self):
        with self.session.lock:
            result = self.session.snapshot()
            if self.account_sessions:
                result['context']['account_generation'] = self.account_generation
                preferences = self.account_sessions.cached_preferences()
                result['lines'] = [self.account_sessions.qualify_line(self.account_sessions.present_dto(line, preferences))
                    for line in result['lines']]
                result['lexirise'] = self.account_sessions.lexirise_status()
            frame = self.preview_frame
            if self._preview_current(frame):
                bounds = self._picture(frame['width'], frame['height'])
                game = self.session.index.game
                region = getattr(self.session.settings.get(), game + '_region', self.session.settings.get().region)
                result['status']['capture'].update(window_bounds=(0, 0, frame['width'], frame['height']),
                    crop_bounds=region_bounds(bounds, region))
            return result

    def _preview_current(self, frame):
        return bool(frame and frame is self.preview_frame and self.session.running
            and frame['generation'] == self.session.generation and frame['epoch'] == self.document_epoch
            and frame['owner'] == self.receiver_owner)

    def preview(self, query):
        values = parse_qs(query, keep_blank_values=True, max_num_fields=8)
        if set(values) - {'left', 'top', 'width', 'height', 'picture_area', 't', 'account_generation'} or any(len(v) != 1 for v in values.values()):
            raise ValueError('Invalid preview crop')
        coordinates = {'left', 'top', 'width', 'height'}
        supplied = coordinates.intersection(values)
        if supplied and supplied != coordinates:
            raise ValueError('A complete preview crop is required')
        region = CaptureRegion(**{key: values[key][0] for key in coordinates}) if supplied else None
        area = values.get('picture_area', [None])[0]
        if area is not None and area not in {'window', '16:9'}:
            raise ValueError('Invalid picture area')
        with self.session.lock:
            if self.account_sessions:
                self.guard_account(values.get('account_generation', [None])[0])
            frame = self.preview_frame
            if not self._preview_current(frame) or self.native is None:
                return None
            if region is None:
                settings = self.session.settings.get()
                region = getattr(settings, self.session.index.game + '_region', settings.region)
            crop = region_bounds(self._picture(frame['width'], frame['height'], area), region)
        # Bitmap decoding cannot hold the lifecycle/session lock. Only one
        # bounded preview operation can own native image memory at a time.
        if not self.preview_lock.acquire(blocking=False):
            return None
        try:
            try:
                encoded = str(self.native.preview(frame['bytes'], *crop))
                if len(encoded) > 2 * 1024**2:
                    return None
                image = base64.b64decode(encoded, validate=True)
                if not image.startswith(b'\xff\xd8') or not image.endswith(b'\xff\xd9'):
                    return None
                return frame, image
            except Exception:
                # Header bounds can be readable in a truncated image which the
                # bitmap decoder rejects. Keep it an unavailable image, without
                # propagating platform/provider diagnostics to HTTP logs.
                return None
        finally:
            self.preview_lock.release()

    def _active_receiver(self):
        # Caller holds the same session lock used by frame admission, pause,
        # settings, import publication and asynchronous OCR confirmation.
        if self.receiver_owner and (self.receiver_owner['generation'] != self.session.generation or not self.session.running):
            self.receiver_owner = None
        return self.receiver_owner

    def _receiver_conflict(self, state, detail):
        return {'state': state, 'detail': detail, 'generation': self.session.generation,
            'running': self.session.running}, 409

    def control_receiver(self, value, document_epoch):
        if (not isinstance(value, dict) or set(value) - {'id', 'revision', 'action', 'expected_generation'}
                or not isinstance(value.get('id'), str) or not UUID_PATTERN.fullmatch(value['id'])
                or type(value.get('revision')) is not int or not 0 < value['revision'] <= 2**53 - 1
                or value.get('action') not in {'start', 'stop'}):
            raise ValueError('Invalid screen receiver control')
        identity, revision, action = value['id'], value['revision'], value['action']
        if action == 'start' and (type(value.get('expected_generation')) is not int
                or not 0 <= value['expected_generation'] <= 2**53 - 1):
            raise ValueError('A current screen generation is required')
        with self.session.lock:
            if not isinstance(document_epoch, str) or not secrets.compare_digest(document_epoch, self.document_epoch):
                return self._receiver_conflict('receiver_document_changed', 'The reader document changed; reconnect from the current screen')
            owner = self._active_receiver()
            entry = self.receiver_revisions.get(identity)
            if entry is None:
                if len(self.receiver_revisions) >= 128:
                    return self._receiver_conflict('receiver_registry_full', 'Reopen the app before connecting another screen receiver')
                entry = self.receiver_revisions[identity] = {'revision': 0, 'retired': False}
            if entry['retired']:
                return self._receiver_conflict('receiver_document_retired', 'This screen receiver belongs to a replaced reader document')
            if revision <= entry['revision']:
                return self._receiver_conflict('receiver_revision_stale', 'A newer screen receiver action already won')
            entry['revision'] = revision
            if action == 'start':
                if owner and owner['id'] != identity:
                    return self._receiver_conflict('receiver_owned', 'Another screen receiver is active')
                if value['expected_generation'] != self.session.generation:
                    return self._receiver_conflict('receiver_generation_changed', 'The screen source changed; refresh its current generation')
                generation = self.session.start()
                self.receiver_owner = {'id': identity, 'revision': revision, 'generation': generation}
            elif owner and owner['id'] == identity:
                self.session.stop('Screen receiver stopped')
                self.receiver_owner = None
            return {'generation': self.session.generation, 'receiver_id': identity,
                'receiver_revision': revision, 'running': self.session.running}, 200

    def replace_document(self):
        with self.session.lock:
            if self.document_started or self.receiver_revisions or self.session.running:
                self.session.stop('Reader document replaced; reconnect the screen source')
                self.receiver_owner = None
                for entry in self.receiver_revisions.values():
                    entry['retired'] = True
                self.document_epoch = secrets.token_hex(16)
            self.document_started = True
            return self.document_epoch

    def pause(self):
        with self.session.lock:
            self.session.stop('App paused; reconnect the screen source to continue')
            self.receiver_owner = None

    def submit_frame(self, raw, generation, sequence, receiver_id, receiver_revision, document_epoch):
        with self.session.lock:
            owner = self._active_receiver()
            if owner:
                if (receiver_id != owner['id'] or receiver_revision != str(owner['revision'])
                        or document_epoch != self.document_epoch or generation != owner['generation']):
                    return self._receiver_conflict('receiver_frame_stale', 'The screen receiver changed')
            elif receiver_id is not None or receiver_revision is not None:
                return self._receiver_conflict('receiver_frame_stale', 'This screen receiver is no longer active')
            elif document_epoch is not None and document_epoch != self.document_epoch:
                return self._receiver_conflict('receiver_document_changed', 'The reader document changed')
            if generation != self.session.generation or not self.session.running:
                return self._receiver_conflict('receiver_generation_changed', 'Screen source changed')
            if not raw or sequence < 0 or self.native is None or self.session.index is None:
                raise ValueError('Native frame OCR is unavailable or the image is invalid')
            if self.preview_frame and sequence <= self.preview_frame['sequence']:
                return self._receiver_conflict('receiver_frame_stale', 'A newer screen frame was already admitted')
            try:
                dimensions = self.native.submit(raw, generation, sequence, self.session.index.source_locale)
                if dimensions is not None:
                    dimensions = json.loads(str(dimensions))
                    width, height = dimensions['width'], dimensions['height']
                    if any(type(n) is not int or not 0 < n <= 4096 for n in (width, height)):
                        raise ValueError('Invalid native frame dimensions')
                    if self.frame_geometry and self.frame_geometry != (generation, width, height):
                        self.session.stop('Screen dimensions changed; reconnect the screen source')
                        return self._receiver_conflict('receiver_dimensions_changed', 'Reconnect the rotated screen source')
                    self.frame_geometry = (generation, width, height)
                    self.preview_frame = {'bytes': raw, 'width': width, 'height': height, 'sequence': sequence,
                        'generation': generation, 'epoch': self.document_epoch, 'owner': dict(owner) if owner else None}
            except Exception as error:
                raise ValueError('The native frame could not be admitted') from error
            return {'accepted': True, 'generation': generation, 'frame': sequence}, 202

    def accept_ocr(self, generation, sequence, raw):
        with self.session.lock:
            if generation != self.session.generation or not self.session.running:
                return []
            return self._accept_ocr(generation, sequence, raw)

    def _accept_ocr(self, generation, sequence, raw):
        value = json.loads(raw)
        width, height, blocks = value['width'], value['height'], value['blocks']
        if (type(width) is not int or type(height) is not int or not 0 < width <= 4096
                or not 0 < height <= 4096 or not isinstance(blocks, list) or len(blocks) > 128):
            raise ValueError('Invalid native OCR frame')
        if self.frame_geometry and self.frame_geometry[0] == generation and self.frame_geometry[1:] != (width, height):
            self.session.stop('Screen dimensions changed; reconnect the screen source')
            self.frame_geometry = None
            return []
        self.frame_geometry = (generation, width, height)
        settings = self.session.settings.get()
        game = self.session.index.game if self.session.index else 'zzz'
        channels = {'dialogue': getattr(settings, game + '_region', settings.region),
                    'cinematic': getattr(settings, game + '_cinematic_region', settings.cinematic_region)}
        picture = self._picture(width, height)
        positioned = presentation_lines(value, width, height)
        nte_layout = None
        if game == 'nte':
            from .caption_layout import native_nte_caption
            nte_layout = native_nte_caption(positioned, (width, height), picture,
                region_bounds(picture, channels['dialogue']))
        result = []
        texts = []
        for block in blocks:
            if (not isinstance(block, dict) or not isinstance(block.get('text'), str)
                    or len(block['text']) > 8192 or not isinstance(block.get('rect'), list)
                    or len(block['rect']) != 4 or any(type(n) is not int for n in block['rect'])
                    or not 0 <= block['rect'][0] < block['rect'][2] <= width
                    or not 0 <= block['rect'][1] < block['rect'][3] <= height):
                raise ValueError('Invalid native OCR block')
            left, top, right, bottom = block['rect']
            if picture[0] <= left < right <= picture[0] + picture[2] and picture[1] <= top < bottom <= picture[1] + picture[3]:
                texts.append(block['text'])
        for channel, region in channels.items():
            groups = []
            x, y, crop_width, crop_height = region_bounds(picture, region)
            for block in blocks:
                left, top, right, bottom = block['rect']
                # Only whole recognized blocks inside the calibrated region.
                if x <= left < right <= x + crop_width and y <= top < bottom <= y + crop_height:
                    groups.append(block['text'])
            if game == 'nte' and channel == 'dialogue' and nte_layout is not None:
                groups = list(nte_layout.groups)
            result.extend(self.session.observe(generation, sequence, groups, channel=channel, nte_layout=nte_layout,
                dialogue_menu=bool(nte_layout and nte_layout.dialogue_menu)))
        result.extend(self.session.observe(generation, sequence, texts, channel='fullframe',
            presentation_lines=positioned, frame_size=(width, height),
            dialogue_menu=bool(nte_layout and nte_layout.dialogue_menu)))
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
            def _headers(self, status, size, content_type, *, cookie=False, extra=None):
                self.response_started = True
                self.send_response(status)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(size))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Referrer-Policy', 'no-referrer')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; frame-src https://vdo.ninja; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
                if cookie:
                    self.send_header('Set-Cookie', f'toolkit_session={host.cookie}; HttpOnly; SameSite=Strict; Path=/')
                for name, value in (extra or {}).items():
                    self.send_header(name, value)
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
                self.request_bytes_read += len(raw)
                if len(raw) != size:
                    raise InterruptedError('Request was interrupted')
                return raw
            def _handle(self):
                path = urlsplit(self.path).path
                if not self._authorize(path):
                    self._json({'detail': 'App-local request required'}, 403);return
                if path in {'/api/lexirise/accounts', '/api/lexirise/accounts/select'} and host.account_sessions:
                    if self.command == 'GET' and path == '/api/lexirise/accounts':
                        with host.session.lock:
                            captured = self.headers.get('X-Toolkit-Account-Generation')
                            if captured is not None:
                                host.guard_account(captured, selecting=True)
                            self._json(host.account_sessions.status());return
                    if self.command != 'POST' or self.headers.get('X-Proxy-Transcript') != 'lexirise':
                        self._json({'detail': 'Use the account selector.'}, 403);return
                    value = json.loads(self._body(4096))
                    with host.session.lock:
                        generation = host.guard_account(self.headers.get('X-Toolkit-Account-Generation'), selecting=True)
                    if path.endswith('/select'):
                        if not isinstance(value, dict) or set(value) != {'id'} or not isinstance(value['id'], str):
                            raise ValueError('Invalid account selection')
                        self._json(host.account_sessions.select(value['id'], generation));return
                    if (not isinstance(value, dict) or set(value) - {'key', 'name'} or not isinstance(value.get('key'), str)
                            or not isinstance(value.get('name', ''), str) or len(value.get('name', '')) > 80):
                        raise ValueError('Invalid protected account registration')
                    self._json(host.account_sessions.register(value['key'], value.get('name', ''), generation));return
                if host.account_sessions:
                    from .android_account_api import dispatch
                    result = dispatch(host, self.command, path, urlsplit(self.path).query, self.headers, self._body)
                    if result is not None:
                        payload, status, scope = result
                        with host.session.lock:
                            if scope is not None:
                                scope.check()
                            self._json(payload, status);return
                if path == '/api/platform' and self.command == 'GET':
                    self._json(host.platform());return
                if path in {'/api/snapshot', '/api/status'} and self.command == 'GET':
                    self._json(host.snapshot());return
                if path == '/api/capture/preview.jpg' and self.command == 'GET':
                    try:
                        preview = host.preview(urlsplit(self.path).query)
                    except (ValueError, KeyError, TypeError):
                        self._json({'detail': 'Invalid preview crop'}, 422);return
                    with host.session.lock:
                        if preview is None or not host._preview_current(preview[0]):
                            self._json({'detail': 'No current screen preview'}, 404);return
                        self._headers(200, len(preview[1]), 'image/jpeg')
                        self.wfile.write(preview[1]);return
                if path == '/api/settings':
                    if self.command == 'GET':
                        self._json(host.session.settings.get().model_dump(mode='json'));return
                    if self.command == 'PATCH':
                        value = json.loads(self._body(1024**2))
                        with host.session.lock:
                            host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                            self._json(host.session.update_settings(value));return
                if path == '/api/capture/start' and self.command == 'POST':
                    self._body(4096)
                    with host.session.lock:
                        host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                        if host._active_receiver():
                            self._json(*host._receiver_conflict('receiver_owned', 'Use the active screen receiver controls'));return
                        generation = host.session.start()
                        self._json({**host.snapshot(), 'generation': generation});return
                if path == '/api/capture/receiver' and self.command == 'POST':
                    value = json.loads(self._body(4096))
                    with host.session.lock:
                        host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                        self._json(*host.control_receiver(value, self.headers.get('X-Toolkit-Document-Epoch')));return
                if path in {'/api/capture/stop', '/api/capture/source'} and self.command == 'POST':
                    self._body(4096)
                    with host.session.lock:
                        host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                        if host._active_receiver():
                            self._json(*host._receiver_conflict('receiver_owned', 'Use the active screen receiver controls'));return
                        host.session.stop('Screen source changed' if path.endswith('source') else 'Capture paused')
                        self._json({**host.snapshot(), 'generation': host.session.generation});return
                if path == '/api/library/import' and self.command == 'POST':
                    if self.headers.get('Transfer-Encoding') or not self.headers.get('Content-Length', '').isdigit():
                        raise ValueError('A bounded library length is required')
                    size = int(self.headers['Content-Length'])
                    if not 0 < size <= MAX_LIBRARY:
                        raise ValueError('Library is too large or empty')
                    identity = self.headers.get('X-Toolkit-Import-Id')
                    with host.session.lock:
                        generation = host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                        session = host.session
                        job = host._import_job(identity, register=True, session=session, account_generation=generation)
                    try:
                        with tempfile.TemporaryDirectory(prefix='upload-', dir=session.root) as folder:
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
                                    self.request_bytes_read += len(block)
                            self._json(session.import_library(upload, cancelled=job['cancel'].is_set,
                                publish_guard=lambda: host.publish_import(job)));return
                    finally:
                        with host.import_lock:
                            job['working'] = False
                            if job['state'] not in {'committed', 'cancelled'}:
                                job['state'] = 'failed'
                if path == '/api/library/import/cancel' and self.command == 'POST':
                    value = json.loads(self._body(4096))
                    with host.session.lock:
                        host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                        result, status = host.cancel_import(value.get('import_id'))
                    self._json(result, status);return
                if path == '/api/capture/frame' and self.command == 'POST':
                    generation, sequence = (int(self.headers.get(name, '-1')) for name in ('X-Toolkit-Generation', 'X-Toolkit-Frame'))
                    raw = self._body(MAX_FRAME)
                    if self.headers.get('Content-Type') not in {'image/jpeg', 'image/png'}:
                        raise ValueError('Native frame OCR is unavailable or the image is invalid')
                    with host.session.lock:
                        host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                        self._json(*host.submit_frame(raw, generation, sequence,
                            self.headers.get('X-Toolkit-Receiver-Id'), self.headers.get('X-Toolkit-Receiver-Revision'),
                            self.headers.get('X-Toolkit-Document-Epoch')));return
                line_match = re.fullmatch(r'/api/lines/([1-9][0-9]*)/(favorite|audio)', path)
                if line_match:
                    identity, operation = int(line_match[1]), line_match[2]
                    if operation == 'favorite' and self.command == 'PATCH':
                        value = json.loads(self._body(4096)).get('favorite')
                        if type(value) is not bool:
                            raise ValueError('Invalid favorite value')
                        with host.session.lock:
                            host.guard_account(self.headers.get('X-Toolkit-Account-Generation'))
                            if host.account_sessions:
                                identity = host.account_sessions.local_line(identity)
                            line = host.session.history.set_favorite(identity, value)
                            if line is not None:
                                host.session.state_version += 1
                            result = host.session._line(line) if line else None
                            if result and host.account_sessions:
                                result = host.account_sessions.qualify_line(result)
                        if result is None:
                            self._json({'detail': 'Line not found'}, 404);return
                        self._json(result);return
                    if operation == 'audio' and self.command == 'GET':
                        with host.session.lock:
                            if host.account_sessions:
                                identity = host.account_sessions.local_line(identity)
                            session = host.session
                            account_generation = host.account_generation
                            audio = session.audio_path(identity)
                        if audio is None:
                            self._json({'detail': 'Original recording unavailable'}, 404);return
                        size = audio.stat().st_size
                        first, last, status = 0, size - 1, 200
                        extra = {'Accept-Ranges': 'bytes'}
                        if self.headers.get('Range'):
                            match = re.fullmatch(r'bytes=([0-9]*)-([0-9]*)', self.headers['Range'])
                            if match and (match[1] or match[2]):
                                first = int(match[1]) if match[1] else max(0, size - int(match[2]))
                                last = min(size - 1, int(match[2])) if match[1] and match[2] else size - 1
                            if not match or not (match[1] or match[2]) or not 0 <= first <= last < size:
                                self._headers(416, 0, 'application/octet-stream', extra={'Content-Range': f'bytes */{size}'})
                                return
                            status = 206;extra['Content-Range'] = f'bytes {first}-{last}/{size}'
                        with audio.open('rb') as source:
                            with session.lock:
                                if host.account_sessions:
                                    host.account_sessions.guard_import(session, account_generation)
                                self._headers(status, last - first + 1, 'audio/wav' if audio.suffix == '.wav' else 'audio/mpeg', extra=extra)
                            source.seek(first);remaining = last - first + 1
                            while remaining:
                                with session.lock:
                                    if host.account_sessions and (host.session is not session or host.account_generation != account_generation):
                                        self.close_connection = True;return
                                block = source.read(min(65536, remaining))
                                if not block:
                                    break
                                self.wfile.write(block);remaining -= len(block)
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
                    document = path in {'/', '/index.html'} and self.headers.get('Sec-Fetch-Dest', 'document') == 'document'
                    epoch = host.replace_document() if document else host.document_epoch
                    raw = raw.replace(b'<head>', ('<head><meta name="toolkit-host-platform" content="android">'
                        '<meta name="toolkit-document-epoch" content="' + epoch + '">').encode())
                self._headers(200, len(raw), mimetypes.guess_type(file.name)[0] or 'application/octet-stream', cookie=path == '/')
                self.wfile.write(raw)
            def _dispatch(self):
                self.request_bytes_read = 0
                self.response_started = False
                try:
                    self._handle()
                except Exception as error:
                    self.close_connection = True
                    if self.response_started:
                        return
                    try:
                        # Closing a small unread upload can reset TCP before a
                        # Windows client receives the error. Drain only bounded
                        # remaining bytes, never a rejected multi-GiB library.
                        length = self.headers.get('Content-Length', '')
                        remaining = int(length) - self.request_bytes_read if length.isascii() and length.isdigit() and len(length) <= 20 else 0
                        if 0 < remaining <= 65536:
                            self.rfile.read(remaining)
                        status, detail = 400, {'detail': 'The local request did not complete. Check the current library before retrying.'}
                        if host.account_sessions:
                            from .android_accounts import AndroidAccountConflict
                            from .lexirise import LexiriseError
                            if isinstance(error, AndroidAccountConflict):
                                status, detail = 409, {'state': error.state, 'detail': str(error), 'account_generation': host.account_generation}
                            elif isinstance(error, LexiriseError):
                                detail = {'detail': str(error)}
                        self._json(detail, status)
                    except OSError:
                        pass
            do_GET = do_POST = do_PATCH = _dispatch
        return Handler


def start(root, frontend, native=None, enable_accounts=False, authored_accounts=False):
    global _host
    with _host_lock:
        if _host is None:
            # A stable app-local origin preserves the shared reader's existing
            # localStorage keys through offline restarts and app upgrades.
            pointer = Path(root) / 'reader-origin.json'
            port = json.loads(pointer.read_text())['port'] if pointer.is_file() else 0
            if type(port) is not int or port != 0 and not 1024 <= port <= 65535:
                raise ValueError('Invalid app-local reader origin')
            _host = AndroidHost(root, frontend, native, port=port, enable_accounts=enable_accounts,
                authored_accounts=authored_accounts)
            pending = pointer.with_suffix('.pending')
            pending.write_text(json.dumps({'port': _host.server.server_port}), encoding='utf8')
            pending.replace(pointer)
        if (_host.authored_accounts != bool(authored_accounts) or Path(root).absolute() != _host.root
                or bool(_host.account_sessions) != bool(enable_accounts or authored_accounts)):
            raise ValueError('The native startup mode cannot change within this process.')
        return _host.origin + '/'


def pause():
    with _host_lock:
        if _host:
            _host.pause()


def bootstrap_cookie():
    """Native-only bootstrap: unauthenticated loopback clients get no session."""
    with _host_lock:
        if not _host:
            raise ValueError('The private host has not started')
        return f'toolkit_session={_host.cookie}; HttpOnly; SameSite=Strict; Path=/'


def accept_ocr(generation, sequence, raw):
    with _host_lock:
        return json.dumps(_host.accept_ocr(generation, sequence, raw)) if _host else '[]'
