"""Local destination preferences, honest estimates and interruptible export jobs."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid

from .game_paths import GAMES, settings_path, discover_install
from .mobile_export_layout import latest_export

ACTIVE = {'preparing', 'exporting', 'cancelling'}


def stop_export_process(process):
    """Only terminate the process tree owned by this export, including decoders."""
    if process.poll() is not None:
        return
    if sys.platform == 'win32':
        subprocess.run(['taskkill.exe', '/PID', str(process.pid), '/T', '/F'],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15,
                       creationflags=subprocess.CREATE_NO_WINDOW)
    else:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    process.wait(timeout=5)


class MobileExportManager:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self._lock = threading.RLock()
        self._cancel = threading.Event()
        self._thread = self._process = self._picker = self._picker_result = None
        self._picker_started = 0.0
        self._picker_message = ''
        self._status = {'state': 'idle', 'progress': 0, 'message': 'Ready to export a mobile library'}
        self._estimates = {}

    @property
    def preferences_path(self):
        return settings_path().with_name('mobile-library.json')

    def destination(self):
        try:
            value = json.loads(self.preferences_path.read_text(encoding='utf-8')).get('destination_folder')
            if isinstance(value, str) and Path(value).is_absolute():
                return Path(value)
        except (OSError, ValueError):
            pass
        return self.root / 'output/mobile-libraries'

    def _save_destination(self, folder):
        path = self.preferences_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix('.pending')
        temp.write_text(json.dumps({'destination_folder': str(folder)}), encoding='utf-8')
        os.replace(temp, path)

    def _validate_folder(self, folder):
        path = Path(folder).expanduser()
        if not path.is_absolute() or len(str(path)) > 2000:
            raise ValueError('Choose an absolute destination folder on this PC.')
        path = path.resolve()
        if path == self.root or self.root in path.parents:
            allowed = self.root / 'output'
            if path != allowed and allowed not in path.parents:
                raise ValueError('Save exports outside toolkit source files, or inside its output folder.')
        for parent in [path, *path.parents]:
            if parent != self.root and (parent / '.git').exists():
                raise ValueError('Choose a private folder outside a Git repository.')
        for game in GAMES:
            install = discover_install(game)
            if install:
                install = install.resolve()
                target = path / game
                if install == path or install in path.parents or target == install or install in target.parents:
                    raise ValueError('Choose a destination outside installed game files.')
        existing = path
        while not existing.exists():
            existing = existing.parent
        if not existing.is_dir():
            raise ValueError('The destination must be a folder, not a file.')
        return path, existing

    def _finish_picker(self):
        if self._picker and self._picker.poll() is None and not Path(str(self._picker_result) + '.ready').exists() and time.monotonic() - self._picker_started > 25:
            self.close_picker()
            self._picker_message = 'Windows did not show the folder browser. Paste a folder path or try Browse again.'
        if self._picker and self._picker.poll() is not None:
            try:
                value = json.loads(self._picker_result.read_text(encoding='utf-8-sig'))
                if value.get('folder'):
                    folder, _ = self._validate_folder(value['folder'])
                    self._save_destination(folder)
                elif value.get('error'):
                    self._picker_message = 'The Windows folder browser failed. Paste a folder path or try Browse again.'
            except (OSError, ValueError):
                if getattr(self._picker, 'returncode', 0):
                    self._picker_message = 'The folder browser closed unexpectedly. Paste a folder path or try Browse again.'
            finally:
                self._picker_result.unlink(missing_ok=True)
                Path(str(self._picker_result) + '.ready').unlink(missing_ok=True)
                self._picker = self._picker_result = None

    def close_picker(self):
        with self._lock:
            if not self._picker:
                return False
            process, result = self._picker, self._picker_result
            if process.poll() is None:
                process.terminate()
                process.wait(timeout=5)
            # Never apply an abandoned selection. Keep the user's saved destination.
            result.unlink(missing_ok=True)
            Path(str(result) + '.ready').unlink(missing_ok=True)
            self._picker = self._picker_result = None
            self._picker_message = 'Folder browser closed. You can paste a destination or try Browse again.'
            return True

    def status(self):
        with self._lock:
            self._finish_picker()
            status = {**self._status, 'destinationFolder': str(self.destination()),
                      'browseActive': bool(self._picker), 'browseMessage': self._picker_message,
                      'browsePhase': 'open' if self._picker and Path(str(self._picker_result) + '.ready').exists() else 'starting' if self._picker else None}
        if status.get('estimate') and status.get('outputFolder'):
            try:
                status['estimate'] = {**status['estimate'], 'freeBytes': shutil.disk_usage(status['outputFolder']).free}
            except OSError:
                pass
        return status

    def browse(self, folder=None):
        if sys.platform != 'win32':
            raise ValueError('The folder picker requires Windows. You can paste a folder path instead.')
        with self._lock:
            self._finish_picker()
            if self._picker or self._status['state'] in ACTIVE:
                return False
            initial, _ = self._validate_folder(folder or self.destination())
            directory = self.preferences_path.parent
            directory.mkdir(parents=True, exist_ok=True)
            result = directory / ('mobile-folder-' + uuid.uuid4().hex + '.json')
            startup = subprocess.STARTUPINFO()
            startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startup.wShowWindow = 1  # SW_SHOWNORMAL: do not inherit the hidden companion's show state.
            self._picker = subprocess.Popen(['powershell.exe', '-NoProfile', '-STA', '-ExecutionPolicy', 'Bypass',
                '-File', str(self.root / 'scripts/select-export-folder.ps1'),
                '-InitialPath', str(initial), '-ResultPath', str(result)],
                creationflags=subprocess.CREATE_NO_WINDOW, startupinfo=startup,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self._picker_result = result
            self._picker_started = time.monotonic()
            self._picker_message = ''
            return True

    def preview(self, game, include_audio=True, destination_folder=None):
        if game not in GAMES:
            raise ValueError('Unsupported game')
        folder, existing = self._validate_folder(destination_folder or self.destination())
        data = self.root / 'data'
        inputs = ([data / 'voice-assets/manifest.json', data / 'voice-assets/learned-manifest.json']
                  if game == 'zzz' else [data / game / 'textmap.json'])
        signature = tuple((str(p), p.stat().st_size, p.stat().st_mtime_ns) for p in inputs if p.is_file())
        key = (game, signature)
        with self._lock:
            cached = self._estimates.get(key)
        if cached is None:
            records, count = [], 0
            if game == 'zzz':
                entries = {}
                for path in inputs:
                    if path.is_file():
                        entries.update(json.loads(path.read_text(encoding='utf-8')).get('entries', {}))
                count = len(entries)
            elif inputs[0].is_file():
                records = json.loads(inputs[0].read_text(encoding='utf-8')).get('records', [])
                count = len(records) if game == 'hito' else sum(bool(r.get('audio')) for r in records)
            # A range is intentionally explicit: source codecs and movie trims
            # make exact MP3 byte counts unknowable before conversion.
            catalog = count * 650 + 2048
            cached = {'rows': count, 'catalog': catalog, 'audio': 0 if game == 'hito' else count * 96 * 1024,
                      'basis': 'Typical MP3 clip sizes; refined as voices convert'}
            with self._lock:
                self._estimates = {key: cached}
        audio = cached['audio'] if include_audio else 0
        estimated = cached['catalog'] + audio
        basis = cached['basis'] if include_audio else 'Catalog metadata estimate; no voices included'
        # A previous completed export is a better starting point than typical sizes.
        output = folder / game
        try:
            completed, catalog_path = latest_export(output, game)
            if catalog_path.is_file():
                files = list(completed.glob('*.zip')) if include_audio else [catalog_path]
                estimated = sum(p.stat().st_size for p in files)
                basis = 'Previous completed export; game updates can change the size'
        except (OSError, ValueError, KeyError, TypeError):
            pass
        free = shutil.disk_usage(existing).free
        return {'destinationFolder': str(folder), 'estimatedBytes': estimated,
                'estimateLowBytes': round(estimated * .6), 'estimateHighBytes': round(estimated * 1.8),
                'workingBytes': estimated * 3 + (512 * 1024**2 if include_audio else 0),
                'freeBytes': free, 'rows': cached['rows'], 'basis': basis, 'includeAudio': include_audio}

    def cancel(self):
        with self._lock:
            if self._status['state'] not in {'preparing', 'exporting', 'cancelling'}:
                return False
            self._cancel.set()
            self._status.update(state='cancelling', message='Stopping export and its decoder…')
            process = self._process
        if process:
            threading.Thread(target=self._stop, args=(process,), daemon=True).start()
        return True

    def _stop(self, process):
        try:
            stop_export_process(process)
        except (OSError, subprocess.SubprocessError):
            # Do not report cancellation complete until the monitor sees exit.
            with self._lock:
                self._status['message'] = 'Still stopping the export. Waiting for its process to exit.'
        else:
            with self._lock:
                if self._process is process and self._cancel.is_set():
                    self._status.update(state='cancelled', message='Export cancelled. Completed clips are saved; export again to resume.')

    def start(self, game, include_audio=True, destination_folder=None):
        with self._lock:
            self._finish_picker()
            if self._thread and self._thread.is_alive() or self._picker or self._status['state'] in ACTIVE:
                return False
            preview = self.preview(game, include_audio, destination_folder)
            folder, _ = self._validate_folder(preview['destinationFolder'])
            output = folder / game
            output.mkdir(parents=True, exist_ok=True)
            probe = output / ('.write-check-' + uuid.uuid4().hex)
            try:
                probe.write_bytes(b'')
            finally:
                probe.unlink(missing_ok=True)
            self._save_destination(folder)
            self._cancel = threading.Event()
            self._status = {'state': 'preparing', 'game': game, 'progress': 0,
                'message': 'Checking local game library', 'estimate': preview, 'outputFolder': str(output)}
            self._thread = threading.Thread(target=self._run, args=(game, include_audio, output), daemon=True)
            self._thread.start()
            return True

    def _worker_args(self, game, include_audio, output):
        args = [sys.executable, '-u', '-m', 'backend.mobile_export_worker', '--root', str(self.root),
                '--game', game, '--output', str(output)]
        return args if include_audio else [*args, '--catalog-only']

    def _run(self, game, include_audio, output):
        process = None
        try:
            args = self._worker_args(game, include_audio, output)
            with self._lock:
                if self._cancel.is_set():
                    return
                process = subprocess.Popen(args, cwd=self.root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                    text=True, encoding='utf-8', creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
                    start_new_session=sys.platform != 'win32', env={**os.environ, 'PYTHONIOENCODING': 'utf-8'})
                self._process = process
            for line in process.stdout:
                try:
                    values = json.loads(line)
                except ValueError:
                    continue
                with self._lock:
                    if not self._cancel.is_set() and isinstance(values, dict) and 'state' in values:
                        self._status.update(values)
            code = process.wait()
            with self._lock:
                if not self._cancel.is_set() and (code or self._status['state'] not in {'complete', 'error'}):
                    self._status.update(state='error', message='Export stopped unexpectedly. Check disk space and resume.')
        except Exception:
            with self._lock:
                if not self._cancel.is_set():
                    self._status.update(state='error', message='Could not start export. Check the destination and resume.')
        finally:
            if process and process.poll() is None:
                self._stop(process)
            with self._lock:
                exited = process is None or process.poll() is not None
                if exited:
                    self._process = None
                if self._cancel.is_set() and exited:
                    self._status.update(state='cancelled', message='Export cancelled. Completed clips are saved; export again to resume.')
