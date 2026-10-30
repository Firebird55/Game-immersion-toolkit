"""Verified public releases, installed by an independent process across handoff."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import Request, urlopen
import zipfile

from .runtime_bundle import RuntimeBundleError, discover_layout

REPOSITORY = 'Firebird55/Game-immersion-toolkit'
API = 'https://api.github.com/repos/' + REPOSITORY
CODE_ROOT = Path(__file__).resolve().parents[1]
MAX_DOWNLOAD = 1024 * 1024 * 1024


def version(value):
    if not re.fullmatch(r'v?\d+\.\d+\.\d+', value):
        raise ValueError('Only stable toolkit releases can be installed automatically.')
    return tuple(map(int, value.lstrip('v').split('.')))


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text(encoding='utf-8-sig'))
    except (OSError, ValueError):
        return default


def save_status(root, state, message, **extra):
    home = Path(root) / 'data/toolkit-updates'
    home.mkdir(parents=True, exist_ok=True)
    payload = {'state': state, 'message': message, 'updated_at': datetime.now(timezone.utc).isoformat(), **extra}
    pending = home / 'status.pending'
    pending.write_text(json.dumps(payload), encoding='utf-8')
    pending.replace(home / 'status.json')


def request_json(url):
    with urlopen(Request(url, headers={'User-Agent': 'Game-immersion-toolkit-updater',
                                      'Accept': 'application/vnd.github+json'}), timeout=30) as response:
        return json.load(response)


def asset(release, name):
    matches = [item for item in release.get('assets', []) if item.get('name') == name]
    if len(matches) != 1:
        raise ValueError('Release is missing a required verified asset: ' + name)
    item = matches[0]
    expected = f"https://github.com/{REPOSITORY}/releases/download/{release['tag_name']}/{name}"
    if item.get('browser_download_url') != expected:
        raise ValueError('Release asset does not belong to the toolkit repository.')
    return item


def download(item, destination, root):
    expected = item.get('size', 0)
    if not isinstance(expected, int) or not 0 < expected <= MAX_DOWNLOAD:
        raise ValueError('Release asset size is invalid.')
    count, last_report = 0, 0
    digest = hashlib.sha256()
    with urlopen(Request(item['browser_download_url'], headers={'User-Agent': 'Game-immersion-toolkit-updater'}), timeout=30) as response, destination.open('wb') as output:
        while chunk := response.read(1024 * 1024):
            count += len(chunk)
            if count > expected:
                raise ValueError('Release download exceeds its declared size.')
            output.write(chunk)
            digest.update(chunk)
            if time.monotonic() - last_report > 1:
                save_status(root, 'downloading', 'Downloading ' + item['name'], downloaded_bytes=count, total_bytes=expected)
                last_report = time.monotonic()
    if count != expected:
        raise ValueError('Release download was incomplete; the current version is still running.')
    return digest.hexdigest()


def verify_and_extract(archive, checksums, provenance, destination, tag, commit):
    expected = {}
    for line in checksums.read_text(encoding='utf-8').splitlines():
        match = re.fullmatch(r'([a-fA-F0-9]{64})  ([^/\\]+)', line)
        if not match or match[2] in expected:
            raise ValueError('Invalid release checksum manifest.')
        expected[match[2]] = match[1].lower()
    for path in (archive, provenance):
        with path.open('rb') as stream:
            actual = hashlib.file_digest(stream, 'sha256').hexdigest()
        if expected.get(path.name) != actual:
            raise ValueError('Release checksum verification failed; nothing was installed.')
    proof = read_json(provenance, {})
    if proof.get('repository') != REPOSITORY or proof.get('version') != tag[1:] or proof.get('sourceCommit') != commit:
        raise ValueError('Release provenance does not match the published tag.')
    prefix = 'Game-immersion-toolkit-' + tag[1:]
    with zipfile.ZipFile(archive) as bundle:
        total, names = 0, set()
        for member in bundle.infolist():
            path = PurePosixPath(member.filename)
            # Windows paths must not escape, alias another file, or create streams.
            if (path.is_absolute() or not path.parts or path.parts[0] != prefix
                    or any(part in {'.', '..'} or ':' in part or part.endswith((' ', '.')) for part in path.parts)
                    or '\\' in member.filename or member.filename.casefold() in names
                    or (member.external_attr >> 16) & 0o170000 == 0o120000):
                raise ValueError('Unsafe release archive path.')
            names.add(member.filename.casefold())
            total += member.file_size
            if total > 4 * MAX_DOWNLOAD:
                raise ValueError('Release archive expands beyond the allowed size.')
        bundle.extractall(destination)
    source = destination / prefix
    if read_json(source / 'PROVENANCE.json') != proof:
        raise ValueError('Packaged provenance differs from the release.')
    package = read_json(source / 'package.json', {})
    if package.get('name') != 'game-immersion-toolkit' or package.get('version') != tag[1:]:
        raise ValueError('Packaged toolkit version is invalid.')
    return source


@contextmanager
def update_lock(path):
    from .export_lock import ExportLock
    lock = ExportLock(path)
    acquired = lock.acquire()
    try:
        yield acquired
    finally:
        lock.close()


def update_once(root, current):
    if discover_layout().mode == 'bundle':
        # The source installer acquires another legacy lock and installs build
        # dependencies. It cannot safely run inside a frozen supervising guard.
        raise RuntimeBundleError('Frozen updates require the verified supervising host; source ZIP installation is unavailable.')
    root = Path(root).resolve()
    home = root / 'data/toolkit-updates'
    home.mkdir(parents=True, exist_ok=True)
    # OS-held exclusive lock is released on crashes, unlike a stale PID file.
    with update_lock(home / 'install.lock') as acquired:
        if not acquired:
            return
        save_status(root, 'checking', 'Checking GitHub for a newer stable toolkit release', installed_version=current)
        try:
            release = request_json(API + '/releases/latest')
            tag = release['tag_name']
            if release.get('draft') or release.get('prerelease'):
                raise ValueError('The latest release is not a stable public release.')
            if version(tag) <= version(current):
                save_status(root, 'current', 'Toolkit is up to date', installed_version=current, available_version=tag[1:])
                return
            commit = request_json(API + '/commits/' + tag)['sha']
            if not re.fullmatch('[a-f0-9]{40}', commit):
                raise ValueError('Could not verify the published release commit.')
            with tempfile.TemporaryDirectory(prefix='release-', dir=home) as temporary:
                folder = Path(temporary)
                names = [f'Game-immersion-toolkit-{tag[1:]}.zip', 'SHA256SUMS', 'PROVENANCE.json']
                for name in names:
                    download(asset(release, name), folder / name, root)
                save_status(root, 'verifying', 'Verifying release checksums and source commit', available_version=tag[1:])
                source = verify_and_extract(*(folder / name for name in names), folder / 'extracted', tag, commit)
                save_status(root, 'installing', 'Preparing replacement dependencies; capture continues', available_version=tag[1:])
                with (home / 'install.log').open('w', encoding='utf-8') as log:
                    process = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File',
                        str(source / 'scripts/update-companion.ps1'), '-SourceRoot', str(source), '-Root', str(root)],
                        stdout=log, stderr=log, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
                if process.returncode:
                    raise ValueError('Replacement preparation failed. Current capture was retained. See data/toolkit-updates/install.log; retry from Setup.')
                save_status(root, 'current', 'Toolkit updated successfully', installed_version=tag[1:], available_version=tag[1:])
        except Exception as error:
            # Detailed paths and runtime output remain in the private local log.
            save_status(root, 'error', 'Toolkit update failed; the current installation is retained. Retry in Setup. ' + str(error))


class ToolkitUpdater:
    def __init__(self, root):
        self.root = Path(root)
        self.layout = discover_layout()
        self.current = self.layout.version or read_json(CODE_ROOT / 'package.json', {})['version']
        self.stop = threading.Event()
        self.thread = None
        self.process = None
        self.lock = threading.Lock()

    def status(self):
        if os.environ.get('PROXY_TRANSCRIPT_HOST_MANAGED') == '1':
            return {'state': 'unavailable', 'message': 'This desktop host keeps ownership during its session. Install a verified newer executable after quitting; automatic supervised updates are not yet available.',
                'installed_version': self.current, 'enabled': False}
        if self.layout.mode == 'bundle':
            return {'state': 'unavailable', 'message': 'Frozen updates require a verified supervising host; the current candidate is retained.',
                'installed_version': self.current, 'enabled': False}
        value = read_json(self.root / 'data/toolkit-updates/status.json', {})
        if value.get('state') in {'checking', 'downloading', 'verifying', 'installing'}:
            with update_lock(self.root / 'data/toolkit-updates/install.lock') as acquired:
                if acquired:
                    value.update(state='error', message='The previous toolkit update was interrupted. Check and install now to retry.')
                    value.pop('stage', None)
        value['installed_version'] = self.current
        value['enabled'] = read_json(self.root / 'data/toolkit-updates/preferences.json', {}).get('enabled', True)
        if value.get('state') == 'installing':
            value['stage'] = read_json(self.root / 'data/toolkit-updates/stage.json', {}).get('message')
        return value

    def configure(self, enabled):
        if os.environ.get('PROXY_TRANSCRIPT_HOST_MANAGED') == '1':
            raise RuntimeBundleError('Quit the desktop host before installing a verified update. Automatic supervised updates are not yet available.')
        if self.layout.mode == 'bundle':
            raise RuntimeBundleError('Automatic frozen updates are unavailable until supervised takeover is verified.')
        home = self.root / 'data/toolkit-updates'
        home.mkdir(parents=True, exist_ok=True)
        pending = home / 'preferences.pending'
        pending.write_text(json.dumps({'enabled': enabled}), encoding='utf-8')
        pending.replace(home / 'preferences.json')
        if enabled:
            self.request()

    def request(self):
        if os.environ.get('PROXY_TRANSCRIPT_HOST_MANAGED') == '1':
            return False
        if self.layout.mode == 'bundle':
            return False
        with self.lock:
            if self.process and self.process.poll() is None:
                return False
            if os.name != 'nt' or not (self.root / 'data/processes.json').is_file():
                return False
            # The downloader must survive retirement of this backend at handoff.
            home = self.root / 'data/toolkit-updates'
            home.mkdir(parents=True, exist_ok=True)
            with (home / 'updater.log').open('a', encoding='utf-8') as log:
                self.process = subprocess.Popen(self.layout.child_command('toolkit-update', ['--root', str(self.root),
                    '--current', self.current, '--detach']), cwd=self.layout.application_root,
                    env=self.layout.child_environment('toolkit-update'), stdin=subprocess.DEVNULL, stdout=log, stderr=log,
                    creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
            return True

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        def monitor():
            # The launcher publishes its owned-process record after health is ready.
            if self.stop.wait(10):
                return
            while not self.stop.is_set():
                if self.status()['enabled']:
                    self.request()
                self.stop.wait(6 * 3600)
        self.thread = threading.Thread(target=monitor, daemon=True, name='toolkit-release-updates')
        self.thread.start()

    def close(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=2)
            if self.thread.is_alive():
                raise RuntimeError('Toolkit update monitor is still stopping; handoff is blocked.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--current', required=True)
    parser.add_argument('--detach', action='store_true')
    args = parser.parse_args()
    if args.detach:
        layout = discover_layout()
        if layout.mode == 'bundle':
            raise RuntimeBundleError('Frozen updater detachment requires the verified supervising host.')
        # A short-lived launcher exits before installation starts. The updater
        # is not in the retiring backend's live child tree during handoff.
        subprocess.Popen(layout.child_command('toolkit-update', ['--root', str(args.root),
                          '--current', args.current]), cwd=layout.application_root,
                         env=layout.child_environment('toolkit-update'), stdin=subprocess.DEVNULL,
                         creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0) |
                                       getattr(subprocess, 'CREATE_NEW_PROCESS_GROUP', 0))
    else:
        update_once(args.root, args.current)
