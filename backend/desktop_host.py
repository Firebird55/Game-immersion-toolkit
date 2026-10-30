"""One desktop owner, visible lifecycle logs and retained service processes.

The host never compiles or installs a runtime on the user's machine. Frozen
children use fixed dispatch and verified application resources. A source checkout
uses the same host after its developer has built the static desktop frontend.
"""
from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import queue
import re
import secrets
import signal
import sys
import threading
import time
from urllib.error import URLError
from urllib.request import Request, urlopen
import webbrowser

from .bundle_host import ExclusiveFileLease, HostProbeError, _atomic_json, _reject_links
from .owned_process import OwnedProcess
from .runtime_bundle import RuntimeBundleError, discover_layout


class HostError(RuntimeError):
    pass


def selected_environment(data_root=None):
    """Select platform roots only at the top-level executable entrypoint."""
    env = dict(os.environ)
    if getattr(sys, 'frozen', False):
        if data_root is None:
            if sys.platform == 'win32':
                base = Path(env.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'Game Immersion Toolkit'
            elif sys.platform == 'darwin':
                base = Path.home() / 'Library/Application Support/Game Immersion Toolkit'
            else:
                base = Path(env.get('XDG_DATA_HOME', Path.home() / '.local/share')) / 'game-immersion-toolkit'
        else:
            base = Path(data_root)
        if not base.is_absolute():
            raise HostError('The user data folder must be absolute.')
        roots = dict(settings_root=base, data_root=base / 'data', cache_root=base / 'cache',
                     tool_root=base / 'tools', work_root=base / 'work', state_root=base / 'state',
                     default_export_root=base / 'exports')
        for name, path in roots.items():
            env['PROXY_TRANSCRIPT_' + name.upper()] = str(path)
    elif data_root is not None:
        base = Path(data_root)
        if not base.is_absolute():
            raise HostError('The source installation folder must be absolute.')
        env['PROXY_TRANSCRIPT_PROJECT_ROOT'] = str(base)
    return env


_SECRET = re.compile(r'(?i)(authorization\s*[:=]\s*(?:bearer\s+)?|bearer\s+|(?:api[_-]?key|token|password|secret|cookie)[\"\']?\s*[=:]\s*[\"\']?)([^\s\"\',;}]+)')


def safe_log(value):
    value = str(value).replace('\r', '').replace('\n', ' | ')
    value = re.sub(r'[\x00-\x08\x0b-\x1f\x7f]', '', value)
    value = _SECRET.sub(lambda match: match[1] + '[redacted]', value)
    return value[:4096]


class HostLog:
    def __init__(self, root):
        _reject_links(root)
        root.mkdir(parents=True, exist_ok=True)
        self.lines = deque(maxlen=2000)
        self.events = queue.Queue(maxsize=2000)
        self.lock = threading.Lock()
        self.logger = logging.Logger('desktop-host')
        self.handler = RotatingFileHandler(root / 'desktop.log', maxBytes=2 * 1024 * 1024,
                                          backupCount=4, encoding='utf-8')
        self.handler.setFormatter(logging.Formatter('%(message)s'))
        self.logger.addHandler(self.handler)

    def write(self, message, *, source='Host'):
        line = datetime.now().astimezone().isoformat(timespec='seconds') + ' [' + source + '] ' + safe_log(message)
        with self.lock:
            self.logger.info(line)
            self.lines.append(line)
            try:
                self.events.put_nowait(line)
            except queue.Full:
                pass  # The bounded GUI buffer must never block service pipes.
        if sys.stdout:
            try:
                print(line, flush=True)
            except (OSError, UnicodeError):
                pass

    def close(self):
        self.handler.close()


class Service:
    def __init__(self, name, command, *, cwd, env, log, retained_fds=()):
        self.name, self.log = name, log
        self.ready = queue.Queue(maxsize=1)
        self.started = time.monotonic()
        self.owner = OwnedProcess(command, cwd=cwd, env=env, text=True,
            independent_session=True, retained_fds=retained_fds)
        self.threads = []
        for channel in ('stdout', 'stderr'):
            thread = threading.Thread(target=self._read, args=(channel,), name=name + '-' + channel, daemon=True)
            self.threads.append(thread)
            thread.start()

    def _read(self, channel):
        stream = getattr(self.owner.process, channel)
        try:
            while line := stream.readline(8192):
                text = line.rstrip()
                if channel == 'stdout':
                    try:
                        value = json.loads(text)
                        if isinstance(value, dict) and value.get('ready') is True:
                            self.ready.put_nowait(value)
                            continue
                    except (ValueError, queue.Full):
                        pass
                self.log.write(text, source=self.name)
        except (OSError, ValueError):
            pass

    def wait_ready(self, stopping, timeout=120):
        deadline = time.monotonic() + timeout
        notice = time.monotonic() + 10
        while time.monotonic() < deadline and not stopping.is_set():
            if self.owner.poll() is not None:
                raise HostError(f'{self.name} exited during startup (code {self.owner.poll()}).')
            try:
                return self.ready.get(timeout=.1)
            except queue.Empty:
                if time.monotonic() >= notice:
                    self.log.write('Still starting; waiting for service readiness.', source=self.name)
                    notice += 10
        raise HostError(f'{self.name} did not become ready within {timeout:g} seconds.')

    def stop(self):
        self.owner.stop(timeout=10)
        for thread in self.threads:
            thread.join(timeout=2)
            if thread.is_alive():
                raise HostError(f'{self.name} log pipe did not close after shutdown.')
        self.owner.close_streams()


def request_json(port, path, *, payload=None, timeout=5, headers=None):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(f'http://127.0.0.1:{port}' + path, data=data,
                      headers={'Content-Type': 'application/json', **(headers or {})})
    with urlopen(request, timeout=timeout) as response:
        result = response.read(1024 * 1024 + 1)
    if len(result) > 1024 * 1024:
        raise HostError('Local service response exceeded its bound.')
    return json.loads(result)


class HostControl:
    """Local instance reuse. The private capability is never placed in a URL."""
    def __init__(self, path, host):
        self.path, self.host = path, host
        self.token = secrets.token_urlsafe(32)
        control = self
        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_):
                pass
            def do_POST(self):
                allowed = (self.client_address[0] == '127.0.0.1' and not self.headers.get('Origin')
                    and self.headers.get_all('X-Toolkit-Control') == [control.token]
                    and self.path in {'/open', '/quit'} and self.headers.get('Content-Length') == '0')
                if allowed:
                    if self.path == '/quit':
                        host.stop_requested.set()
                    else:
                        host.open_requested.set()
                        host.show_logs_requested.set()
                self.send_response(204 if allowed else 403)
                self.send_header('Content-Length', '0')
                self.end_headers()
        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True, name='desktop-control')
        self.thread.start()
        from .protected_storage import private_write
        private_write(path, json.dumps({'schema': 'toolkit-host-control-v1',
            'port': self.server.server_port, 'token': self.token}).encode('utf-8'))

    def close(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        from .atomic_files import remove
        remove(self.path)


def contact_instance(path, action='open'):
    try:
        _reject_links(path)
        if path.stat().st_size > 2048:
            return False
        value = json.loads(path.read_text(encoding='utf-8'))
        port, token = value['port'], value['token']
        if (value['schema'] != 'toolkit-host-control-v1' or type(port) is not int or not 1024 < port < 65536
                or not isinstance(token, str) or not re.fullmatch(r'[A-Za-z0-9_-]{43}', token)):
            return False
        request = Request(f'http://127.0.0.1:{port}/{action}', data=b'', headers={'X-Toolkit-Control': token})
        with urlopen(request, timeout=3) as response:
            return response.status == 204
    except (OSError, ValueError, KeyError, TypeError):
        return False


class DesktopHost:
    def __init__(self, layout, *, frontend_root=None, port=3000, api_port=8766, browser=True,
                 service_factory=Service, open_browser=webbrowser.open):
        self.layout, self.frontend_root = layout, frontend_root
        self.port, self.api_port = port, api_port
        self.browser, self.open_browser = browser, open_browser
        self.service_factory = service_factory
        self.stop_requested = threading.Event()
        self.open_requested = threading.Event()
        self.show_logs_requested = threading.Event()
        self.finished = threading.Event()
        self.ready = threading.Event()
        self.services = {}
        self.ports = {}
        self.status = 'Starting'
        self.exit_code = 0
        self.log = None
        self.control = None
        self.lease = ExclusiveFileLease(layout.data_root / 'companion-operation.lock')
        self.route_path = layout.state_root / 'desktop-host-route.json'
        self.control_path = layout.state_root / 'desktop-host-control.json'
        self.browser_opened = False
        self.capture_running = False
        self.failures = {name: deque() for name in ('API', 'Frontend', 'Gateway')}

    @property
    def url(self):
        return f'http://127.0.0.1:{self.port}'

    def acquire(self):
        try:
            self.lease.acquire()
        except HostProbeError as error:
            if error.code == 'operation-busy' and contact_instance(self.control_path):
                return False
            raise HostError('Another launcher or update owns this installation. Wait for it to finish; no process was stopped.') from error
        try:
            self.log = HostLog(self.layout.state_root / 'logs')
            self.control = HostControl(self.control_path, self)
        except BaseException:
            self.lease.close()
            raise
        return True

    def _start(self, name):
        kinds = {'API': 'api', 'Frontend': 'frontend', 'Gateway': 'gateway'}
        kind = kinds[name]
        arguments = {'API': ['--port', '0', '--shutdown-stdin'], 'Frontend': ['--port', '0'],
            'Gateway': ['--state', str(self.route_path), '--api-port', str(self.api_port),
                        '--frontend-port', str(self.port), '--shutdown-stdin']}[name]
        if name == 'Frontend' and self.layout.mode == 'source':
            arguments += ['--root', str(self.frontend_root)]
        env = self.layout.child_environment(kind)
        env.update(PYTHONUNBUFFERED='1', PYTHONIOENCODING='utf-8', PROXY_TRANSCRIPT_HOST_MANAGED='1')
        self.log.write('Starting ' + name.lower() + '.')
        service = self.service_factory(name, self.layout.child_command(kind, arguments),
            cwd=self.layout.application_root, env=env, log=self.log,
            retained_fds=self.lease.retained_descriptors())
        self.services[name] = service
        ready = service.wait_ready(self.stop_requested)
        if name == 'Gateway':
            self.api_port, self.port = ready['apiPort'], ready['frontendPort']
        else:
            port = ready.get('port')
            if type(port) is not int or not 1024 < port < 65536:
                raise HostError(name + ' reported an invalid private port.')
            self.ports[name] = port
        self.log.write(name + ' is ready.')

    def _publish(self):
        _atomic_json(self.route_path, {'schema': 'toolkit-desktop-route-v1', 'active': {
            'apiPort': self.ports['API'], 'frontendPort': self.ports['Frontend']}})

    def _open(self, *, requested=False):
        self.open_requested.clear()
        if not self.browser and not requested:
            return
        try:
            if self.open_browser(self.url):
                self.log.write('Opened the transcript in your default browser.')
            else:
                self.log.write('Open ' + self.url + ' in your browser to read the transcript.')
        except Exception as error:
            self.log.write('Browser could not open (' + type(error).__name__ + '); open ' + self.url + ' manually.')
        self.browser_opened = True

    def _status(self):
        try:
            value = request_json(self.ports['API'], '/api/status', timeout=2)
            capture = value.get('capture', {})
            self.capture_running = capture.get('running') is True
            # Only an allowlisted status summary, never a transcript/account dump.
            current = str(capture.get('status', capture.get('message', 'Ready')))
            if current != self.status:
                self.status = current
                self.log.write(current, source='Capture')
        except (OSError, ValueError, TypeError):
            pass

    def run(self):
        try:
            self.log.write('Game immersion toolkit ' + self.layout.version + ' starting. Logs stay open while it runs.')
            self._start('API')
            self._start('Frontend')
            self._publish()
            self._start('Gateway')
            self.status = 'Ready'
            self.ready.set()
            self.log.write('Transcript ready at ' + self.url + '. Use Share for another device on your local network.')
            self._open()
            next_status = 0
            while not self.stop_requested.wait(.2):
                if self.open_requested.is_set():
                    self._open(requested=True)
                for name, service in tuple(self.services.items()):
                    code = service.owner.poll()
                    if code is None:
                        continue
                    self.status = name + ' restarting'
                    self.log.write(f'{name} exited (code {code}); stopping its remaining owned children before restart.')
                    service.stop()  # A failed drain forbids replacement.
                    del self.services[name]
                    now = time.monotonic()
                    failures = self.failures[name]
                    while failures and now - failures[0] > 300:
                        failures.popleft()
                    failures.append(now)
                    if len(failures) > 5:
                        raise HostError(name + ' failed repeatedly. Automatic restart stopped; reopen the toolkit after checking its logs.')
                    delay = min(15, 2 ** (len(failures) - 1))
                    self.log.write(f'Restarting {name.lower()} in {delay} seconds.')
                    if self.stop_requested.wait(delay):
                        break
                    self._start(name)
                    if name == 'API' and self.capture_running:
                        request_json(self.ports['API'], '/api/capture/start', payload={})
                        self.log.write('Resumed capture after API recovery; confirmed transcript lines were retained.')
                    if name != 'Gateway':
                        self._publish()
                    self.status = 'Ready'
                    self.log.write(name + ' recovered; existing transcript readers can reconnect.')
                if time.monotonic() >= next_status and not self.stop_requested.is_set():
                    self._status()
                    next_status = time.monotonic() + 3
        except Exception as error:
            self.exit_code = 1
            self.status = 'Recovery required'
            self.log.write(type(error).__name__ + ': ' + str(error))
        finally:
            self._shutdown()
            while not self.finished.is_set():
                # A failed cleanup is a retained recovery state, never license
                # to release the installation lease and start another writer.
                time.sleep(2)
                self._shutdown()

    def _shutdown(self):
        self.ready.clear()
        self.log.write('Stopping transcript services and waiting for saved work.')
        api = self.services.get('API')
        if api and api.owner.poll() is None and 'API' in self.ports:
            try:
                request_json(self.ports['API'], '/api/runtime/quiesce', payload={}, timeout=32,
                             headers={'X-Proxy-Transcript': 'update'})
                self.log.write('Capture and runtime writes have stopped.')
            except (OSError, ValueError) as error:
                self.log.write('Graceful drain did not finish (' + type(error).__name__ + '); stopping the owned process tree before releasing the installation.')
        all_stopped = True
        for name in ('Gateway', 'API', 'Frontend'):
            service = self.services.get(name)
            if service:
                try:
                    service.stop()
                    del self.services[name]
                    self.log.write(name + ' stopped.')
                except Exception as error:
                    all_stopped = False
                    self.exit_code = 1
                    self.log.write(name + ' cleanup failed: ' + type(error).__name__ + '. Installation ownership is retained; no replacement will start.')
        if all_stopped:
            try:
                from .atomic_files import remove
                remove(self.route_path)
                if self.control:
                    self.control.close()
                    self.control = None
                self.lease.close()
                self.log.write('Stopped. Saved transcripts remain available for the next launch.')
                self.finished.set()
            except OSError:
                self.status = 'Finishing shutdown'
                self.log.write('A local state file is still in use. Retaining ownership and retrying shutdown.')
        else:
            self.status = 'Recovery required: children are still stopping'


def validate_frontend(layout, selected):
    from .desktop_frontend import FrontendBuild, frontend_root
    if layout.mode == 'source':
        selected = selected or layout.application_root / 'output/desktop-frontend'
    args = argparse.Namespace(root=selected, retained_root=[])
    root = frontend_root(args, layout)
    return root, FrontendBuild(root).build_id


def main(arguments=None):
    parser = argparse.ArgumentParser(description='Start the desktop transcript with visible logs and a tray icon.')
    parser.add_argument('--data-root', type=Path)
    parser.add_argument('--frontend-root', type=Path)
    parser.add_argument('--port', type=int, default=3000)
    parser.add_argument('--api-port', type=int, default=8766)
    parser.add_argument('--headless', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--host-check', action='store_true')
    parser.add_argument('--request-quit', action='store_true')
    args = parser.parse_args(arguments)
    if not args.headless and not args.host_check and not args.request_quit:
        from .desktop_host_ui import ensure_console
        ensure_console()
        print('Game immersion toolkit: checking runtime and frontend resources…', flush=True)
    if any(not 0 <= value < 65536 for value in (args.port, args.api_port)):
        parser.error('Ports must be between 0 and 65535.')
    env = selected_environment(args.data_root)
    layout = discover_layout(env)
    if args.request_quit:
        lease = ExclusiveFileLease(layout.data_root / 'companion-operation.lock')
        try:
            lease.acquire()
        except HostProbeError:
            if not contact_instance(layout.state_root / 'desktop-host-control.json', 'quit'):
                return 1
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                try:
                    lease.acquire()
                    break
                except HostProbeError:
                    time.sleep(.2)
            else:
                return 1
        lease.close()
        return 0
    root, frontend_id = validate_frontend(layout, args.frontend_root)
    if args.host_check:
        if not args.headless:
            from PySide6 import QtCore, QtGui, QtWidgets  # Package import, no display/app creation.
        print(json.dumps({'host': 'available', 'mode': layout.mode, 'frontend_build': frontend_id,
                          'native_acceptance': 'not-run', 'r19_complete': False}))
        return 0
    os.environ.update(env)
    host = DesktopHost(layout, frontend_root=root, port=args.port, api_port=args.api_port,
                       browser=not args.no_browser)
    if not host.acquire():
        return 0
    for signum in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signum, lambda *_: host.stop_requested.set())
    if args.headless:
        host.run()
        return host.exit_code
    from .desktop_host_ui import run_ui
    return run_ui(host)


def launch(arguments=None):
    try:
        return main(arguments)
    except Exception as error:
        message = 'Toolkit could not start: ' + safe_log(error)
        print(message, file=sys.stderr, flush=True)
        args = sys.argv[1:] if arguments is None else arguments
        if not any(flag in args for flag in ('--headless', '--host-check', '--request-quit')):
            from .desktop_host_ui import show_startup_error
            show_startup_error(message)
        return 1


if __name__ == '__main__':
    raise SystemExit(launch())
