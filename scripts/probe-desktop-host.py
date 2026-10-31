"""Exercise the actual frozen host with isolated state and a reduced PATH.

The report contains exact artifact identities and booleans, never local paths,
process IDs, tokens, account records or raw application logs. This is a native
headless lifecycle check, not browser/tray/capture or complete R19 acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import psutil
from backend.bundle_host import ExclusiveFileLease, HostProbeError
from backend.runtime_payload import validate, executable_target, digest


class ProbeFailure(RuntimeError):
    """Only fixed public error codes may enter a report."""


def inventory_identity(receipt):
    return hashlib.sha256(json.dumps({'files': receipt['files'], 'directories': receipt['directories']},
        sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def public_identity(receipt):
    if (receipt.get('profile') not in {'runtime', 'runtime-experiment'}
            or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', str(receipt.get('build_id', '')))):
        raise ProbeFailure('invalid-artifact-identity')
    return {key: receipt[key] for key in ('source_commit', 'build_id', 'profile', 'version')}


def child_kind(arguments):
    try:
        index = arguments.index('--runtime-child')
        return arguments[index + 1] if arguments[index + 2] == '--' else None
    except (ValueError, IndexError):
        return None


def alive(process):
    try:
        return process.is_running() and process.status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def child_environment(base):
    keep = {'systemroot', 'windir', 'temp', 'tmp', 'tmpdir', 'lang', 'lc_all', 'display',
            'wayland_display', 'xdg_runtime_dir', 'dbus_session_bus_address'}
    environment = {name: value for name, value in os.environ.items() if name.lower() in keep}
    # HOME and Windows profile folders are isolated even if a native dependency
    # consults them outside the application's explicit layout contract.
    environment.update(HOME=str(base / 'home'), USERPROFILE=str(base / 'home'),
        LOCALAPPDATA=str(base / 'local'), APPDATA=str(base / 'roaming'),
        XDG_CONFIG_HOME=str(base / 'config'), XDG_DATA_HOME=str(base / 'xdg-data'),
        XDG_CACHE_HOME=str(base / 'xdg-cache'), QT_QPA_PLATFORM='offscreen',
        PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    environment['PATH'] = (os.pathsep.join((str(Path(os.environ['SystemRoot']) / 'System32'),
        os.environ['SystemRoot'])) if os.name == 'nt' else '/usr/bin:/bin')
    return environment


class FrozenHost:
    def __init__(self, executable, user, environment):
        self.executable, self.user, self.environment = executable, user, environment
        self.port = None
        self.observed = {}
        self.service_processes = {}
        self.stdout_closed = threading.Event()
        self.process = subprocess.Popen([str(executable), '--headless', '--no-browser', '--data-root', str(user),
            '--port', '0', '--api-port', '0'], cwd=user.parent, env=environment,
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace',
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.identity = psutil.Process(self.process.pid)
        self.reader = threading.Thread(target=self._read, daemon=True)
        self.reader.start()

    def _read(self):
        try:
            for line in self.process.stdout:
                # The host reports only the actual bound public socket here.
                match = re.search(r'\[Host\] Transcript ready at http://127\.0\.0\.1:([0-9]{1,5})\.', line)
                if match and 1024 < int(match[1]) < 65536:
                    self.port = int(match[1])
        finally:
            self.stdout_closed.set()

    def observe(self):
        if not alive(self.identity):
            return []
        descendants = self.identity.children(recursive=True)
        for process in descendants:
            try:
                self.observed[(process.pid, process.create_time())] = process
                if child_kind(process.cmdline()) in {'api', 'frontend', 'gateway'}:
                    self.service_processes[(process.pid, process.create_time())] = process
            except psutil.NoSuchProcess:
                pass
        return descendants

    def wait(self, predicate, timeout, code, *, require_running=True):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.observe()
            if require_running and self.process.poll() is not None:
                raise ProbeFailure('frozen-host-exited')
            try:
                if predicate():
                    return
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(.1)
        raise ProbeFailure(code)

    def get(self, path):
        with urlopen(f'http://127.0.0.1:{self.port}' + path, timeout=3) as response:
            if response.status != 200:
                raise ProbeFailure('frozen-http-response')
            return response.read(1024 * 1024)

    def route(self):
        return json.loads((self.user / 'state/desktop-host-route.json').read_text())['active']

    def crash_api(self):
        # Authority comes from a live retained launcher and its current tree,
        # never a PID recorded in route/status files or discovered by name alone.
        candidates = []
        for process in self.observe():
            try:
                if child_kind(process.cmdline()) == 'api' and Path(process.exe()).resolve() == self.executable.resolve():
                    candidates.append((len(process.parents()), process))
            except psutil.NoSuchProcess:
                pass
        if not candidates:
            raise ProbeFailure('owned-api-not-found')
        process = max(candidates, key=lambda item: item[0])[1]
        if not alive(self.identity) or not any(parent == self.identity for parent in process.parents()):
            raise ProbeFailure('owned-api-identity-changed')
        process.kill()

    def quit(self, timeout):
        completed = subprocess.run([str(self.executable), '--request-quit', '--data-root', str(self.user)],
            cwd=self.user.parent, env=self.environment, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if completed.returncode != 0:
            raise ProbeFailure('frozen-quit-not-acknowledged')
        self.process.wait(timeout=timeout)
        if self.process.returncode != 0:
            raise ProbeFailure('frozen-quit-failed')

    def verify_stopped(self, timeout):
        lock = ExclusiveFileLease(self.user / 'data/companion-operation.lock')
        def acquire():
            try:
                lock.acquire()
                if any(alive(process) for process in self.service_processes.values()):
                    raise ProbeFailure('frozen-lease-released-before-services-stopped')
                return True
            except HostProbeError:
                return False
        try:
            self.wait(acquire, timeout, 'frozen-lease-retained', require_running=False)
        finally:
            lock.close()
        self.wait(lambda: not any(alive(process) for process in self.observed.values()), timeout,
            'frozen-descendants-remain', require_running=False)
        self.reader.join(timeout=3)
        if not self.stdout_closed.is_set():
            raise ProbeFailure('frozen-log-pipe-retained')
        self.process.stdout.close()

    def cleanup(self):
        # Failed probes still clean up only processes observed as descendants
        # during this invocation. psutil verifies creation identity before kill.
        self.observe()
        if self.process.poll() is None:
            try:
                self.quit(50)
            except Exception:
                if alive(self.identity):
                    self.identity.kill()
                self.process.wait(timeout=10)
        deadline = time.monotonic() + 15
        while any(alive(process) for process in self.observed.values()) and time.monotonic() < deadline:
            time.sleep(.1)
        remaining = [process for process in self.observed.values() if alive(process)]
        for process in remaining:
            try:
                process.kill()
            except psutil.NoSuchProcess:
                pass
        _gone, surviving = psutil.wait_procs(remaining, timeout=10)
        if any(alive(process) for process in surviving):
            raise ProbeFailure('probe-cleanup-incomplete')
        self.reader.join(timeout=3)
        if not self.reader.is_alive():
            self.process.stdout.close()


def probe(runtime, provenance, output, timeout):
    report = {'schema': 'toolkit-desktop-native-probe-v1', 'status': 'failed', 'passed': False, 'checks': {},
        'execution': 'actual-frozen-process',
        'r19_complete': False, 'native_acceptance': 'partial-headless-lifecycle',
        'browser_tray_capture': 'not-run', 'frozen_update_transaction': 'not-run'}
    active = None
    try:
        runtime = runtime.absolute()
        receipt_raw = provenance.read_bytes()
        receipt = json.loads(receipt_raw)
        executable = runtime / ('ProxyTranscriptRuntime.exe' if os.name == 'nt' else 'ProxyTranscriptRuntime')
        target = executable_target(executable)
        validate(runtime, receipt, target, candidate=True)
        report.update(public_identity(receipt), target=target,
            runtime_receipt_sha256=hashlib.sha256(receipt_raw).hexdigest(),
            inventory_sha256=inventory_identity(receipt), executable_sha256=digest(executable))
        report['checks']['closed_inventory'] = True
        base = Path(tempfile.mkdtemp(prefix='toolkit-frozen-host-')).resolve()
        user = base / 'synthetic-user'
        environment = child_environment(base)
        for name in ('home', 'local', 'roaming', 'config', 'xdg-data', 'xdg-cache'):
            (base / name).mkdir(mode=0o700)
        preferences = user / 'state/desktop-updates/preferences.json'
        preferences.parent.mkdir(mode=0o700, parents=True)
        preferences.write_text('{"enabled":false}\n', encoding='utf-8')
        check = subprocess.run([str(executable), '--host-check', '--data-root', str(user)],
            cwd=base, env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding='utf-8', errors='replace', timeout=timeout,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        if check.returncode or json.loads(check.stdout).get('mode') != 'bundle':
            raise ProbeFailure('frozen-host-check-failed')
        report['checks']['host_check'] = True
        active = FrozenHost(executable, user, environment)
        active.wait(lambda: active.port is not None, timeout, 'frozen-startup-timeout')
        if json.loads(active.get('/api/health'))['status'] != 'ok' or b'<html' not in active.get('/').lower():
            raise ProbeFailure('frozen-reader-not-ready')
        report['checks']['frontend_gateway'] = True
        initial_port, old_route = active.port, active.route()
        active.crash_api()
        active.wait(lambda: active.route()['apiPort'] != old_route['apiPort']
            and json.loads(active.get('/api/health'))['status'] == 'ok', timeout, 'frozen-recovery-timeout')
        if active.port != initial_port or active.route()['frontendPort'] != old_route['frontendPort']:
            raise ProbeFailure('frozen-recovery-changed-origin')
        report['checks']['api_crash_recovery'] = True
        active.observe()
        active.quit(55)
        active.verify_stopped(20)
        report['checks']['owned_shutdown'] = True
        active = FrozenHost(executable, user, environment)
        active.wait(lambda: active.port is not None, timeout, 'frozen-restart-timeout')
        if json.loads(active.get('/api/health'))['status'] != 'ok':
            raise ProbeFailure('frozen-restart-not-ready')
        report['checks']['same_state_restart'] = True
        active.observe()
        active.identity.kill()
        active.process.wait(timeout=10)
        active.verify_stopped(30)
        report['checks']['host_crash_cleanup'] = True
        validate(runtime, receipt, target, candidate=True)
        report['checks']['immutable_payload'] = True
        report['status'] = 'passed'
        report['passed'] = True
    except Exception as error:
        report['error'] = str(error) if isinstance(error, ProbeFailure) else type(error).__name__
    finally:
        if active is not None:
            try:
                active.cleanup()
            except Exception:
                report.update(status='failed', passed=False, cleanup_error='probe-cleanup-incomplete')
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(report))
    return 0 if report['status'] == 'passed' else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--provenance', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=180)
    args = parser.parse_args()
    if not 15 <= args.timeout <= 600:
        parser.error('Timeout must be between 15 and 600 seconds.')
    provenance = args.provenance or args.runtime_root.parent.parent / 'CANDIDATE-PROVENANCE.json'
    return probe(args.runtime_root, provenance, args.output, args.timeout)


if __name__ == '__main__':
    raise SystemExit(main())
