"""Account-bound publisher data plans, staged downloads and validated publication."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, fields, replace
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import threading
import time

from .atomic_files import replace as atomic_replace
from .game_data_protocol import (GAME_TITLES, MAX_METADATA_BYTES, MAX_ASSET_BYTES,
    GameDataError, GameDataRequest, GameDataPlan, SnapshotSource, PreparationStage,
    SourceProof, bounded_text, private_handle)
from .local_game import LocalDialogue
from .multilingual_index import MultilingualTextIndex
from .private_data_paths import MAX_TEXT, MAX_ROWS, _no_links


def _json_bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _write_bytes(path, raw):
    _no_links(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    pending = path.with_name(path.name + '.' + secrets.token_hex(8) + '.pending')
    try:
        with pending.open('xb') as handle:
            handle.write(raw); handle.flush(); os.fsync(handle.fileno())
        atomic_replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def _write(path, value):
    _write_bytes(path, _json_bytes(value))


def _read(path):
    _no_links(path)
    if not path.is_file():
        return None
    if path.stat().st_size > 2 * 1024**2:
        raise GameDataError('invalid_local_state', 'Downloaded game information needs repair.')
    return json.loads(path.read_text(encoding='utf8'))


def _size(root):
    _no_links(root)
    if not root.exists():
        return 0
    total, count, pending = 0, 0, [root]
    while pending:
        directory = pending.pop()
        try: children = list(directory.iterdir())
        except FileNotFoundError: continue
        for item in children:
            try:
                _no_links(item); count += 1
                if count > 1000000:
                    raise GameDataError('cache_file_limit', 'The game cache exceeds its file limit.')
                if item.is_dir(): pending.append(item)
                else: total += item.stat().st_size
            except FileNotFoundError:
                continue
            if total > MAX_ASSET_BYTES:
                raise GameDataError('cache_size_limit', 'The game cache exceeds its size limit.')
    return total


def _remove_owned(path, root):
    _no_links(path); _no_links(root)
    if path.resolve() == root.resolve() or not path.resolve().is_relative_to(root.resolve()):
        raise GameDataError('unsafe_cache_path', 'The game cache path is invalid.')
    _size(path)  # Reject links/reparse points before any recursive operation.
    if path.exists():
        shutil.rmtree(path)


class _Context:
    def __init__(self, service, root, owner, game, request, directory, phase, *, budget=None, job=None):
        self.service, self.root, self.owner, self.game = service, root, owner, game
        self.request, self.directory, self.phase = request, directory, phase
        self.cache_directory = root / game / 'cache'
        self.budget, self.job, self.consumed = budget, job, 0
        self.cancel = threading.Event()
        self.index = None
        self.source_descriptor = None
        self.activation_token = None
        self.activation_required = False
        self.transfer_lock = threading.RLock()
        self.transfers_closed = False
        self.data_epoch = service.epochs.get((root, game), 0)
        self.stage_handle = service._stage_handle(root, game, request) if phase == 'plan' else None

    def cancelled(self):
        try:
            self.check(); return False
        except Exception:
            return True

    def check(self):
        if self.cancel.is_set() or self.service.closed:
            raise GameDataError('preparation_cancelled', 'Game preparation stopped.', 409)
        if self.service._owner() != self.owner:
            self.cancel.set()
            raise GameDataError('game_data_owner_changed', 'The account changed. Retry with the current account.', 409)
        if self.service.epochs.get((self.root, self.game), 0) != self.data_epoch:
            self.cancel.set()
            raise GameDataError('game_data_changed', 'The game data changed. Refresh Settings.', 409)
        if self.activation_required and self.service.activations.get(self.root) != (self.owner, self.activation_token):
            raise GameDataError('active_game_changed', 'A newer game selection was kept.', 409)

    def consume_bytes(self, count, *, kind='asset'):
        with self.transfer_lock:
            self.check()
            if type(count) is not int or count < 0 or kind not in {'metadata', 'asset', 'audio'}:
                raise GameDataError('invalid_transfer_count', 'The game source reported an invalid transfer.')
            if kind == 'audio' and self.request.content_mode != 'text-audio':
                raise GameDataError('audio_not_requested', 'Audio was not requested for this game.')
            if self.transfers_closed or self.phase not in {'plan', 'download'} or self.phase == 'plan' and kind != 'metadata':
                raise GameDataError('unapproved_asset_transfer', 'Check the download size before acquiring game data.')
            maximum = MAX_METADATA_BYTES if self.phase == 'plan' else self.budget
            if maximum is None or self.consumed + count > maximum:
                raise GameDataError('transfer_budget_exceeded', 'The game source exceeded the approved download size.')
            self.consumed += count

    def remaining_bytes(self, *, kind='asset'):
        with self.transfer_lock:
            self.consume_bytes(0, kind=kind)
            return (MAX_METADATA_BYTES if self.phase == 'plan' else self.budget) - self.consumed

    def progress(self, phase, downloaded_bytes, total_bytes, message=''):
        self.check()
        if (not bounded_text(phase, 64) or not bounded_text(message, 1000, empty=True)
                or type(downloaded_bytes) is not int or not 0 <= downloaded_bytes <= self.consumed
                or total_bytes is not None and (type(total_bytes) is not int or not downloaded_bytes <= total_bytes <= (self.budget if self.budget is not None else MAX_METADATA_BYTES))):
            raise GameDataError('invalid_download_progress', 'The game source reported invalid progress.')
        if self.job:
            with self.service.lock:
                self.job.update(phase=phase, downloaded_bytes=downloaded_bytes, total_bytes=total_bytes, message=message)


class GameDataService:
    def __init__(self, root, providers, owner_guard=lambda: 'local', *, on_activate=None,
            retained_bytes=lambda _game: 0, clock=time.monotonic):
        if set(providers) - set(GAME_TITLES):
            raise ValueError('Unsupported publisher provider')
        self.root_getter = root if callable(root) else lambda: root
        self.providers, self.owner_guard = dict(providers), owner_guard
        self.on_activate, self.retained_bytes, self.clock = on_activate, retained_bytes, clock
        self.lock = threading.RLock()
        self.plans, self.jobs, self.errors, self.epochs, self.activations = {}, {}, {}, {}, {}
        self.closed = False
        self.pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='toolkit-game-data')

    def _owner(self):
        value = self.owner_guard()
        if type(value) not in {str, int}:
            raise GameDataError('invalid_data_owner', 'The current account is unavailable.', 409)
        return value

    def _scope(self, expected_owner=None):
        if self.closed:
            raise GameDataError('game_data_closed', 'Game data preparation has stopped.', 503)
        before = self._owner()
        if expected_owner is not None and expected_owner != before:
            raise GameDataError('game_data_owner_changed', 'The account changed. Refresh Settings.', 409)
        root = Path(self.root_getter()).absolute()
        if before != self._owner():
            raise GameDataError('game_data_owner_changed', 'The account changed. Retry with the current account.', 409)
        _no_links(root); root.mkdir(parents=True, exist_ok=True)
        return root, before

    def _provider(self, game):
        if game not in GAME_TITLES:
            raise GameDataError('unsupported_game', 'Choose a supported live-service game.', 404)
        if game not in self.providers:
            raise GameDataError('game_runtime_unavailable', 'This game’s original-data reader is unavailable on this device.', 409)
        return self.providers[game]

    def _metadata(self, root, game):
        value = _read(root / game / 'current.json')
        if value is None:
            return None
        return self._validate_metadata(value, game)

    def _stage(self, root, game):
        value = _read(root / game / 'stage.json')
        if value is None:
            return None
        result = self._validate_metadata(value, game)
        if result['ready']:
            raise GameDataError('invalid_local_state', 'Downloaded game information needs repair.')
        return result

    def _stage_handle(self, root, game, request):
        stage = self._stage(root, game)
        return private_handle(stage['handle']) if stage and stage['request'] == request.json() else None

    def _validate_metadata(self, value, game):
        if (not isinstance(value, dict) or value.get('schema') != 'game-data-source-v1' or value.get('game') != game
                or not isinstance(value.get('directory'), str) or len(value['directory']) != 64
                or any(char not in '0123456789abcdef' for char in value['directory'])):
            raise GameDataError('invalid_local_state', 'Downloaded game information needs repair.')
        if (type(value.get('ready')) is not bool or not bounded_text(value.get('revision'), 256)
                or not bounded_text(value.get('message'), 1000, empty=True)):
            raise GameDataError('invalid_local_state', 'Downloaded game information needs repair.')
        GameDataRequest.parse(value['request'])
        private_handle(value['handle'])
        if value.get('ready'):
            SourceProof(**value['source_proof'])
            if (not isinstance(value.get('snapshot_sha256'), str) or len(value['snapshot_sha256']) != 64
                    or any(char not in '0123456789abcdef' for char in value['snapshot_sha256'])):
                raise GameDataError('invalid_local_state', 'Downloaded game information needs repair.')
        return value

    def _row(self, root, owner, game):
        metadata_error = None
        try: current = self._metadata(root, game)
        except (GameDataError, ValueError, TypeError, KeyError, OSError):
            current = None
            metadata_error = 'Downloaded game information needs repair. Delete and download this game again; saved history stays.'
        try: stage = self._stage(root, game)
        except (GameDataError, ValueError, TypeError, KeyError, OSError):
            stage = None
            metadata_error = 'An unfinished download needs repair. Existing game data and saved history stay.'
        candidates = [item for item in self.plans.values() if item['root'] == root and item['owner'] == owner
                      and item['game'] == game and item['expires'] > self.clock()]
        latest = candidates[-1] if candidates else None
        plan = latest['plan'] if latest else None
        request = (latest['request'] if latest else GameDataRequest.parse(current['request']) if current else
            GameDataRequest.parse(stage['request']) if stage else GameDataRequest('global', 'en'))
        job = self.jobs.get((root, game))
        if job and job['context'].owner != owner:
            job['context'].cancel.set(); job = None
        public_job = ({key: job[key] for key in ('id', 'status', 'phase', 'downloaded_bytes', 'total_bytes', 'message')} if job else None)
        ready = bool(current and current['ready'])
        state = 'ready' if ready else 'not_downloaded'
        if game not in self.providers:
            state = 'unsupported'
        if plan and ready and plan.revision != current['revision']:
            state = 'update_available'
        active = job and job['status'] in {'queued', 'running'}
        if active:
            state = 'downloading'
        failure = self.errors.get((root, owner, game)) or metadata_error
        if failure and not active:
            state = 'error'
        retained = self.retained_bytes(game)
        if type(retained) is not int or not 0 <= retained <= 2**53 - 1:
            raise GameDataError('invalid_retained_size', 'Saved recording sizes are unavailable.')
        installed = _size(root / game / 'cache')
        can_download = bool(plan and plan.runtime_available and plan.download_bytes is not None
                            and plan.required_disk_bytes is not None and not active and not latest['used'])
        return {'id': game, 'title': GAME_TITLES[game], 'state': state,
            'revision': plan.revision if plan else current['revision'] if current else stage['revision'] if stage else None,
            'installed_revision': current['revision'] if ready else None,
            'can_activate': ready and game in self.providers,
            **request.json(), 'installed_bytes': installed, 'deletable_bytes': installed, 'retained_bytes': retained,
            'download_bytes': plan.download_bytes if plan else None,
            'download_is_upper_bound': plan.download_is_upper_bound if plan else False,
            'required_disk_bytes': plan.required_disk_bytes if plan else None,
            'plan_id': latest['id'] if latest else None, 'job': public_job,
            'can_plan': game in self.providers and not active, 'can_download': can_download,
            'can_delete': installed > 0 and not active,
            'message': failure or (public_job['message'] if public_job else plan.message if plan else
                stage['message'] if stage else 'Original game data ready.' if ready else current.get('message', '') if current else
                'Check the download size to begin.' if game in self.providers else
                'This game’s original-data reader is unavailable on this device.')}

    def snapshot(self, *, expected_owner=None):
        root, owner = self._scope(expected_owner)
        with self.lock:
            result = {'schema': 'game-data-v1', 'games': [self._row(root, owner, game) for game in GAME_TITLES]}
            if owner != self._owner():
                raise GameDataError('game_data_owner_changed', 'The account changed. Refresh Settings.', 409)
            return result

    def plan(self, game, request, *, expected_owner=None):
        provider, selection = self._provider(game), GameDataRequest.parse(request)
        root, owner = self._scope(expected_owner)
        with self.lock:
            running = self.jobs.get((root, game))
            if running and running['status'] in {'queued', 'running'} and running['context'].owner == owner:
                raise GameDataError('download_active', 'Wait for the current game download to finish.', 409)
        identity = secrets.token_hex(16)
        directory = root / game / 'cache' / '.planning' / identity
        _no_links(directory); directory.mkdir(parents=True)
        ctx = _Context(self, root, owner, game, selection, directory, 'plan')
        try:
            plan = provider.plan(selection, ctx); ctx.check()
            with ctx.transfer_lock: ctx.transfers_closed = True
            if not isinstance(plan, GameDataPlan):
                raise GameDataError('invalid_download_plan', 'The game reader did not provide a bounded download plan.')
            with self.lock:
                ctx.check()
                for key, item in list(self.plans.items()):
                    if item['expires'] <= self.clock():
                        if not item['used']:
                            _remove_owned(item['directory'], item['root'])
                        self.plans.pop(key)
                if len(self.plans) >= 128:
                    raise GameDataError('plan_limit', 'Too many download estimates are open. Retry later.', 409)
                self.plans[identity] = {'id': identity, 'root': root, 'owner': owner, 'game': game, 'request': selection,
                    'plan': plan, 'expires': self.clock() + 900, 'used': False, 'directory': directory}
                self.errors.pop((root, owner, game), None)
                return {'game': self._row(root, owner, game)}
        except Exception:
            ctx.cancel.set()
            with ctx.transfer_lock: ctx.transfers_closed = True
            _remove_owned(directory, root); raise

    def download(self, game, request, *, expected_owner=None):
        provider = self._provider(game)
        root, owner = self._scope(expected_owner)
        if not isinstance(request, dict) or set(request) != {'plan_id', 'revision'}:
            raise GameDataError('download_plan_required', 'Check the download size before downloading.', 409)
        with self.lock:
            item = self.plans.get(request['plan_id']) if isinstance(request['plan_id'], str) else None
            if (not item or item['root'] != root or item['owner'] != owner or item['game'] != game
                    or item['expires'] <= self.clock() or request['revision'] != item['plan'].revision):
                raise GameDataError('download_plan_changed', 'The download estimate changed. Check its size again.', 409)
            if item['used']:
                previous = self.jobs.get((root, game))
                if previous and previous.get('plan_id') == item['id'] and previous['status'] in {'queued', 'running', 'complete'}:
                    return {'game': self._row(root, owner, game)}
                raise GameDataError('download_plan_used', 'Check the download size again before retrying.', 409)
            if not self._row(root, owner, game)['can_download']:
                raise GameDataError('download_not_available', 'A bounded download plan and a working game reader are required.', 409)
            device = root.stat().st_dev
            reserved = sum(job['reserved'] for job in self.jobs.values() if job['device'] == device and job['status'] in {'queued', 'running'})
            if shutil.disk_usage(root).free < item['plan'].required_disk_bytes + reserved:
                raise GameDataError('insufficient_storage', 'Free more storage before downloading this game.', 507)
            directory = root / game / 'cache' / '.staging' / secrets.token_hex(16)
            _no_links(directory); directory.mkdir(parents=True)
            ctx = _Context(self, root, owner, game, item['request'], directory, 'download', budget=item['plan'].download_bytes)
            ctx.activation_token = secrets.token_hex(16)
            self.activations[root] = (owner, ctx.activation_token)
            job = {'id': secrets.token_hex(16), 'plan_id': item['id'], 'status': 'queued', 'phase': item['plan'].stage,
                'downloaded_bytes': 0, 'total_bytes': item['plan'].download_bytes, 'message': 'Preparing original game data.',
                'context': ctx, 'reserved': item['plan'].required_disk_bytes, 'device': device}
            ctx.job = job; item['used'] = True
            ctx.check()
            self.jobs[(root, game)] = job
            self.pool.submit(self._prepare, provider, item, job)
            return {'game': self._row(root, owner, game)}

    def _validate_source(self, source, ctx):
        if not isinstance(source, SnapshotSource):
            raise GameDataError('incomplete_game_source', 'The original game data is not ready yet.')
        path = source.snapshot_path.absolute()
        _no_links(path)
        if not path.resolve().is_relative_to(ctx.directory.resolve()) or not path.is_file() or not 0 < path.stat().st_size <= MAX_TEXT:
            raise GameDataError('invalid_game_snapshot', 'The game reader did not produce a valid original snapshot.')
        ctx.check()
        index = MultilingualTextIndex(ctx.game, path.parent, autoload=False); index.path = path
        if not index.load() or not index.ready or not 0 < index.entry_count <= MAX_ROWS or index.source_locale != ctx.request.source_locale:
            raise GameDataError('invalid_game_snapshot', 'The original game snapshot could not be validated.')
        if index.snapshot_metadata.get('content_mode') != ctx.request.content_mode:
            raise GameDataError('game_content_mode_changed', 'The prepared game data does not match the selected download mode.')
        allowed = {item.name for item in fields(LocalDialogue)}
        for row in index._records:
            if set(row) - allowed:
                raise GameDataError('unsupported_game_snapshot', 'The game reader produced unsupported dialogue fields.')
            if ctx.request.content_mode == 'text' and row.get('audio'):
                raise GameDataError('unexpected_audio_preparation', 'Text-only preparation must not include playable audio.')
            if ctx.request.content_mode == 'text-audio' and row.get('audio_omitted_by_request'):
                raise GameDataError('incomplete_audio_preparation', 'The requested original audio has not been prepared.')
        if ctx.request.content_mode == 'text-audio' and index.audio_count and (source.voice_source is None or not callable(getattr(source.voice_source, 'has', None))
                or not callable(getattr(source.voice_source, 'resolve', None))):
            raise GameDataError('original_voice_unavailable', 'This device cannot retrieve the original voices yet.')
        if ctx.request.content_mode == 'text-audio':
            for row in index._records:
                if row.get('audio') and source.voice_source.has(row) is not True:
                    raise GameDataError('original_audio_incomplete', 'The requested original audio has not finished downloading.')
        ctx.check(); ctx.index = index
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        return digest

    def _prepare(self, provider, item, job):
        ctx = job['context']; metadata = None; owns_output = True
        try:
            with self.lock: job['status'] = 'running'
            ctx.check(); result = provider.download(item['plan'], ctx); ctx.check()
            with ctx.transfer_lock: ctx.transfers_closed = True
            if not isinstance(result, (SnapshotSource, PreparationStage)):
                raise GameDataError('incomplete_game_source', 'The original game data is not ready yet.')
            digest = self._validate_source(result, ctx) if isinstance(result, SnapshotSource) else None
            identity = hashlib.sha256(_json_bytes({'revision': item['plan'].revision,
                'request': ctx.request.json(), 'handle': result.restore_handle, 'snapshot': digest})).hexdigest()
            final = ctx.cache_directory / 'sources' / identity
            _no_links(final); final.parent.mkdir(parents=True, exist_ok=True)
            ctx.check()
            if final.exists():
                _remove_owned(ctx.directory, ctx.root); owns_output = False
            else:
                atomic_replace(ctx.directory, final)
            ctx.directory = final
            _remove_owned(item['directory'], ctx.root)
            metadata = {'schema': 'game-data-source-v1', 'game': ctx.game, 'revision': item['plan'].revision,
                'request': ctx.request.json(), 'directory': identity, 'handle': result.restore_handle,
                'ready': isinstance(result, SnapshotSource), 'snapshot_sha256': digest,
                'source_proof': asdict(result.source_proof) if isinstance(result, SnapshotSource) else None,
                'message': result.message if isinstance(result, PreparationStage) else 'Original game data ready.'}
            if metadata['ready']:
                restore = _Context(self, ctx.root, ctx.owner, ctx.game, ctx.request, final, 'restore', budget=0)
                result = provider.restore(result.restore_handle, restore)
                if (self._validate_source(result, restore) != digest or asdict(result.source_proof) != metadata['source_proof']
                        or result.restore_handle != metadata['handle']):
                    raise GameDataError('source_restore_mismatch', 'The game source could not be restored locally.')
                ctx.index = restore.index
            ctx.source_descriptor = metadata
            # A bootstrap/archive stage is not a ready source. Keep the last
            # working pointer through every subsequent estimate/failure/restart.
            pointer = ctx.root / ctx.game / ('current.json' if metadata['ready'] else 'stage.json')
            stage_to_remove = None
            if metadata['ready']:
                try: stage = self._stage(ctx.root, ctx.game)
                except (OSError, ValueError, TypeError, KeyError, GameDataError): stage = None
                if stage and stage['revision'] == metadata['revision'] and stage['request'] == metadata['request']:
                    stage_to_remove = ctx.root / ctx.game / 'stage.json'
            with self.lock:
                ctx.check(); _no_links(pointer)
                previous = pointer.read_bytes() if pointer.exists() else None
                if previous is not None and len(previous) > 2 * 1024**2:
                    raise GameDataError('invalid_local_state', 'Downloaded game information needs repair.')
                _write(pointer, metadata)
                try:
                    if (metadata['ready'] and self.on_activate
                            and self.activations.get(ctx.root) == (ctx.owner, ctx.activation_token)):
                        # The maintained callback checks and activates under
                        # the owner's lock. Its return is the commit point:
                        # an account switch AFTER that point must not delete
                        # the just-committed source from the old profile.
                        self.on_activate(ctx, result)
                    else:
                        ctx.check()
                except Exception:
                    if previous is None: pointer.unlink(missing_ok=True)
                    else: _write_bytes(pointer, previous)
                    raise
                self.errors.pop((ctx.root, ctx.owner, ctx.game), None)
                if stage_to_remove:
                    try: stage_to_remove.unlink(missing_ok=True)
                    except OSError: pass  # Housekeeping cannot undo a committed source.
                job.update(status='complete' if metadata['ready'] else 'needs_plan', phase='ready' if metadata['ready'] else 'estimate',
                    downloaded_bytes=ctx.consumed, message=metadata['message'])
                ctx.index = None
        except Exception as error:
            ctx.cancel.set()
            with ctx.transfer_lock: ctx.transfers_closed = True
            with self.lock:
                message = error.message if isinstance(error, GameDataError) else 'Game preparation failed. Previous game data was kept.'
                self.errors[(ctx.root, ctx.owner, ctx.game)] = message
                job.update(status='failed', message=message)
                ctx.index = None
            # Only this job's owned unpublished output is removed. A successfully
            # published previous generation, history and recordings stay intact.
            if owns_output and (metadata is None or job['status'] != 'complete'):
                try: _remove_owned(ctx.directory, ctx.root)
                except (OSError, ValueError, GameDataError): pass

    def activate(self, game, request, *, expected_owner=None):
        """Explicitly select an already downloaded revision, without transfers."""
        self._provider(game)
        root, owner = self._scope(expected_owner)
        with self.lock:
            metadata = self._metadata(root, game)
            if (not isinstance(request, dict) or set(request) != {'revision'} or not metadata
                    or not metadata['ready'] or request['revision'] != metadata['revision']):
                raise GameDataError('installed_game_changed', 'The downloaded game changed. Refresh Settings.', 409)
            token = secrets.token_hex(16)
            self.activations[root] = (owner, token)
        self.restore(game, expected_owner=owner, _metadata=metadata, _activation_token=token)
        with self.lock:
            if self._owner() != owner or self.activations.get(root) != (owner, token):
                raise GameDataError('active_game_changed', 'A newer game selection was kept.', 409)
            return {'game': self._row(root, owner, game)}

    def restore(self, game, *, expected_owner=None, source_descriptor=None, _metadata=None, _activation_token=None):
        provider = self._provider(game)
        root, owner = self._scope(expected_owner)
        metadata = (self._validate_metadata(private_handle(source_descriptor), game)
            if source_descriptor is not None else self._metadata(root, game))
        if expected_owner is not None and expected_owner != owner:
            raise GameDataError('game_data_owner_changed', 'The account changed. Refresh Settings.', 409)
        if not metadata or not metadata['ready']:
            return None
        if _metadata is not None and metadata != _metadata:
            raise GameDataError('installed_game_changed', 'The downloaded game changed. Refresh Settings.', 409)
        ctx = _Context(self, root, owner, game, GameDataRequest.parse(metadata['request']),
            root / game / 'cache' / 'sources' / metadata['directory'], 'restore', budget=0)
        ctx.source_descriptor = metadata
        with self.lock:
            existing = self.activations.get(root)
            if _activation_token is not None:
                ctx.activation_token = _activation_token
            else:
                if existing is None or existing[0] != owner:
                    existing = (owner, secrets.token_hex(16)); self.activations[root] = existing
                ctx.activation_token = existing[1]
            ctx.activation_required = True
            ctx.explicit_activation = _activation_token is not None
        ctx.check(); source = provider.restore(metadata['handle'], ctx)
        if (self._validate_source(source, ctx) != metadata['snapshot_sha256']
                or asdict(source.source_proof) != metadata['source_proof'] or source.restore_handle != metadata['handle']):
            raise GameDataError('source_restore_mismatch', 'Downloaded game data needs repair. Existing history is kept.')
        with self.lock:
            ctx.check()
            if source_descriptor is None and metadata != self._metadata(root, game):
                raise GameDataError('installed_game_changed', 'The downloaded game changed. Refresh Settings.', 409)
            if self.on_activate:
                self.on_activate(ctx, source)
            else:
                ctx.check()
        ctx.index = None
        return source

    def original_voice_source(self, descriptor, *, expected_owner):
        """Reopen one previously validated source, without compiling its full index.

        The descriptor is read only from the app's hashed transcript reference
        store, never accepted from an HTTP caller or imported browser history.
        Missing managed data does not make an original line unvoiced.
        """
        if not isinstance(descriptor, dict) or descriptor.get('game') not in GAME_TITLES:
            raise GameDataError('invalid_original_reference', 'The original recording reference is unavailable.')
        game = descriptor['game']; metadata = self._validate_metadata(descriptor, game)
        if metadata['request']['content_mode'] != 'text-audio':
            raise GameDataError('audio_not_requested', 'Select Text + audio in Settings to download original recordings.', 409)
        root, owner = self._scope()
        if owner != expected_owner or not metadata['ready']:
            raise GameDataError('game_data_owner_changed', 'The account changed before the recording could be opened.', 409)
        # An older explicitly downloaded original may still be needed to retain
        # a saved line after choosing text-only. This restore context forbids
        # every network byte; it cannot acquire an omitted or absent voice.
        directory = root / game / 'cache' / 'sources' / metadata['directory']
        if not directory.is_dir():
            raise GameDataError('original_source_not_downloaded', 'Download this game’s data to retrieve this original recording.', 409)
        ctx = _Context(self, root, owner, game, GameDataRequest.parse(metadata['request']), directory, 'restore', budget=0)
        ctx.source_descriptor = metadata; ctx.check()
        source = self._provider(game).restore(metadata['handle'], ctx)
        path = source.snapshot_path.absolute(); _no_links(path)
        if (not path.resolve().is_relative_to(directory.resolve()) or not path.is_file()
                or source.restore_handle != metadata['handle'] or asdict(source.source_proof) != metadata['source_proof']):
            raise GameDataError('invalid_original_source', 'The original recording source needs repair.')
        with path.open('rb') as handle:
            digest = hashlib.file_digest(handle, 'sha256').hexdigest()
        if digest != metadata['snapshot_sha256'] or source.voice_source is None:
            raise GameDataError('invalid_original_source', 'The original recording source needs repair.')
        ctx.check()
        return source.voice_source

    def delete(self, game, request, *, expected_owner=None):
        if game not in GAME_TITLES:
            raise GameDataError('unsupported_game', 'Choose a supported live-service game.', 404)
        root, owner = self._scope(expected_owner)
        with self.lock:
            row = self._row(root, owner, game)
            if not isinstance(request, dict) or set(request) != {'revision'} or request['revision'] != row['revision']:
                raise GameDataError('game_data_changed', 'The game data changed. Refresh Settings before deleting it.', 409)
            if row['state'] == 'downloading':
                raise GameDataError('download_active', 'Wait for the game download to finish before deleting it.', 409)
            self.epochs[(root, game)] = self.epochs.get((root, game), 0) + 1
            ctx = _Context(self, root, owner, game, GameDataRequest.parse({key: row[key] for key in ('region', 'source_locale', 'target_locales', 'content_mode')}),
                root / game, 'delete')
            ctx.check()
            if self.on_activate:
                self.on_activate(ctx, None)
            ctx.check(); freed = _size(root / game / 'cache')
            _remove_owned(root / game, root)
            self.plans = {key: value for key, value in self.plans.items() if value['root'] != root or value['game'] != game}
            self.jobs.pop((root, game), None); self.errors.pop((root, owner, game), None)
            return {'game': self._row(root, owner, game), 'freed_bytes': freed}

    def close(self):
        with self.lock:
            self.closed = True
            for job in self.jobs.values(): job['context'].cancel.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
