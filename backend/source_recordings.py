"""Retained original recordings, independent of deletable publisher caches.

References are app-authored, content-addressed private JSON. Providers only
decode already downloaded originals into a caller-owned temporary directory.
No provider lookup, transfer or decoder runs while the capture lock is held.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
import threading

from .game_data import _write, _read
from .game_data_protocol import GAME_TITLES, GameDataError, private_handle
from .prepared_library import MAX_AUDIO
from .private_data_paths import _no_links

SHA = re.compile(r'[0-9a-f]{64}')
CLIP = re.compile(r'([0-9a-f]{64})\.(mp3|wav)')


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _identity(value):
    if type(value) is not int or not 0 < value <= 2**32 - 1:
        raise ValueError('Invalid local transcript identity')
    return str(value)


class OriginalRecordings:
    def __init__(self, root):
        self.root = Path(root).absolute()
        _no_links(self.root)
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._working = set()

    def register(self, line_id, descriptor, row, *, line_stamp=None):
        """Save the exact admitted authored occurrence, never an OCR guess."""
        identity = _identity(line_id)
        descriptor, row = private_handle(descriptor), private_handle(row)
        if (descriptor.get('game') not in GAME_TITLES or not descriptor.get('ready')
                or descriptor.get('request', {}).get('content_mode') != 'text-audio'
                or not row.get('audio') or row.get('audio_omitted_by_request')
                or row.get('voice_status') != 'voiced'):
            raise ValueError('A downloaded original voice binding is required')
        value = {'schema': 'original-recording-reference-v1', 'source': descriptor, 'row': row}
        encoded = _canonical(value)
        if len(encoded) > 2 * 1024**2:
            raise ValueError('The saved original reference exceeds its limit')
        reference = hashlib.sha256(encoded).hexdigest()
        _write(self.root / 'references' / (reference + '.json'), value)
        if line_stamp is not None and (not isinstance(line_stamp, str) or SHA.fullmatch(line_stamp) is None):
            raise ValueError('Invalid immutable transcript stamp')
        _write(self.root / 'lines' / (identity + '.json'), {'reference': reference, 'line_sha256': line_stamp})
        return reference

    def matches(self, line_id, stamp):
        pointer = _read(self.root / 'lines' / (_identity(line_id) + '.json'))
        return bool(isinstance(pointer, dict) and isinstance(stamp, str) and SHA.fullmatch(stamp)
            and pointer.get('line_sha256') == stamp)

    def reference(self, line_id):
        pointer = _read(self.root / 'lines' / (_identity(line_id) + '.json'))
        if pointer is None:
            return None
        reference = pointer.get('reference')
        if not isinstance(reference, str) or SHA.fullmatch(reference) is None:
            raise ValueError('The saved original reference is corrupt')
        value = _read(self.root / 'references' / (reference + '.json'))
        if (not isinstance(value, dict) or value.get('schema') != 'original-recording-reference-v1'
                or hashlib.sha256(_canonical(value)).hexdigest() != reference):
            raise ValueError('The saved original reference is corrupt')
        return reference, value

    def path(self, line_id):
        saved = self.reference(line_id)
        return self._path(saved[0]) if saved else None

    def _path(self, reference, *, verify=True):
        receipt = _read(self.root / 'resolved' / (reference + '.json'))
        if receipt is None:
            return None
        name = receipt.get('clip')
        match = CLIP.fullmatch(name) if isinstance(name, str) else None
        if match is None:
            raise ValueError('The retained original recording is corrupt')
        path = self.root / 'audio' / name
        _no_links(path)
        if not path.is_file() or not 0 < path.stat().st_size <= MAX_AUDIO:
            raise ValueError('The retained original recording is missing')
        if verify:
            with path.open('rb') as source:
                if hashlib.file_digest(source, 'sha256').hexdigest() != match[1]:
                    raise ValueError('The retained original recording is corrupt')
        return path

    def materialize(self, line_id, source_for, *, cancelled=lambda: False):
        """Resolve one local original outside OCR locks; publish only if current.

        source_for receives the saved opaque descriptor. Its provider.restore
        must be offline and has must certify locally materialized originals.
        A busy reference is retried later, never waited on under another lock.
        """
        def check():
            if cancelled():
                raise GameDataError('recording_cancelled', 'Original recording preparation stopped.', 409)
        check()
        saved = self.reference(line_id)
        if saved is None:
            return None
        reference, value = saved
        existing = self._path(reference)
        if existing is not None:
            check(); return existing
        with self._lock:
            if reference in self._working:
                raise GameDataError('recording_busy', 'This original recording is still being prepared.', 409)
            self._working.add(reference)
        try:
            check()
            voice = source_for(value['source'])
            check()
            if voice is None or voice.has(value['row']) is not True:
                raise GameDataError('original_not_downloaded', 'The downloaded original recording is unavailable.', 409)
            staging = self.root / 'staging'; _no_links(staging); staging.mkdir(exist_ok=True)
            with tempfile.TemporaryDirectory(prefix='decode-', dir=staging) as folder:
                temporary = Path(folder)
                result = voice.resolve(value['row'], temporary / 'original', cancelled=cancelled)
                check()
                if result is None:
                    raise GameDataError('original_decode_unavailable', 'This original recording could not be prepared.', 409)
                result = Path(result).absolute(); _no_links(result)
                if (not result.resolve().is_relative_to(temporary.resolve()) or result.suffix not in {'.mp3', '.wav'}
                        or not result.is_file() or not 0 < result.stat().st_size <= MAX_AUDIO):
                    raise ValueError('The original decoder returned an invalid private recording')
                with result.open('rb') as source:
                    digest = hashlib.file_digest(source, 'sha256').hexdigest()
                name = digest + result.suffix
                destination = self.root / 'audio' / name
                _no_links(destination); destination.parent.mkdir(exist_ok=True)
                check()
                # The source already belongs to our staging directory. Atomic
                # same-volume publication never retains a game-cache path.
                os.replace(result, destination)
                check()
                _write(self.root / 'resolved' / (reference + '.json'), {'clip': name})
                check()
                return self._path(reference)
        finally:
            with self._lock:
                self._working.discard(reference)

    def lines(self, game):
        if game not in GAME_TITLES:
            raise ValueError('Unsupported game')
        directory = self.root / 'lines'; _no_links(directory)
        if not directory.exists():
            return []
        result = []
        for path in directory.iterdir():
            _no_links(path)
            if not re.fullmatch(r'[1-9][0-9]{0,9}\.json', path.name):
                raise ValueError('The saved recording references need repair')
            identity = int(path.stem)
            saved = self.reference(identity)
            if saved[1]['source']['game'] == game:
                result.append(identity)
        return result

    def retained_bytes(self, game):
        # Storage polling needs actual file sizes, not repeated full-audio reads.
        # Playback/materialization still hash every returned recording.
        paths = {self._path(self.reference(identity)[0], verify=False) for identity in self.lines(game)} - {None}
        return sum(path.stat().st_size for path in paths)
