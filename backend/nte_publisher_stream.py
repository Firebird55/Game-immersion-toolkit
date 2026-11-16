"""Private, short-lived loopback streams for the managed NTE package parser.

Only registered verified TOCs and checksum-covered UCAS ranges are exposed.
The nonce is passed to the owned child through stdin, never to the frontend.
"""
from contextlib import AbstractContextManager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import re
import hashlib
import secrets
import sys
import threading
from urllib.parse import parse_qs, urlsplit

from . import nte_release as release
from .preparation_errors import PreparationFailure

TRANSFER = 4 * 1024**2


def check(condition):
    if not condition:
        raise PreparationFailure('unsupported_game_format',
            'NTE publisher streams failed verification; the previous prepared snapshot is retained.')


def _complete_global(container):
    # CUE reads aligned global blocks including their padding. That padding is
    # outside the per-block SHA1, so authenticate the entire small global file.
    check(not container.paths and container.ucas.size <= 16 * 1024**2)
    path = container.root / 'complete.ucas'
    data = path.read_bytes() if path.is_file() and path.stat().st_size == container.ucas.size else b''
    if hashlib.md5(data).hexdigest() != container.ucas.digest:
        release.save_file(container.region, container.branch, container.ucas, path)
        data = path.read_bytes()
    check(len(data) == container.ucas.size and hashlib.md5(data).hexdigest() == container.ucas.digest)
    return lambda at, size: data[at:at + size]


class Broker(AbstractContextManager):
    def __init__(self, containers):
        check(0 < len(containers) <= 128)
        self.nonce = secrets.token_urlsafe(32)
        self._streams, self._descriptors = {}, []
        self.failures = []
        self.delivered = 0
        self._lock = threading.Lock()
        for name, container in containers.items():
            check(isinstance(name, str) and len(name) <= 160 and
                  re.fullmatch(r'[A-Za-z0-9_/-]+\.utoc', name) and
                  not name.startswith('/') and '..' not in name and '//' not in name)
            toc_id, ucas_id = secrets.token_hex(16), secrets.token_hex(16)
            self._streams[toc_id] = (len(container.raw), lambda at, n, data=container.raw: data[at:at + n])
            read = (_complete_global(container) if name.rsplit('/', 1)[-1] == 'global.utoc'
                    else container.read_stored)
            self._streams[ucas_id] = (container.ucas.size, read)
            self._descriptors.append((name, toc_id, len(container.raw), ucas_id, container.ucas.size))
        broker = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = 'HTTP/1.1'

            def log_message(self, *_args):
                pass

            def reject(self, status):
                self.send_response(status)
                self.send_header('Content-Length', '0')
                self.end_headers()

            def do_GET(self):
                target = urlsplit(self.path)
                parts = target.path.split('/')
                if (target.scheme or target.netloc or target.fragment or len(parts) != 3 or
                        not re.fullmatch(r'[A-Za-z0-9_-]{43}', parts[1]) or
                        not secrets.compare_digest(parts[1], broker.nonce)):
                    return self.reject(403)
                stream = broker._streams.get(parts[2])
                try:
                    query = parse_qs(target.query, strict_parsing=True, keep_blank_values=True)
                except ValueError:
                    return self.reject(400)
                if stream is None or set(query) != {'offset', 'size'}:
                    return self.reject(400)
                if any(len(query[k]) != 1 or not re.fullmatch(r'0|[1-9][0-9]{0,12}', query[k][0]) for k in query):
                    return self.reject(400)
                at, size = int(query['offset'][0]), int(query['size'][0])
                if size > TRANSFER or not 0 <= at <= stream[0] - size:
                    return self.reject(416)
                try:
                    data = stream[1](at, size)
                    check(isinstance(data, bytes) and len(data) == size)
                except Exception as error:
                    with broker._lock:
                        broker.failures.append(error)
                    return self.reject(502)
                self.send_response(200)
                self.send_header('Content-Type', 'application/octet-stream')
                self.send_header('Content-Length', str(len(data)))
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                # Logical bytes committed to this response, not a measurement
                # of publisher transfer or acknowledgement by the child.
                with broker._lock:
                    broker.delivered += len(data)
                try:
                    self.wfile.write(data)
                except (BrokenPipeError, ConnectionResetError):
                    return

        class Server(ThreadingHTTPServer):
            request_queue_size = 32

            def handle_error(self, request, client_address):
                error = sys.exc_info()[1]
                if not isinstance(error, (ConnectionError, TimeoutError)):
                    with broker._lock:
                        broker.failures.append(error)

        self._server = Server(('127.0.0.1', 0), Handler)
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever,
                                        kwargs={'poll_interval': 0.05}, daemon=True)

    @property
    def descriptors(self):
        prefix = f'http://127.0.0.1:{self._server.server_port}/{self.nonce}/'
        return [{'name': name, 'toc_url': prefix + toc, 'toc_size': toc_size,
                 'ucas_url': prefix + ucas, 'ucas_size': ucas_size}
                for name, toc, toc_size, ucas, ucas_size in self._descriptors]

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *args):
        self._server.shutdown()
        self._server.server_close()
        self._thread.join(timeout=2)
        check(not self._thread.is_alive())
