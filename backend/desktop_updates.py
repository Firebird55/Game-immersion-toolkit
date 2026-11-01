"""Updates are prepared in a background thread and activated by the one host.

This module never starts another launcher, releases the operation lease, edits
application files, restores old data, or treats a saved PID as ownership.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import stat
import threading
import time
import uuid

from .bundle_host import _atomic_json, _reject_links

ROOTS = ('settings_root', 'data_root', 'cache_root', 'tool_root', 'work_root', 'state_root', 'default_export_root')
PROTOCOL = 1
STORAGE_EPOCH = 1


class UpdateError(RuntimeError):
    pass


def require_compatible(current, candidate):
    if (current.mode != 'bundle' or candidate.layout.mode != 'bundle'
            or getattr(current, 'storage_epoch', 1) != STORAGE_EPOCH
            or getattr(current, 'host_protocol', 1) != PROTOCOL
            or candidate.storage_epoch != STORAGE_EPOCH or candidate.host_protocol != PROTOCOL):
        raise UpdateError('This update needs a different storage or host protocol. Install a compatible release manually.')
    if any(getattr(current, field) != getattr(candidate.layout, field) for field in ROOTS):
        raise UpdateError('The update cannot change this installation’s writable folders.')


def copy_test_state(layout, stop_event, *, max_bytes=64 * 1024**3, max_files=100_000):
    """Copy closed stores only; caller must already prove its writer tree dead.

    The result has separate roots. It cannot write through to durable state,
    credentials, export destinations or caches. No hard links or symlinks.
    """
    base = layout.work_root / 'desktop-updates' / uuid.uuid4().hex
    _reject_links(base)
    base.mkdir(parents=True, exist_ok=False, mode=0o700)
    user = base / 'user'
    roots = dict(settings_root=user, data_root=user / 'data', cache_root=user / 'cache',
        tool_root=user / 'tools', work_root=user / 'work', state_root=user / 'state',
        default_export_root=user / 'exports')
    copied = replace(layout, **roots)
    for root in roots.values():
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
    count, total = 0, 0
    skipped = {getattr(layout, field) for field in ROOTS if field != 'settings_root'}
    for source, destination, exclusions in (
        (layout.settings_root, copied.settings_root, skipped),
        (layout.data_root, copied.data_root, {layout.cache_root, layout.work_root,
            layout.state_root, layout.tool_root, layout.default_export_root} - {layout.data_root}),
    ):
        if not source.exists():
            continue
        _reject_links(source)
        for directory, children, files in os.walk(source, followlinks=False):
            directory = Path(directory)
            children[:] = [name for name in children if directory / name not in exclusions]
            for name in children:
                path = directory / name
                _reject_links(path)
                (destination / path.relative_to(source)).mkdir(parents=True, exist_ok=True, mode=0o700)
            for name in files:
                path = directory / name
                if path == layout.data_root / 'companion-operation.lock':
                    continue
                if stop_event.is_set():
                    raise UpdateError('Update cancelled while preparing its test copy.')
                _reject_links(path)
                info = path.stat()
                count += 1
                total += info.st_size
                if not stat.S_ISREG(info.st_mode) or count > max_files or total > max_bytes:
                    raise UpdateError('The test copy exceeds its bounded file inventory.')
                target = destination / path.relative_to(source)
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with path.open('rb') as reader, os.fdopen(descriptor, 'wb') as writer:
                    written = 0
                    while chunk := reader.read(1024 * 1024):
                        if stop_event.is_set():
                            raise UpdateError('Update cancelled while preparing its test copy.')
                        written += len(chunk)
                        if written > info.st_size:
                            raise UpdateError('A supposedly closed store changed while copying.')
                        writer.write(chunk)
                    if written != info.st_size or path.stat().st_mtime_ns != info.st_mtime_ns:
                        raise UpdateError('A supposedly closed store changed while copying.')
                    writer.flush()
                    os.fsync(writer.fileno())
    return copied


def read_record(path, *, limit=32768):
    _reject_links(path)
    if not path.exists():
        return None
    if path.stat().st_size > limit:
        raise UpdateError('The local update record exceeds its bound.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise UpdateError('The local update record is invalid.')
    return value


class DesktopUpdates:
    def __init__(self, host, *, prepare=None):
        self.host = host
        self.prepare = prepare
        self.home = host.layout.state_root / 'desktop-updates'
        self.lock = threading.RLock()
        self.thread = None
        self.pending = None
        self.busy = False
        self.enabled = True
        self.next_check = 0
        self.supported = host.layout.mode == 'bundle' and host.layout.profile == 'runtime'
        self.value = dict(state='idle' if self.supported else 'unavailable',
            message='Ready to check for toolkit updates.' if self.supported else
                'Automatic installation requires an eligible frozen runtime release.',
            installed_version=host.layout.version, available_version='', stage='idle')

    def initialize(self):
        saved = read_record(self.home / 'preferences.json')
        if saved is not None:
            if set(saved) != {'enabled'} or type(saved['enabled']) is not bool:
                raise UpdateError('Saved update preferences are invalid.')
            self.enabled = saved['enabled']

    def status(self):
        with self.lock:
            return {**self.value, 'supported': self.supported, 'enabled': self.enabled}

    def progress(self, state, message, **extra):
        with self.lock:
            self.value.update(state=state, stage=state, message=str(message)[:1024],
                installed_version=self.host.layout.version, updated_at=datetime.now(timezone.utc).isoformat())
            self.value.update({key: value for key, value in extra.items()
                if key in {'available_version', 'downloaded_bytes', 'total_bytes'}})
            _atomic_json(self.home / 'status.json', self.status())
        if self.host.log:
            self.host.log.write(message, source='Update')

    def configure(self, enabled):
        if type(enabled) is not bool:
            raise UpdateError('Automatic updates must be enabled or disabled.')
        with self.lock:
            _atomic_json(self.home / 'preferences.json', {'enabled': enabled})
            self.enabled = enabled
        return self.status()

    def request(self):
        with self.lock:
            if not self.supported or self.busy or self.host.stop_requested.is_set():
                return {**self.status(), 'started': False}
            self.busy = True
            self.progress('checking', 'Checking for a verified toolkit release.')
            self.thread = threading.Thread(target=self._prepare, name='desktop-update-prepare', daemon=True)
            self.thread.start()
            return {**self.status(), 'started': True}

    def _prepare(self):
        try:
            if self.prepare is None:
                from .desktop_release import prepare_update
                prepare = prepare_update
            else:
                prepare = self.prepare
            candidate = prepare(self.host.layout, self.host.layout.version,
                lambda message: self.progress('preparing', message), self.host.stop_requested)
            with self.lock:
                if candidate is None:
                    self.progress('current', 'No newer eligible toolkit release is available.')
                    self.busy = False
                else:
                    require_compatible(self.host.layout, candidate)
                    self.pending = candidate
        except Exception as error:
            self.progress('error', 'Update preparation failed (' + type(error).__name__ + '). The current version is still running; retry from Settings.')
            with self.lock:
                self.busy = False
        finally:
            self.next_check = time.monotonic() + 6 * 3600

    def tick(self):
        with self.lock:
            candidate, self.pending = self.pending, None
        if candidate is not None:
            try:
                self.host.install_update(candidate)
            finally:
                with self.lock:
                    self.busy = False
        elif self.enabled and self.supported and time.monotonic() >= self.next_check:
            self.request()

    def stopped(self):
        return self.thread is None or not self.thread.is_alive()
