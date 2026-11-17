"""Authored originals survive cache deletion, scope loss and process restart."""
import copy
import hashlib
import json
import threading
import struct
import wave
from pathlib import Path

import pytest

from backend.game_data_protocol import GameDataError
from backend.source_recordings import OriginalRecordings


@pytest.fixture
def original(tmp_path):
    source = tmp_path / 'source'; source.mkdir()
    with wave.open(str(source / 'tone.wav'), 'wb') as stream:
        stream.setparams((1, 2, 16000, 0, 'NONE', 'NONE'))
        stream.writeframes(struct.pack('<h', 1000) * 1600)
    row = {'text_id': 'owned:line', 'english': 'Follow the river beyond the bridge.',
        'source_text': 'Follow the river beyond the bridge.', 'texts': {'en': 'Follow the river beyond the bridge.',
            'zh-Hans': '沿河走过桥。'}, 'audio': {'source': 'owned-authored-fixture'}, 'voice_status': 'voiced'}
    descriptor = {'game': 'zzz', 'ready': True, 'request': {'content_mode': 'text-audio'}, 'handle': {'authored': True}}
    return descriptor, row, (source / 'tone.wav').read_bytes()


class Voice:
    def __init__(self, raw): self.raw, self.calls = raw, 0
    def has(self, row): return row['audio'] == {'source': 'owned-authored-fixture'}
    def resolve(self, row, destination, *, cancelled):
        assert self.has(row); self.calls += 1
        path = destination.with_suffix('.wav'); path.write_bytes(self.raw)
        return path


def test_actual_private_wav_retained_after_source_deleted_and_fresh_reopen(tmp_path, original):
    descriptor, row, raw = original
    store = OriginalRecordings(tmp_path / 'retained'); voice = Voice(raw)
    store.register(1, descriptor, row)
    path = store.materialize(1, lambda saved: voice if saved == descriptor else None)
    assert path.read_bytes() == raw and path.stem == hashlib.sha256(raw).hexdigest()
    store.register(2, descriptor, row)
    assert store.materialize(2, lambda _: pytest.fail('Original already saved')) == path
    assert store.retained_bytes('zzz') == len(raw) and voice.calls == 1
    # Removing the publisher source has no effect on the durable private copy.
    (tmp_path / 'source/tone.wav').unlink()
    reopened = OriginalRecordings(tmp_path / 'retained')
    assert reopened.path(1).read_bytes() == raw
    assert reopened.lines('zzz') == [1, 2]


def test_complete_occurrence_and_encoding_identity_cannot_borrow_recording(tmp_path, original):
    descriptor, row, raw = original
    store = OriginalRecordings(tmp_path / 'retained'); voice = Voice(raw)
    first = store.register(1, descriptor, row)
    path = store.materialize(1, lambda _: voice)
    changed = copy.deepcopy(row); changed['texts']['zh-Hans'] += '新的翻译。'
    assert store.register(2, descriptor, changed) != first
    assert store.path(2) is None
    changed_descriptor = copy.deepcopy(descriptor); changed_descriptor['handle']['revision'] = 'next'
    assert store.register(3, changed_descriptor, row) != first
    assert store.path(3) is None and store.path(1) == path


def test_foreign_decoder_path_empty_original_and_tampering_fail_closed(tmp_path, original):
    descriptor, row, raw = original
    store = OriginalRecordings(tmp_path / 'retained'); store.register(1, descriptor, row)
    voice = Voice(raw)
    foreign = tmp_path / 'not-a-decoder-output.wav'; foreign.write_bytes(raw)
    voice.resolve = lambda *_, **__: foreign
    with pytest.raises(ValueError): store.materialize(1, lambda _: voice)
    assert store.path(1) is None and foreign.read_bytes() == raw
    voice.has = lambda _: False
    with pytest.raises(GameDataError): store.materialize(1, lambda _: voice)
    voice = Voice(raw); path = store.materialize(1, lambda _: voice)
    path.write_bytes(b'tampered')
    with pytest.raises(ValueError, match='corrupt'): store.path(1)


def test_changed_or_unplayable_source_reference_does_not_start_decoder(tmp_path, original):
    descriptor, row, raw = original
    store = OriginalRecordings(tmp_path / 'retained')
    for change in ({'audio': None}, {'voice_status': 'unknown'}, {'audio_omitted_by_request': True}):
        with pytest.raises(ValueError): store.register(1, descriptor, {**row, **change})
    descriptor['request']['content_mode'] = 'text'
    with pytest.raises(ValueError): store.register(1, descriptor, row)
    descriptor['request']['content_mode'] = 'text-audio'
    reference = store.register(1, descriptor, row)
    path = store.root / 'references' / (reference + '.json')
    value = json.loads(path.read_text()); value['row']['audio'] = {'different': True}
    path.write_text(json.dumps(value))
    with pytest.raises(ValueError, match='corrupt'):
        store.materialize(1, lambda _: pytest.fail('Corrupt reference reached provider'))


def test_delayed_old_owner_decoder_never_publishes_receipt(tmp_path, original):
    descriptor, row, raw = original
    store = OriginalRecordings(tmp_path / 'retained'); store.register(1, descriptor, row)
    started, release, cancelled = threading.Event(), threading.Event(), threading.Event()
    voice = Voice(raw); decode = voice.resolve
    def resolve(*args, **kwargs):
        started.set(); assert release.wait(3)
        return decode(*args, **kwargs)
    voice.resolve = resolve; failures = []
    def run():
        try: store.materialize(1, lambda _: voice, cancelled=cancelled.is_set)
        except GameDataError as error: failures.append(error.code)
    worker = threading.Thread(target=run); worker.start(); assert started.wait(2)
    with pytest.raises(GameDataError, match='still being prepared'):
        store.materialize(1, lambda _: pytest.fail('Duplicate decoder'))
    # A→B→A remains revoked; equality of the final profile is insufficient.
    cancelled.set(); release.set(); worker.join(3)
    assert not worker.is_alive() and failures == ['recording_cancelled']
    assert store.path(1) is None
    assert list((store.root / 'staging').iterdir()) == []
