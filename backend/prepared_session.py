"""Shared production matching/confirmation/history with host-provided OCR frames."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager, nullcontext
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import math
from pathlib import Path
import secrets
import threading
import time

from .capture_confirmation import StableMatchTracker, capture_match_eligible, capture_confirmation_frames
from .floating_caption_policy import floating_caption_policy, observe_floating_contexts, positioned_training_matches
from .config import SettingsStore
from .endfield_caption_context import EndfieldCaptionContext
from .nte_dialogue_context import NteDialogueContext
from .caption_layout import NativeNteCaption, is_cinematic_fragment
from .languages import study_language
from .models import AppSettings, CaptureSnapshot, is_comic_text_id
from .native_frame_admission import NativeFrameReceipt
from .zzz_cinema_context import CinemaContext, ProxyEvidence, proxy_source_scope
from .multilingual_index import MultilingualTextIndex
from .prepared_library import CLIP, SHA, MAX_AUDIO, PreparedLibraryStore, _no_links
from .storage import TranscriptStore
from .source_recordings import OriginalRecordings
from .game_data_protocol import GameDataError, GameDataRequest, bounded_text, private_handle


class PreparedCaptureSession:
    def __init__(self, root, *, on_invalidate=lambda: None):
        self.root = Path(root).absolute()
        _no_links(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.on_invalidate = on_invalidate
        self.settings = SettingsStore(self.root / 'settings.json')
        self.history = TranscriptStore(self.root / 'transcript.db')
        self.libraries = PreparedLibraryStore(self.root / 'libraries')
        self.recordings = OriginalRecordings(self.root / 'original-recordings')
        self.recording_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix='toolkit-original')
        self.recording_jobs = set()
        self.recording_errors = set()
        self.direct_descriptor = self.direct_voice = self.original_source_for = None
        self.source_transition = False
        self.runtime_id = secrets.token_hex(16)
        self.state_version = self.generation = 0
        self.session_id = secrets.token_hex(16)
        self.running = False
        self.last_frame = -1
        self.processed_channels = set()
        self._visible_comics = ()
        self.last_time = None
        self.trackers = {}
        self._independent_exact = set()
        self._continuation_checks = set()
        self._admission_key = None
        self.contexts = {}
        self.floating_contexts = {}
        self.nte_context = NteDialogueContext()
        self.zzz_cinema = CinemaContext()
        self.zzz_proxy = ProxyEvidence()
        self.index = self.directory = None
        self.records_by_id = {}
        self.context_kinds = set()
        self.last_ocr = ''
        self.message = 'Download game data in Settings to begin'
        self._activate_current()

    def _activate_current(self):
        active = self.root / 'active-game-data.json'
        _no_links(active)
        if active.exists():
            # A managed source (including an explicitly deleted one) takes
            # precedence over an older backup ZIP. The host restores it offline.
            return
        directory = self.libraries.current()
        if directory is None:
            return
        payload = json.loads((directory / 'textmap.json').read_text(encoding='utf8'))
        game = payload['game']
        del payload
        index = MultilingualTextIndex(game, directory)
        if not index.ready:
            raise ValueError('The shared matcher could not open this library')
        self._activate_prepared(directory, index)

    def _activate_prepared(self, directory, index):
        self.direct_descriptor = self.direct_voice = self.original_source_for = None
        self.directory, self.index = directory, index
        self.records_by_id = {}
        for row in index._records:
            self.records_by_id.setdefault(row['text_id'], []).append(row)
        self.context_kinds = {row.get('dialogue_kind') for row in index._records if row.get('previous_text_id')}
        self._apply_settings()
        self.message = 'Prepared library ready; start a supported screen source'

    def activate_source(self, directory, index, descriptor, voice, source_for):
        """Activate the service-validated production index, without ZIP conversion."""
        descriptor = private_handle(descriptor)
        request = GameDataRequest.parse(descriptor.get('request'))
        if (not index.ready or descriptor.get('game') != index.game or not descriptor.get('ready')
                or request.source_locale != index.source_locale or not bounded_text(descriptor.get('revision'), 256)):
            raise ValueError('A validated original game snapshot is required')
        with self.lock:
            self.stop('Game data changed; start the screen source again')
            previous = (self.directory, self.index, self.records_by_id, self.context_kinds,
                self.direct_descriptor, self.direct_voice, self.original_source_for)
            try:
                index.publisher_generation = descriptor['revision']
                index.publisher_request_sha256 = hashlib.sha256(json.dumps(request.json(), sort_keys=True,
                    separators=(',', ':'), ensure_ascii=False, allow_nan=False).encode()).hexdigest()
                index.target_locale = request.target_locales[0] if request.target_locales else ''
                self._activate_prepared(Path(directory), index)
            except Exception:
                (self.directory, self.index, self.records_by_id, self.context_kinds,
                    self.direct_descriptor, self.direct_voice, self.original_source_for) = previous
                raise
            self.direct_descriptor, self.direct_voice = descriptor, voice
            self.original_source_for = source_for
            self.message = 'Original game data ready; paste the screen link to begin'
            self.state_version += 1

    def preserve_game_recordings(self, game, source_for, *, cancelled):
        """Keep referenced originals before deleting the managed source cache.

        Callers first stop capture and revoke old work. All local decoding here
        runs outside the matching lock; failure refuses deletion, keeping data.
        """
        for identity in self.recordings.lines(game):
            if cancelled():
                raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
            if self._recording_line(identity) is None:
                continue
            path = self.recordings.materialize(identity, source_for, cancelled=cancelled)
            with self.lock:
                if cancelled():
                    raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
                if path and self._recording_line(identity):
                    self.history.update_audio(identity, 'official-retained/' + path.name, True)

    def deactivate_source(self, game):
        with self.lock:
            if self.index and self.index.game == game:
                self.stop('Game data deleted; saved history and recordings were kept')
                self.directory = self.index = None
                self.direct_descriptor = self.direct_voice = self.original_source_for = None
                self.records_by_id.clear(); self.context_kinds.clear()

    def _source_row(self, match):
        rows = [row for row in self.records_by_id.get(match.text_id, ())
                if row.get('source_text') == match.source_text and row.get('audio_locale') == match.audio_locale
                and row.get('voice_status') == match.voice_status]
        if not rows and self.index.game == 'zzz' and self.index._zzz_cinema_occurrences:
            row = self.index._zzz_cinema_occurrences['rows'].get(match.text_id)
            if row and all(getattr(match, key) == value for key, value in self.index._publisher_context(row).items()):
                return row
        if self.index.game != 'zzz' or len(rows) > 1:
            rows = [row for row in rows if not row.get('player_voice') or row['player_voice'] == self.index.player_voice]
        return rows[0] if len(rows) == 1 else None

    def _has_original(self, match):
        if self.direct_descriptor is None:
            return self._clip(match) is not None
        row = self._source_row(match)
        return bool(row and self.direct_voice and self.direct_voice.has(row) is True)

    def _queue_original(self, identity):
        if self.original_source_for is None or len(self.recording_jobs) >= 128:
            return
        if self._recording_line(identity) is None:
            return
        saved = self.recordings.reference(identity)
        if saved is None:
            return
        reference, _ = saved
        generation, source_for = self.generation, self.original_source_for
        key = (identity, reference, generation)
        if key in self.recording_jobs:
            return
        self.recording_jobs.add(key)
        self.recording_errors.discard(identity)
        def cancelled():
            with self.lock:
                return generation != self.generation or source_for is not self.original_source_for
        def work():
            try:
                path = self.recordings.materialize(identity, source_for, cancelled=cancelled)
                with self.lock:
                    if (not cancelled() and path and self._recording_line(identity)
                            and self.recordings.reference(identity)[0] == reference):
                        self.history.update_audio(identity, 'official-retained/' + path.name, True)
                        self.state_version += 1
            except Exception as error:
                with self.lock:
                    if not cancelled() and not (isinstance(error, GameDataError) and error.code == 'recording_busy'):
                        if len(self.recording_errors) >= 128:
                            self.recording_errors.clear()
                        self.recording_errors.add(identity)
                        self.state_version += 1
            finally:
                with self.lock:
                    self.recording_jobs.discard(key)
        self.recording_pool.submit(work)

    def _apply_settings(self):
        if self.index is None:
            return
        settings = self.settings.get()
        self.index.capture_unvoiced = settings.capture_unvoiced
        self.index.capture_missing_audio = settings.capture_missing_audio
        key = {'zzz': 'zzz_proxy_voice', 'wuwa': 'wuwa_rover_voice'}.get(self.index.game,
                self.index.game + '_player_voice')
        self.index.player_voice = getattr(settings, key, 'unconfigured')

    def stop(self, message='Capture stopped'):
        with self.lock:
            self.running = False
            self.generation += 1
            self.on_invalidate()
            self.last_frame, self.last_time = -1, None
            self.processed_channels.clear()
            self._visible_comics = ()
            self.trackers.clear(); self.contexts.clear(); self.floating_contexts.clear()
            self.nte_context.reset()
            self.zzz_cinema.reset()
            self.zzz_proxy.prepare(None, None)
            self._independent_exact.clear();self._continuation_checks.clear();self._admission_key = None
            self.message = message
            self.state_version += 1

    def start(self):
        with self.lock:
            if self.source_transition:
                raise GameDataError('game_data_busy', 'Wait for game data maintenance to finish.', 409)
            if self.index is None:
                raise ValueError('Download game data in Settings before starting capture')
            self.stop()
            self.running = True
            self.message = 'Waiting for fresh screen frames'
            if self.direct_descriptor:
                for identity in self.recordings.lines(self.index.game):
                    if len(self.recording_jobs) >= 128:
                        break
                    line = self.history.get(identity)
                    if line and not line.has_audio:
                        self._queue_original(identity)
            return self.generation

    def import_library(self, path, *, cancelled=lambda: False, publish_guard=nullcontext):
        @contextmanager
        def activation_scope():
            with self.lock:
                with publish_guard() as mark_committed:
                    yield mark_committed
        def activate(directory, index):
            self.stop('Library changed; start the screen source again')
            self._activate_prepared(directory, index)
            self.state_version += 1
        # Lengthy I/O/validation never blocks pause, cancellation or old-library
        # capture. Only the final validated generation activates under the lock.
        self.libraries.import_archive(path, cancelled=cancelled, publish_guard=activation_scope, activate=activate)
        with self.lock:
            return {'message': self.message, 'game': self.index.game, 'source_locale': self.index.source_locale}

    def update_settings(self, patch):
        with self.lock:
            current = self.settings.get().model_dump()
            if not isinstance(patch, dict) or set(patch) - set(current):
                raise ValueError('Unsupported shared reader setting')
            current.update(patch)
            settings = self.settings.save(AppSettings.model_validate(current))
            self.stop('Settings changed; start the screen source again')
            self._apply_settings()
            return settings.model_dump(mode='json')

    def _clip(self, match):
        rows = [row for row in self.records_by_id.get(match.text_id, ())
                if row.get('source_text') == match.source_text and row.get('audio_locale') == match.audio_locale
                and row.get('voice_status') == match.voice_status]
        if self.index.game != 'zzz' or len(rows) > 1:
            rows = [row for row in rows if not row.get('player_voice') or row['player_voice'] == self.index.player_voice]
        names = {row['audio'].get('prepared_clip') for row in rows if row.get('audio')}
        if len(names) != 1:
            return None
        name = next(iter(names))
        if not isinstance(name, str) or not CLIP.fullmatch(name):
            return None
        path = self.directory / name
        _no_links(path)
        return path if path.is_file() and path.stat().st_size <= MAX_AUDIO else None

    @staticmethod
    def _recording_stamp(line):
        # SQLite can upgrade a recent caption in place. A local integer id is
        # insufficient voice identity; favorites/audio progress are mutable.
        value = line.model_dump(mode='json', exclude={'favorite', 'has_audio', 'voiced', 'audio_source', 'audio_pending'})
        # These optional fields were absent from older retained-reference
        # stamps. Only None is absence-equivalent; every real value is bound.
        for key in ('publisher_generation', 'publisher_request_sha256', 'publisher_occurrence_sha256'):
            if value.get(key) is None:
                value.pop(key, None)
        return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
            ensure_ascii=False, allow_nan=False).encode()).hexdigest()

    def _recording_line(self, identity):
        line = self.history.get(identity)
        return line if line and self.recordings.matches(identity, self._recording_stamp(line)) else None

    def observe(self, generation, sequence, groups, *, channel='dialogue', now=None, dialogue_menu=False,
            nte_layout=None, presentation_lines=None, frame_size=None, admission=None,
            zzz_captions=None, zzz_dialogue=None):
        """Admit fresh host OCR only; late/replayed/rotated-source results lose scope.

        The host owns frame acquisition, calibration and OCR. This method uses
        the exact desktop matcher, confirmation policy and transcript store.
        """
        with self.lock:
            if (not self.running or self.index is None or type(generation) is not int or generation != self.generation
                    or type(sequence) is not int or sequence < self.last_frame
                    or sequence == self.last_frame and channel in self.processed_channels):
                return []
            if (channel not in {'dialogue', 'cinematic', 'tip', 'gameplay', 'fullframe'} or not isinstance(groups, list)
                    or len(groups) > 128 or type(dialogue_menu) is not bool
                    or any(not isinstance(text, str) or len(text) > 8192 for text in groups)):
                raise ValueError('Invalid bounded OCR observation')
            now = time.monotonic() if now is None else now
            if not isinstance(now, (int, float)) or not math.isfinite(now):
                raise ValueError('Invalid observation clock')
            admission_key = None
            if admission is not None:
                if type(admission) is not NativeFrameReceipt:
                    raise ValueError('An opaque native admission receipt is required')
                admission_key = admission.authorize(self, generation, sequence)
            continuous = admission_key is not None and admission_key is self._admission_key
            if admission_key is not self._admission_key:
                self.trackers.clear();self._independent_exact.clear();self._continuation_checks.clear()
                self.contexts.clear();self.floating_contexts.clear()
                self.nte_context.reset()
                self._admission_key = admission_key
            if self.last_time is not None and not 0 <= now - self.last_time <= 3:
                # OCR completion can be slower than the independently admitted
                # live images. Only direct exact confirmations may survive;
                # temporal publisher contexts always retain their old expiry.
                retain = self._independent_exact if continuous and not dialogue_menu else set()
                self.trackers = {key: tracker for key, tracker in self.trackers.items() if key in retain}
                self._continuation_checks = set(self.trackers)
                self.contexts.clear(); self.floating_contexts.clear()
                self.nte_context.reset()
            if dialogue_menu:
                self.contexts.clear();self.floating_contexts.clear()
            if sequence > self.last_frame:
                self.processed_channels.clear()
                self._visible_comics = ()
            self.processed_channels.add(channel)
            self.last_time, self.last_frame = now, sequence
            self.last_ocr = '\n'.join(groups)
            settings = self.settings.get()
            def eligible(hit):
                return capture_match_eligible(hit, capture_unvoiced=settings.capture_unvoiced,
                    capture_missing_audio=settings.capture_missing_audio,
                    mapped_voice=lambda choice: choice.voice_status == 'voiced' and self._has_original(choice))
            policy = floating_caption_policy(self.index.game, self.index,
                capture_unvoiced=settings.capture_unvoiced, capture_missing_audio=settings.capture_missing_audio)
            if channel == 'fullframe':
                if not policy.enabled or policy.menu_blocks_frame(dialogue_menu):
                    for key in list(self.trackers):
                        if key[0] == 'fullframe':
                            del self.trackers[key]
                    self._independent_exact = {key for key in self._independent_exact if key[0] != 'fullframe'}
                    self._continuation_checks = {key for key in self._continuation_checks if key[0] != 'fullframe'}
                    return []
                matches = self.index.match_full_frame_voice_lines(groups) if policy.voice_enabled else []
                if policy.silent_enabled:
                    matches += self.index.match_unvoiced_lines(groups)
                if policy.missing_enabled:
                    matches += self.index.match_missing_audio_lines(groups)
            else:
                matches = self.index.match_line_groups(groups, settings.fuzzy_threshold, channel=channel)
            matches = {hit.text_id: hit for hit in matches if eligible(hit)}
            if self.index.game == 'zzz':
                if channel == 'cinematic':
                    self._visible_comics = tuple(hit for hit in matches.values() if is_comic_text_id(hit.text_id))
                elif self._visible_comics:
                    matches = {identity: hit for identity, hit in matches.items()
                               if not is_cinematic_fragment(hit, self._visible_comics)}
            if (channel == 'cinematic' and self.index.game == 'zzz'
                    and self.index._zzz_cinema_occurrences and admission is not None):
                source_scope = proxy_source_scope(self.index, None, settings.zzz_proxy_voice)
                proxy_scope = (generation, source_scope)
                if self.zzz_proxy.scope != proxy_scope:
                    self.zzz_proxy.prepare(proxy_scope, settings.previous_zzz_cinema_proxy(source_scope))
                frame = admission.cinema_frame(self, generation, sequence, now)
                prior_player = self.zzz_proxy.voice(settings.zzz_proxy_voice)
                player = self.zzz_proxy.observe(self.index, [*(zzz_dialogue or []), *(zzz_captions or [])],
                    frame=frame, now=now, stable_frames=settings.stable_frames)
                if player and source_scope:
                    self.settings.remember_zzz_cinema_proxy(source_scope, player)
                if prior_player != self.zzz_proxy.voice(settings.zzz_proxy_voice):
                    prior_player = None
                hits = self.zzz_cinema.observe(self.index, zzz_captions or [],
                    scope=(proxy_scope, admission_key), frame=frame, now=now,
                    stable_frames=settings.stable_frames, player=prior_player)
                for hit in hits:
                    if eligible(hit):
                        binding = self.index._zzz_cinema_occurrences['rows'][hit.text_id]
                        for member in binding['member_text_ids']:
                            matches.pop(member, None)
                        matches[hit.text_id] = hit
            original_direct = matches
            matches, training = positioned_training_matches(self.index, matches, presentation_lines, frame_size,
                enabled=policy.silent_enabled, dialogue_menu=dialogue_menu)
            direct_exact = {text_id for text_id, hit in matches.items()
                if hit.kind == 'exact' and original_direct.get(text_id) is hit} if not dialogue_menu else set()
            scope = (generation, channel, self.index.source_locale, self.index.target_locale,
                self.index.player_voice, self.index._signature,
                settings.capture_unvoiced, settings.capture_missing_audio)
            if channel == 'fullframe':
                matches = observe_floating_contexts(self.index, groups, matches, self.floating_contexts, policy,
                    game=self.index.game, scope=scope, now=now, stable_frames=settings.stable_frames,
                    capturable=eligible, dialogue_menu=dialogue_menu, training=training)
                if policy.world_cues and policy.voice_enabled:
                    hit = self.index.match_endfield_world_caption(presentation_lines, frame_size)
                    if hit and eligible(hit):
                        matches[hit.text_id] = hit
                if (self.index.game == 'endfield' and policy.silent_enabled
                        and self.index.snapshot_metadata.get('publisher_sns_dialogue_ui')):
                    from .endfield_sns_presentation import merge_sns_observations
                    hits = self.index.match_endfield_sns_dialogue(presentation_lines, frame_size,
                        direct=tuple(matches.values()), dialogue_menu=dialogue_menu)
                    matches = merge_sns_observations(matches, [hit for hit in hits if eligible(hit)])
            if self.index.game == 'nte' and channel == 'dialogue':
                # Generic Endfield context cannot authorize NTE graph traversal.
                # Only genuine positioned menu/quality evidence can arm it.
                layout = nte_layout if isinstance(nte_layout, NativeNteCaption) else None
                default = next(iter(matches.values())) if len(matches) == 1 else None
                hit = self.nte_context.match(self.index, list(layout.groups) if layout else groups, default,
                    enabled=bool(layout and not layout.dialogue_menu and not dialogue_menu), scope=scope,
                    now=now, stable_frames=settings.stable_frames)
                if hit and eligible(hit):
                    matches[hit.text_id] = hit
            # Same authored predecessor mechanism as desktop. Every context is
            # generation/channel/kind scoped; no nearby-text voice fallback.
            for kind in self.context_kinds:
                if not kind or channel == 'fullframe' or dialogue_menu or self.index.game == 'nte':
                    continue
                context = self.contexts.setdefault((channel, kind), EndfieldCaptionContext())
                hit = context.observe(self.index, groups, matches.values(), channel=channel, kind=kind,
                    scope=scope, now=now, stable_frames=settings.stable_frames)
                if hit and eligible(hit):
                    matches[hit.text_id] = hit
            emitted = []
            # A preserved old direct hit cannot become a fuzzy/context-derived
            # confirmation merely because both resolve to the same text ID.
            for key in tuple(self._continuation_checks):
                if key[0] == channel:
                    if key[1] not in direct_exact:
                        self.trackers.pop(key, None)
                    self._continuation_checks.discard(key)
            self._independent_exact = {key for key in self._independent_exact if key[0] != channel}
            self._independent_exact.update((channel, text_id) for text_id in direct_exact)
            for key, tracker in list(self.trackers.items()):
                if key[0] == channel and key[1] not in matches:
                    tracker.observe(None)
            for text_id, hit in matches.items():
                tracker = self.trackers.setdefault((channel, text_id), StableMatchTracker())
                # A static comic page can yield only one fresh receiver frame.
                # The broad scan already matched the complete authored text.
                exact_comic = (channel == 'cinematic' and self.index.game == 'zzz'
                               and is_comic_text_id(text_id) and hit.kind == 'exact'
                               and hit.source_ocr in groups)
                tracker.configure(1 if exact_comic else
                    capture_confirmation_frames(hit, settings.stable_frames, full_frame=channel == 'fullframe'))
                if tracker.observe(text_id):
                    saved_channel = next((name for name in ('dialogue', 'cinematic', 'tip', 'gameplay')
                        if self.index.is_capture_text(hit.text_id, hit.english, name)), 'dialogue') if channel == 'fullframe' else channel
                    line, _ = self.history.add_or_upgrade_recent(hit, self.session_id, channel=saved_channel)
                    if line:
                        if self.direct_descriptor is not None:
                            row = self._source_row(hit)
                            if row and row.get('audio') and self._has_original(hit):
                                self.recordings.register(line.id, self.direct_descriptor, row, line_stamp=self._recording_stamp(line))
                                self._queue_original(line.id)
                            clip = None
                        else:
                            clip = self._clip(hit)
                        if clip:
                            # The saved relative generation keeps original audio
                            # available after imports and process death.
                            relative = clip.relative_to(self.libraries.root).as_posix()
                            line = self.history.update_audio(line.id, 'official-prepared/' + relative, True)
                        emitted.append(self._line(line))
            self.message = 'Reading current screen frames'
            self.state_version += 1
            return emitted

    def audio_path(self, line_id):
        with self.lock:
            relative = self.history.audio_path(line_id)
            if relative and relative.startswith('official-retained/'):
                if self._recording_line(line_id) is None:
                    return None
                path = self.recordings.path(line_id)
                return path if path and relative == 'official-retained/' + path.name else None
            if not relative or not relative.startswith('official-prepared/'):
                return None
            relative = relative.removeprefix('official-prepared/')
            parts = Path(relative).parts
            if len(parts) != 3 or not re_full_sha(parts[0]) or not CLIP.fullmatch('/'.join(parts[1:])):
                return None
            path = self.libraries.root / relative
            _no_links(path)
            if not path.is_file() or not 0 < path.stat().st_size <= MAX_AUDIO:
                return None
            with path.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != CLIP.fullmatch('/'.join(parts[1:]))[1]:
                    raise ValueError('The prepared original recording is corrupt')
            return path

    def _line(self, line):
        value = line.model_dump(mode='json')
        if not line.has_audio and self.recordings.matches(line.id, self._recording_stamp(line)):
            value['original_audio_expected'] = True
            value['audio_pending'] = line.id not in self.recording_errors
            if (value['audio_pending'] and not self.source_transition and self.index is not None
                    and line.game == self.index.game):
                # Opening saved history resumes an interrupted local conversion;
                # it neither starts capture nor authorizes a publisher transfer.
                self._queue_original(line.id)
        if line.has_audio:
            value['audio_source'] = 'original'
        return value

    def snapshot(self):
        with self.lock:
            index = self.index
            capture = CaptureSnapshot(running=self.running, active_game=index.game if index else None,
                phase='reading' if self.running else 'stopped', message=self.message, last_ocr=self.last_ocr)
            capture_payload = capture.model_dump(mode='json')
            capture_payload['source_generation'] = self.generation
            capture_payload['library_revision'] = self.directory.name if self.directory and SHA.fullmatch(self.directory.name) else None
            return {'context': {'runtime_id': self.runtime_id, 'state_version': self.state_version, 'account_generation': 0},
                'status': {'capture': capture_payload,
                    'textmaps': index.status() if index else {'ready': False, 'entry_count': 0, 'audio_count': 0, 'message': self.message},
                    'audio': {'ready': bool(index and index.audio_count), 'message': 'Downloaded original recordings play locally'},
                    'settings': self.settings.get().model_dump(mode='json'),
                    'session': {'id': self.session_id, 'line_count': self.history.count(self.session_id), 'total_line_count': self.history.count()},
                    'selected_languages': {index.game: {'source_locale': index.source_locale,
                        'source_language': study_language(index.source_locale)}} if index else {}},
                'lines': [self._line(line) for line in self.history.list()],
                'lexirise': {'configured': False, 'sent': {}}}


def re_full_sha(value):
    from .prepared_library import SHA
    return bool(SHA.fullmatch(value))
