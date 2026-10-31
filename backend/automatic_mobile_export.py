"""One host-local rule record and a recoverable queue using the existing exporter."""
from __future__ import annotations
from .runtime_paths import data_root as runtime_data_root
from .runtime_bundle import child_command, discover_layout, resource_path
import copy
import json
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time
import zipfile

from .export_lock import ExportLock
from .game_paths import settings_path, discover_install
from .game_assets import asset_adapter
from .languages import GAME_LOCALES, LOCALE_NAMES
from .mobile_export_controls import MobileExportManager, stop_export_process
from .mobile_library import digest, file_digest
from .mobile_export_layout import file_title, work_folder, catalog_name, export_folder_name
from .voice_pack_probe import probe, LABELS


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_suffix('.pending')
    with pending.open('w', encoding='utf-8') as stream:
        json.dump(value, stream, ensure_ascii=False)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(pending, path)


def publish(candidate, destination, recovery, guard=lambda: None):
    """The last good public ZIP survives copy, checksum and replace failures."""
    candidate, destination, recovery = map(Path, (candidate, destination, recovery))
    if not destination.parent.parent.is_dir():
        raise FileNotFoundError('Export drive or folder is unavailable.')
    destination.parent.mkdir(exist_ok=True)
    recovery.parent.mkdir(parents=True, exist_ok=True)
    pending = destination.with_suffix('.zip.pending')
    if shutil.disk_usage(destination.parent).free < candidate.stat().st_size + 16 * 1024**2:
        raise OSError('Not enough space in the export folder.')
    try:
        with candidate.open('rb') as source, pending.open('wb') as target:
            while chunk := source.read(4 * 1024**2):
                guard()
                target.write(chunk)
            target.flush()
            os.fsync(target.fileno())
        if file_digest(candidate) != file_digest(pending):
            raise OSError('Export copy verification failed.')
        guard()
        if destination.exists():
            backup = recovery.with_suffix('.pending')
            shutil.copyfile(destination, backup)
            os.replace(backup, recovery)
        getattr(guard, 'force', guard)()
        os.replace(pending, destination)
    finally:
        pending.unlink(missing_ok=True)


def prune_completed_work(output, game, home):
    """Keep current packs/cache and the separate previous publication, not every ZIP revision."""
    output, home = Path(output), Path(home).resolve()
    pointer = json.loads((output / 'latest.json').read_text(encoding='utf-8'))
    current = pointer['revision']
    work = work_folder(output)
    for parent in (output, work / 'previous-libraries', work / 'libraries'):
        if not parent.is_dir():
            continue
        for folder in parent.iterdir():
            if not folder.is_dir() or folder.is_symlink() or folder.is_junction():
                continue
            catalog = folder / catalog_name(game)
            archives = [catalog] if catalog.is_file() else list(folder.glob('* - Mobile Library.zip'))
            if len(archives) != 1:
                continue
            with zipfile.ZipFile(archives[0]) as archive:
                if archive.getinfo('manifest.json').file_size > 8 * 1024**2:
                    continue
                manifest = json.loads(archive.read('manifest.json'))
            revision = manifest.get('revision')
            if manifest.get('game') != game or revision == current or folder.name not in (revision, export_folder_name(game, revision)):
                continue
            # Resolve and check every directory before recursive removal on Windows.
            resolved = folder.resolve()
            if not resolved.is_relative_to(home) or resolved == home or any(
                    (Path(root) / name).is_symlink() or (Path(root) / name).is_junction()
                    for root, directories, files in os.walk(folder) for name in directories + files):
                continue
            shutil.rmtree(resolved)


class AutomaticMobileExports:
    def __init__(self, root, *, home=None, install_lookup=discover_install):
        self.root = Path(root)
        self.home = Path(home) if home else settings_path().parent / 'automatic-mobile-libraries'
        self.path = self.home / 'rules.json'
        self.install_lookup = install_lookup
        self.lock = threading.RLock()
        self.stop = threading.Event()
        self.wake = threading.Event()
        self.configuration_error = ''
        self.thread = self.process = None
        self.observed = {}
        self.owner = ExportLock(self.home / 'owner.lock')
        self.picker = MobileExportManager(root, scope=('automatic-destination', 'local'))
        try:
            self.data = json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.data, dict) or self.data.get('version') != 1 or not isinstance(self.data.get('rules'), dict):
                raise ValueError('Invalid automatic export settings; restore rules.json from backup.')
        except (ValueError, TypeError):
            self.configuration_error = 'Automatic export settings could not be read. Restore the local rules.json file; existing exports are safe.'
            self.data = {'version': 1, 'rules': {}}
        except FileNotFoundError:
            self.data = {'version': 1, 'rules': {}}

    def choices(self, game):
        adapter, _ = asset_adapter(game)
        catalog = json.loads(resource_path('public/mobile-capture/games-data.json').read_text(encoding='utf-8'))
        entry = next(row for row in catalog['games'] if row['id'] == game)
        targets = [locale for locale in entry['targets'] if locale in adapter.TEXT_LOCALES]
        install = self.install_lookup(game)
        with self.lock:
            rule = copy.deepcopy(self.data['rules'].get(game, {}))
        rows = []
        stamp = None
        for locale in GAME_LOCALES[game]:
            if locale not in adapter.SUPPORTED_LOCALES:
                continue
            state = probe(game, install, locale)
            job = rule.get('jobs', {}).get(locale, {})
            if state == 'unknown' and install and job.get('state') == 'complete':
                try:
                    stamp = stamp or adapter.fingerprint(install)
                    if job.get('fingerprint') == digest([stamp, adapter.LANGUAGE_INDEX_VERSION, locale,
                                                       rule['languages'][locale], rule['destination']]):
                        state = 'present'
                except (OSError, ValueError, KeyError):
                    pass
            rows.append({'locale': locale, 'name': LOCALE_NAMES[locale], 'voice_state': state, 'voice_label': LABELS[state]})
        return rows, targets


    def status(self, game):
        choices, targets = self.choices(game)
        with self.lock:
            rule = copy.deepcopy(self.data['rules'].get(game, {'enabled': False, 'paused': False, 'destination': '', 'languages': {}, 'jobs': {}}))
        picker = self.picker.status()
        return {**rule, 'configurationError': self.configuration_error, 'locales': choices, 'translations': targets, 'browseActive': picker['browseActive'],
                'browsedDestination': picker['destinationFolder'], 'browseMessage': picker['browseMessage']}

    def configure(self, game, enabled, destination, languages):
        if self.configuration_error:
            raise ValueError(self.configuration_error)
        choices, targets = self.choices(game)
        allowed = {row['locale'] for row in choices}
        if not isinstance(languages, dict) or any(locale not in allowed or target not in targets for locale, target in languages.items()):
            raise ValueError('Select supported game voice and translation languages.')
        if enabled and not languages:
            raise ValueError('Select at least one voice language.')
        if enabled:
            destination = str(self.picker._validate_folder(destination)[0])
            if self.home.resolve() == Path(destination) or self.home.resolve() in Path(destination).parents:
                raise ValueError('Choose an export folder outside local recovery storage.')
        with self.lock:
            old = self.data['rules'].get(game, {})
            candidate = copy.deepcopy(self.data)
            candidate['rules'][game] = {**old, 'enabled': enabled, 'paused': old.get('paused', False),
                'destination': destination, 'languages': languages, 'jobs': {locale: job for locale, job in old.get('jobs', {}).items()
                    if locale in languages and old.get('languages', {}).get(locale) == languages[locale]}}
            atomic_json(self.path, candidate)
            self.data = candidate
        self.wake.set()
        return self.status(game)

    def action(self, game, action):
        with self.lock:
            candidate = copy.deepcopy(self.data)
            rule = candidate['rules'].get(game)
            if not rule:
                raise ValueError('Save automatic export settings first.')
            if action in ('pause', 'resume'):
                rule['paused'] = action == 'pause'
            elif action == 'retry':
                for job in rule['jobs'].values():
                    job.pop('fingerprint', None)
                    job.pop('storageFailures', None)
                    job['state'] = 'queued'
            elif action != 'update':
                raise ValueError('Unknown automatic export action.')
            atomic_json(self.path, candidate)
            self.data = candidate
        self.wake.set()
        return self.status(game)

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stop.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True, name='automatic-mobile-export')
        self.thread.start()

    def close(self):
        self.stop.set()
        self.wake.set()
        if self.thread:
            self.thread.join(timeout=30)
            if self.thread.is_alive():
                raise RuntimeError('Automatic export has not stopped; runtime handoff cancelled.')
        if self.process and self.process.poll() is None:
            raise RuntimeError('Automatic export process cleanup is incomplete; runtime handoff cancelled.')
        self.picker.close_picker()

    def _loop(self):
        while not self.stop.is_set() and not self.owner.acquire():
            self.stop.wait(2)
        if self.stop.is_set():
            self.owner.close()
            return
        try:
            # A previous companion may have finished before ownership transferred.
            if self.configuration_error:
                return
            if self.path.exists():
                with self.lock:
                    self.data = json.loads(self.path.read_text(encoding='utf-8'))
            while not self.stop.is_set():
                self.reconcile()
                self.wake.wait(30)
                self.wake.clear()
        finally:
            self.owner.close()

    def _set(self, game, locale, **status):
        with self.lock:
            rule = self.data['rules'].get(game, {})
            if locale not in rule.get('languages', {}):
                return
            rule.setdefault('jobs', {}).setdefault(locale, {}).update(status)
            try:
                atomic_json(self.path, self.data)
            except OSError:
                rule['jobs'][locale].update(state='waiting', message='Local recovery storage is unavailable. Free space or reconnect it; previous saved settings are preserved.')

    def reconcile(self):
        with self.lock:
            rules = copy.deepcopy(self.data['rules'])
        for game, rule in rules.items():
            if self.stop.is_set():
                return
            if not rule['enabled'] or rule.get('paused'):
                continue
            for locale, translation in rule['languages'].items():
                try:
                    self._job(game, locale, translation, rule)
                except (OSError, ValueError):
                    self._set(game, locale, state='waiting', message='Waiting for the game, export drive, tools or free space. Prerequisites will be checked again.')
                except Exception:
                    self._set(game, locale, state='error', message='Export stopped unexpectedly. Check the game and destination, then Retry.')

    def _job(self, game, locale, translation, rule):
        install = self.install_lookup(game)
        if not install or not Path(rule['destination']).is_dir():
            raise FileNotFoundError()
        pack = probe(game, install, locale)
        if pack in ('missing', 'incomplete'):
            self._set(game, locale, state='waiting', message=LABELS[pack])
            return
        adapter, _ = asset_adapter(game)
        stamp = adapter.fingerprint(install)
        identity = digest([stamp, adapter.LANGUAGE_INDEX_VERSION, locale, translation, rule['destination']])
        job = rule.get('jobs', {}).get(locale, {})
        name = f"{file_title(game)} - {LOCALE_NAMES[locale]} - {LOCALE_NAMES.get(translation, translation)} translation - Mobile Library.zip".replace(' — ', ' - ')
        destination = Path(rule['destination']) / file_title(game) / name
        if job.get('fingerprint') == identity and job.get('state') == 'complete' and destination.is_file():
            return
        if job.get('state') == 'error' and job.get('attempt') == identity:
            return
        observed, since = self.observed.get((game, locale), (None, 0))
        if observed != identity:
            self.observed[(game, locale)] = (identity, time.monotonic())
        if observed != identity or time.monotonic() - since < 30:
            self._set(game, locale, state='waiting', message='Waiting for stable game files.')
            return
        from .media_tools import ffmpeg_executable
        if not ffmpeg_executable() or game not in ('beyond', 'heavyrain') and not (runtime_data_root(self.root) / 'voice-assets/vgmstream/vgmstream-cli.exe').is_file():
            self._set(game, locale, state='waiting', message='Prepare game voice tools in Setup. Tools will be checked again automatically.')
            return
        if shutil.disk_usage(self.home).free < max(512 * 1024**2, job.get('estimatedBytes', 0) * 2):
            self._set(game, locale, state='waiting', message='Waiting for enough local working space (at least 512 MiB; more for the estimated library).')
            return
        if shutil.disk_usage(rule['destination']).free < (job.get('bytes') or job.get('estimatedBytes', 0)) + 16 * 1024**2:
            self._set(game, locale, state='waiting', message='Waiting for enough free space in the export folder.')
            return
        key = digest([game, locale, translation])[:24]
        output = self.home / 'work' / key / 'exports'
        output.mkdir(parents=True, exist_ok=True)
        def guard():
            with self.lock:
                current = self.data['rules'].get(game, {})
                if self.stop.is_set() or not current.get('enabled') or current.get('paused') or current.get('languages', {}).get(locale) != translation or current.get('destination') != rule['destination']:
                    raise InterruptedError()
        guard()
        self._set(game, locale, state='preparing', attempt=identity, message='Preparing mobile library in local working storage.')
        command = child_command('mobile-export', ['--root', str(self.root), '--game', game,
                   '--output', str(output), '--source-locale', locale, '--translation-locale', translation,
                   '--automatic-install', str(install)])
        from .update_workers import INDEX_BUILD_LOCK, subprocess_options
        while not INDEX_BUILD_LOCK.acquire(timeout=.5):
            guard()
        log = output.parent / 'progress.jsonl'
        try:
            with log.open('w', encoding='utf-8') as stream:
                self.process = subprocess.Popen(command, cwd=discover_layout().resource_root, stdout=stream, stderr=subprocess.DEVNULL,
                    **subprocess_options(), start_new_session=os.name != 'nt')
                offset = 0
                while self.process.poll() is None:
                    guard()
                    with log.open('rb') as updates:
                        updates.seek(offset)
                        for line in updates:
                            try:
                                value = json.loads(line)
                            except ValueError:
                                break
                            if value.get('state') != 'complete':
                                update = {key: value[key] for key in ('state', 'message', 'progress') if key in value}
                                if 'estimatedAudioBytes' in value or 'estimatedCatalogBytes' in value:
                                    update['estimatedBytes'] = value.get('estimatedAudioBytes', 0) + value.get('estimatedCatalogBytes', 0)
                                self._set(game, locale, **update)
                            offset += len(line)
                    self.stop.wait(.5)
                if self.process.returncode:
                    if self.process.returncode == 3:
                        failures = job.get('storageFailures', 0) + 1 if job.get('attempt') == identity else 1
                        self._set(game, locale, storageFailures=failures, state='error' if failures >= 2 else 'waiting',
                                  message='A required file is still unavailable despite passing storage checks. Finish downloads or check the drive, then Retry.' if failures >= 2 else
                                  'Storage or a required local file is unavailable. Reconnect the drive, finish downloads or free space; prerequisites will be checked again.')
                        return
                    if adapter.fingerprint(install) != stamp:
                        self.observed.pop((game, locale), None)
                        self._set(game, locale, state='waiting', message='Game changed during export; waiting for the newest files.')
                    else:
                        self._set(game, locale, state='error', message='Preparation failed. Check voice downloads and tools, then Retry. Verified clips are retained.')
                    return
            result = None
            with log.open(encoding='utf-8') as stream:
                for line in stream:
                    value = json.loads(line)
                    if value.get('state') == 'complete':
                        result = value
            if result is None:
                raise RuntimeError('Export did not produce a completed library.')
            candidate = Path(result['bundle'])
            checked = [0.0]
            def publish_guard(force=False):
                guard()
                if force or time.monotonic() - checked[0] >= 5:
                    if adapter.fingerprint(install) != stamp:
                        raise InterruptedError()
                    checked[0] = time.monotonic()
            publish_guard.force = lambda: publish_guard(True)
            self._set(game, locale, state='publishing', message='Copying verified library to the export folder.', bytes=candidate.stat().st_size)
            publish(candidate, destination, self.home / 'recovery' / key / name, publish_guard)
            instructions = destination.parent / 'Mobile Library - Read me.txt'
            temporary = instructions.with_suffix('.txt.pending')
            temporary.write_text('Open the ZIP in the mobile companion and leave Keep on this device enabled. Libraries reopen automatically. On iPhone, select each updated ZIP once from Files. Cloud synchronization is managed by your cloud application. Do not share game libraries publicly. No credentials are included.\n', encoding='utf-8')
            os.replace(temporary, instructions)
            self._set(game, locale, state='complete', fingerprint=identity, storageFailures=0, message='Updated in export folder', updatedAt=time.time())
            try:
                prune_completed_work(output, game, self.home)
            except (OSError, ValueError, KeyError, zipfile.BadZipFile):
                pass  # Optional tidying cannot invalidate a completed publication.
        except InterruptedError:
            self._set(game, locale, state='waiting', message='Export interrupted; verified work is retained for resuming.')
        finally:
            try:
                if self.process and self.process.poll() is None:
                    stop_export_process(self.process)
            finally:
                if self.process is None or self.process.poll() is not None:
                    self.process = None
                INDEX_BUILD_LOCK.release()
