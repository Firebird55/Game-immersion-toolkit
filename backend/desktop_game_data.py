"""Desktop publication of explicitly downloaded publisher text snapshots.

The shared service owns planning, transfers and immutable source validation.
This host binds a validated text index to the existing desktop capture service;
audio preparation remains unavailable until its original-recording adapter is
installed. A bootstrap stage never activates capture or replaces ready data.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
import threading

from .game_data import GameDataService, _read, _write, _write_bytes
from .game_data_protocol import GAME_TITLES, GameDataError
from .game_data_providers import create_game_data_providers
from .multilingual_index import MultilingualTextIndex


class _TextOnlyVoices:
    ready = False

    def __init__(self, locale, executor):
        self.locale, self._executor = locale, executor

    def has_variant(self, *_args): return False
    def schedule(self, *_args): return False
    def status(self):
        return {'ready': False, 'mapped_lines': 0, 'message': 'Audio omitted by download choice.'}


class DesktopGameData:
    def __init__(self, runtime, data_root, *, providers=None):
        self.runtime, self.root = runtime, Path(data_root)
        self.epoch, self.active = 0, {}
        self.restore_error = None
        self._restore_lock, self._restored_owner = threading.RLock(), None
        platform = {'win32': 'windows', 'darwin': 'macos'}.get(sys.platform, 'linux')
        self.providers = (create_game_data_providers(platform=platform) if providers is None else providers)
        self.service = self._service()

    def _service(self):
        return GameDataService(self.profile_root, self.providers, owner_guard=self.owner,
            on_activate=self._activate)

    def owner(self):
        with self.runtime.accounts.lock:
            status = self.runtime.accounts.status()
            # The generation invalidates A -> B -> A work as well as A -> B.
            return f'{status["active"]}:{self.runtime.accounts.generation}:{self.epoch}'

    def profile_root(self):
        with self.runtime.accounts.lock:
            identity = self.runtime.accounts.status()['active']
            return self.root / hashlib.sha256(identity.encode()).hexdigest()

    def _bind(self, game, index, voices):
        runtime = self.runtime
        # Invalidate in-flight OCR before swapping either reference. Capture's
        # existing epoch checks reject frames spanning this publication.
        runtime.capture._scan_epoch += 1
        if game == 'zzz':
            runtime.textmaps = runtime.capture.textmaps = index
            runtime.voice_assets = runtime.capture.voice_assets = voices
        else:
            runtime.game_indexes[game] = runtime.capture.game_indexes[game] = index
            runtime.game_voice_assets[game] = runtime.capture.game_voice_assets[game] = voices
        runtime.capture._scan_epoch += 1

    def _selections(self):
        value = _read(self.profile_root() / 'selected.json')
        if value is None:
            return {'schema': 'desktop-game-selections-v1', 'games': {}}
        if (not isinstance(value, dict) or set(value) != {'schema', 'games'}
                or value['schema'] != 'desktop-game-selections-v1'
                or not isinstance(value['games'], dict) or set(value['games']) - set(GAME_TITLES)
                or any(item is not None and not isinstance(item, dict) for item in value['games'].values())):
            raise GameDataError('invalid_game_selection', 'Downloaded game selection needs repair. Saved history was kept.')
        return value

    def _activate(self, ctx, source):
        with self.runtime.accounts.lock:
            ctx.check()
            key = (ctx.owner, ctx.game)
            previous = self.active.get(key)
            selections = self._selections()
            if source is None:
                selections['games'][ctx.game] = None
                _write(self.profile_root() / 'selected.json', selections)
                if previous:
                    index, voices = previous
                    empty = MultilingualTextIndex(ctx.game, ctx.directory, autoload=False)
                    self._bind(ctx.game, empty, voices)
                    self.active[key] = (empty, voices)
                return
            if ctx.request.content_mode != 'text':
                raise GameDataError('desktop_original_audio_adapter_unavailable',
                    'Original audio preparation is not available in this desktop build. Previous game data was kept.', 409)
            if ctx.game != 'zzz' and ctx.game not in self.runtime.game_indexes:
                raise GameDataError('desktop_capture_profile_unavailable',
                    'This game’s desktop capture profile is not available yet.', 409)
            index = ctx.index
            if index is None or not index.ready:
                raise GameDataError('invalid_game_snapshot', 'The downloaded text snapshot is not ready.')
            index.publisher_generation = ctx.source_descriptor['revision']
            index.target_locale = ctx.request.target_locales[0] if ctx.request.target_locales else ''
            index.publisher_request_sha256 = hashlib.sha256(json.dumps(ctx.request.json(),
                ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            old_voices = (self.runtime.voice_assets if ctx.game == 'zzz'
                else self.runtime.game_voice_assets[ctx.game])
            voices = _TextOnlyVoices(index.source_locale, old_voices._executor)
            if (ctx.phase == 'restore' and not getattr(ctx, 'explicit_activation', False)
                    and selections['games'].get(ctx.game) != ctx.source_descriptor):
                raise GameDataError('active_game_changed', 'A newer downloaded game selection was kept.', 409)
            pointer = self.profile_root() / 'selected.json'
            previous_bytes = pointer.read_bytes() if pointer.exists() else None
            selections['games'][ctx.game] = ctx.source_descriptor
            _write(pointer, selections)
            try:
                self._bind(ctx.game, index, voices)
                self.active[key] = (index, voices)
            except Exception:
                if previous_bytes is None: pointer.unlink(missing_ok=True)
                else: _write_bytes(pointer, previous_bytes)
                raise

    def restore_selected(self):
        """Restore this profile's exact selections locally, never latest/remote."""
        with self._restore_lock:
            owner = self.owner()
            if owner == self._restored_owner:
                return
            selections = self._selections()
            for game, descriptor in selections['games'].items():
                if descriptor is None:
                    with self.runtime.accounts.lock:
                        if owner != self.owner():
                            raise GameDataError('game_data_owner_changed', 'Account changed. Refresh Settings.', 409)
                        if game != 'zzz' and game not in self.runtime.game_indexes:
                            continue
                        empty = MultilingualTextIndex(game, self.profile_root(), autoload=False)
                        old = self.runtime.voice_assets if game == 'zzz' else self.runtime.game_voice_assets[game]
                        voices = _TextOnlyVoices('', old._executor)
                        self._bind(game, empty, voices)
                        self.active[(owner, game)] = (empty, voices)
                else:
                    self.service.restore(game, expected_owner=owner, source_descriptor=descriptor)
            if owner != self.owner():
                raise GameDataError('game_data_owner_changed', 'Account changed. Refresh Settings.', 409)
            self._restored_owner = owner

    def capture_ready(self, game):
        """None means this profile has not selected a publisher snapshot."""
        try:
            self.restore_selected()
        except (GameDataError, OSError, ValueError, TypeError, KeyError):
            self.restore_error = 'Downloaded game data needs repair. Saved history is still available.'
            return False
        with self.runtime.accounts.lock:
            value = self.active.get((self.owner(), game))
            return bool(value[0].ready) if value is not None else None

    def pause(self):
        # Cancellation and the real pool drain complete before SQL handoff.
        self.service.close()
        self.service.pool.shutdown(wait=True, cancel_futures=True)

    def resume(self):
        if self.service.closed:
            self.epoch += 1
            self.active.clear()
            self.service = self._service()
        try:
            self.restore_selected()
            self.restore_error = None
        except (GameDataError, OSError, ValueError, TypeError, KeyError):
            self.restore_error = 'Downloaded game data needs repair. Saved history is still available.'
