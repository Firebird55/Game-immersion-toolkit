"""Adapt verified local publisher originals to the desktop capture callbacks."""
from __future__ import annotations

import hashlib
import json
import threading


def recording_stamp(line):
    value = line.model_dump(mode='json', exclude={'favorite', 'has_audio', 'voiced', 'audio_source', 'audio_pending'})
    for key in ('publisher_generation', 'publisher_request_sha256', 'publisher_occurrence_sha256'):
        if value.get(key) is None:
            value.pop(key, None)
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def occurrence(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':'),
        ensure_ascii=False, allow_nan=False).encode()).hexdigest()


class DesktopOriginalVoices:
    def __init__(self, host, owner, descriptor, index=None, *, saved_line=None):
        self.host, self.owner, self.descriptor = host, owner, descriptor
        self.locale = descriptor['request']['source_locale']
        self.game = descriptor['game']
        self._executor = host.audio_pool
        self.saved_line = saved_line
        self.rows = {}
        original_rows = (index.original_recording_rows() if index is not None and
            callable(getattr(index, 'original_recording_rows', None)) else index._records if index is not None else ())
        for row in original_rows:
            if row.get('audio') and not row.get('audio_omitted_by_request') and row.get('voice_status') == 'voiced':
                self.rows.setdefault(row['text_id'], []).append(row)
        self._slots, self._lock, self._working = threading.BoundedSemaphore(8), threading.Lock(), set()

    @property
    def ready(self):
        return bool(self.rows or self.saved_line)

    def status(self):
        return {'ready': self.ready, 'mapped_lines': len(self.rows),
            'message': 'Original voices from explicitly downloaded publisher data.'}

    def _stopped(self):
        return (self.host.service.closed or self.host.owner() != self.owner
            or (self.owner, self.game) in self.host.blocked)

    def has_variant(self, text_id, _english=None):
        return not self._stopped() and (text_id in self.rows
            or self.saved_line is not None and self.saved_line.text_id == text_id)

    def _row(self, line):
        if line.audio_omitted_by_request or line.publisher_generation != self.descriptor['revision']:
            return None
        request_hash = hashlib.sha256(json.dumps(self.descriptor['request'], sort_keys=True,
            separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
        if line.publisher_request_sha256 != request_hash:
            return None
        found = [row for row in self.rows.get(line.text_id, ())
            if occurrence(row) == line.publisher_occurrence_sha256]
        return found[0] if len(found) == 1 else None

    def schedule(self, text_id, line_id, callback, _english=None):
        if not self.has_variant(text_id) or not self._slots.acquire(blocking=False):
            return False
        line = self.host.runtime.transcript.get(line_id)
        if line is None or line.text_id != text_id or line.audio_omitted_by_request:
            self._slots.release(); return False
        stamp = recording_stamp(line)
        key = (line_id, stamp)
        with self._lock:
            if key in self._working:
                self._slots.release(); return False
            self._working.add(key)
        submitted = False
        try:
            with self.host.runtime.accounts.lock:
                if self._stopped():
                    return False
                records = self.host.recordings()
                if not records.matches(line_id, stamp):
                    row = self._row(line)
                    if row is None:
                        return False
                    descriptor = {**self.descriptor, '_desktop_profile': self.host.profile_root().name}
                    records.register(line_id, descriptor, row, line_stamp=stamp)
            def cancelled():
                current = self.host.runtime.transcript.get(line_id)
                return self._stopped() or current is None or recording_stamp(current) != stamp
            def work():
                try:
                    path = records.materialize(line_id,
                        lambda value: self.host.source_for(value, self.owner), cancelled=cancelled)
                    if not cancelled():
                        callback(line_id, 'publisher-original/' + path.name if path else None, bool(path))
                except Exception:
                    if not cancelled():
                        callback(line_id, None, False)
                finally:
                    with self._lock: self._working.discard(key)
                    self._slots.release()
            self._executor.submit(work)
            submitted = True
        except Exception:
            return False
        else:
            return True
        finally:
            # Early validation returns have not transferred slot ownership.
            if not submitted:
                with self._lock: self._working.discard(key)
                self._slots.release()
