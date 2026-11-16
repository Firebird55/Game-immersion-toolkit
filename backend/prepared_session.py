"""Shared production matching/confirmation/history with host-provided OCR frames."""
from __future__ import annotations

from datetime import datetime, timezone
from contextlib import contextmanager, nullcontext
import hashlib
import json
import math
from pathlib import Path
import secrets
import threading
import time

from .capture_confirmation import StableMatchTracker, capture_match_eligible
from .config import SettingsStore
from .endfield_caption_context import EndfieldCaptionContext
from .languages import study_language
from .models import AppSettings, CaptureSnapshot
from .multilingual_index import MultilingualTextIndex
from .prepared_library import CLIP, MAX_AUDIO, PreparedLibraryStore, _no_links
from .storage import TranscriptStore


class PreparedCaptureSession:
    def __init__(self, root):
        self.root = Path(root).absolute()
        _no_links(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.settings = SettingsStore(self.root / 'settings.json')
        self.history = TranscriptStore(self.root / 'transcript.db')
        self.libraries = PreparedLibraryStore(self.root / 'libraries')
        self.runtime_id = secrets.token_hex(16)
        self.state_version = self.generation = 0
        self.session_id = secrets.token_hex(16)
        self.running = False
        self.last_frame = -1
        self.processed_channels = set()
        self.last_time = None
        self.trackers = {}
        self.contexts = {}
        self.index = self.directory = None
        self.records_by_id = {}
        self.context_kinds = set()
        self.last_ocr = ''
        self.message = 'Import a private prepared library to begin'
        self._activate_current()

    def _activate_current(self):
        directory = self.libraries.current()
        if directory is None:
            return
        payload = json.loads((directory / 'textmap.json').read_text(encoding='utf8'))
        index = MultilingualTextIndex(payload['game'], directory)
        if not index.ready:
            raise ValueError('The shared matcher could not open this library')
        self._activate_prepared(directory, index)

    def _activate_prepared(self, directory, index):
        self.directory, self.index = directory, index
        self.records_by_id = {}
        for row in index._records:
            self.records_by_id.setdefault(row['text_id'], []).append(row)
        self.context_kinds = {row.get('dialogue_kind') for row in index._records if row.get('previous_text_id')}
        self._apply_settings()
        self.message = 'Prepared library ready; start a supported screen source'

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
            self.last_frame, self.last_time = -1, None
            self.processed_channels.clear()
            self.trackers.clear(); self.contexts.clear()
            self.message = message
            self.state_version += 1

    def start(self):
        with self.lock:
            if self.index is None:
                raise ValueError('Import a prepared library before starting capture')
            self.stop()
            self.running = True
            self.message = 'Waiting for fresh screen frames'
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
        if not CLIP.fullmatch(name):
            return None
        path = self.directory / name
        _no_links(path)
        return path if path.is_file() and path.stat().st_size <= MAX_AUDIO else None

    def observe(self, generation, sequence, groups, *, channel='dialogue', now=None):
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
                    or len(groups) > 128 or any(not isinstance(text, str) or len(text) > 8192 for text in groups)):
                raise ValueError('Invalid bounded OCR observation')
            now = time.monotonic() if now is None else now
            if not isinstance(now, (int, float)) or not math.isfinite(now):
                raise ValueError('Invalid observation clock')
            if self.last_time is not None and not 0 <= now - self.last_time <= 3:
                self.trackers.clear(); self.contexts.clear()
            if sequence > self.last_frame:
                self.processed_channels.clear()
            self.processed_channels.add(channel)
            self.last_time, self.last_frame = now, sequence
            self.last_ocr = '\n'.join(groups)
            settings = self.settings.get()
            if channel == 'fullframe':
                matches = self.index.match_full_frame_voice_lines(groups)
                if settings.capture_unvoiced:
                    matches += self.index.match_unvoiced_lines(groups)
                if settings.capture_missing_audio:
                    matches += self.index.match_missing_audio_lines(groups)
            else:
                matches = self.index.match_line_groups(groups, settings.fuzzy_threshold, channel=channel)
            matches = {hit.text_id: hit for hit in matches if capture_match_eligible(hit,
                capture_unvoiced=settings.capture_unvoiced, capture_missing_audio=settings.capture_missing_audio,
                mapped_voice=lambda hit: hit.voice_status == 'voiced' and self._clip(hit) is not None)}
            # Same authored predecessor mechanism as desktop. Every context is
            # generation/channel/kind scoped; no nearby-text voice fallback.
            for kind in self.context_kinds:
                if not kind:
                    continue
                if channel == 'fullframe' and kind not in ({'cinematic'} if self.index.game == 'endfield'
                        else {'music_subtitle'} if self.index.game == 'wuwa' else set()):
                    continue
                context = self.contexts.setdefault((channel, kind), EndfieldCaptionContext())
                hit = context.observe(self.index, groups, matches.values(), channel='cinematic' if channel == 'fullframe' else channel, kind=kind,
                    scope=(generation, channel, self.index.source_locale, self.index.target_locale,
                           self.index.player_voice), now=now, stable_frames=settings.stable_frames)
                if hit and capture_match_eligible(hit, capture_unvoiced=settings.capture_unvoiced,
                        capture_missing_audio=settings.capture_missing_audio, mapped_voice=lambda hit: self._clip(hit) is not None):
                    matches[hit.text_id] = hit
            emitted = []
            for key, tracker in list(self.trackers.items()):
                if key[0] == channel and key[1] not in matches:
                    tracker.observe(None)
            for text_id, hit in matches.items():
                tracker = self.trackers.setdefault((channel, text_id), StableMatchTracker())
                tracker.configure(settings.stable_frames)
                if tracker.observe(text_id):
                    saved_channel = next((name for name in ('dialogue', 'cinematic', 'tip', 'gameplay')
                        if self.index.is_capture_text(hit.text_id, hit.english, name)), 'dialogue') if channel == 'fullframe' else channel
                    line, _ = self.history.add_or_upgrade_recent(hit, self.session_id, channel=saved_channel)
                    if line:
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

    @staticmethod
    def _line(line):
        value = line.model_dump(mode='json')
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
            return {'context': {'runtime_id': self.runtime_id, 'state_version': self.state_version, 'account_generation': 0},
                'status': {'capture': capture_payload,
                    'textmaps': index.status() if index else {'ready': False, 'entry_count': 0, 'audio_count': 0, 'message': self.message},
                    'audio': {'ready': bool(index and index.audio_count), 'message': 'Prepared original recordings play locally'},
                    'settings': self.settings.get().model_dump(mode='json'),
                    'session': {'id': self.session_id, 'line_count': self.history.count(self.session_id), 'total_line_count': self.history.count()},
                    'selected_languages': {index.game: {'source_locale': index.source_locale,
                        'source_language': study_language(index.source_locale)}} if index else {}},
                'lines': [self._line(line) for line in self.history.list()],
                'lexirise': {'configured': False, 'sent': {}}}


def re_full_sha(value):
    from .prepared_library import SHA
    return bool(SHA.fullmatch(value))
