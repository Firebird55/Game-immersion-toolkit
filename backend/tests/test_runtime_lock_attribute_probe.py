"""Authored boundary fixtures only; these never establish Windows behavior."""
import copy
import ctypes
import io
import json
import os
from pathlib import Path, PureWindowsPath
import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest

from backend import runtime_lock_attribute_probe as module


def snapshot(attributes=128, times=None):
    return {'identity': [7, 'a' * 32], 'attributes': attributes, 'times': times or [10, 20, 30, 40]}


@pytest.mark.parametrize('attributes', [1, 33])
def test_readonly_transition_preserves_identity_other_attributes_and_explicit_time_outcomes(attributes):
    original = snapshot(128 if attributes == 1 else 32)
    observed = snapshot(attributes, [10, 21, 30, 41])
    assert module.transition(original, observed, True) == {
        'creation_equal': True, 'access_equal': False, 'write_equal': True, 'change_equal': False}
    assert module.transition(original, copy.deepcopy(original), False) == dict.fromkeys(
        ('creation_equal', 'access_equal', 'write_equal', 'change_equal'), True)


@pytest.mark.parametrize('mutation', ['volume', 'file', 'hidden', 'missing-readonly', 'creation', 'write', 'normal-combined'])
def test_unexpected_identity_attributes_or_data_timestamps_cannot_become_verified(mutation):
    observed = snapshot(1)
    if mutation == 'volume': observed['identity'][0] += 1
    if mutation == 'file': observed['identity'][1] = 'b' * 32
    if mutation == 'hidden': observed['attributes'] |= 2
    if mutation == 'missing-readonly': observed['attributes'] = 128
    if mutation == 'creation': observed['times'][0] += 1
    if mutation == 'write': observed['times'][2] += 1
    if mutation == 'normal-combined': observed['attributes'] = 129
    with pytest.raises(module.Refused): module.transition(snapshot(), observed, True)


@pytest.mark.parametrize('value', [None, {}, {'identity': 'private-file-id'},
    {'identity': [True, 'a' * 32], 'attributes': 128, 'times': [1, 2, 3, 4]},
    {'identity': [1, 'a' * 32], 'attributes': 128, 'times': [1, 2, 3, 'private-time']},
    {'identity': [1, 'a' * 32], 'attributes': 128, 'times': [1, 2, 3, 4], 'path': 'private-path'}])
def test_private_wire_snapshot_is_closed_and_typed(value):
    with pytest.raises(module.Refused): module.private_snapshot(value)


@pytest.mark.parametrize('raw', [b'[]', b'null', b'{"state":"x","state":"y"}', b'\xff', b'x' * 4097])
def test_private_frames_refuse_duplicates_untyped_nonascii_and_overflow(raw):
    with pytest.raises(module.Refused): module.decode(raw)


@pytest.mark.parametrize('kind', ['false', 'exception'])
def test_unknown_close_is_sticky_and_never_reuses_a_numeric_handle(kind):
    calls = []
    def close(handle):
        calls.append(handle)
        if kind == 'exception': raise OSError('private close sentinel')
        return 0
    handle = module.Handle(SimpleNamespace(k=SimpleNamespace(CloseHandle=close)), 123)
    with pytest.raises((module.Refused, OSError)): handle.close()
    with pytest.raises(module.Refused): handle.close()
    with pytest.raises(module.Refused): _ = handle.value
    assert calls == [123] and handle.poisoned
    assert any(record is handle for record in module._UNCONFIRMED)


def test_successful_close_is_idempotent_and_exposure_stops():
    calls = []
    handle = module.Handle(SimpleNamespace(k=SimpleNamespace(CloseHandle=lambda h: calls.append(h) or 1)), 123)
    handle.close(); handle.close()
    assert calls == [123]
    with pytest.raises(module.Refused): _ = handle.value


def test_native_basic_info_abi_and_attribute_set_do_not_change_other_fields():
    assert ctypes.sizeof(module.Basic) == 40 and module.Basic.attributes.offset == 32
    assert ctypes.sizeof(module.Identity) == ctypes.sizeof(module.Standard) == 24
    calls = []
    def set_information(handle, kind, information, size):
        value = information._obj
        calls.append((handle, kind, size, value.attributes,
            tuple(getattr(value, name) for name in ('creation', 'access', 'write', 'change'))))
        return 1
    api = module.Windows.__new__(module.Windows)
    api.k = SimpleNamespace(SetFileInformationByHandle=set_information)
    handle = module.Handle(api, 123)
    api.attributes(handle, 128, True)
    api.attributes(handle, 128, False)
    api.attributes(handle, 32, True)
    assert calls == [(123, 0, 40, 1, (0, 0, 0, 0)),
                     (123, 0, 40, 128, (0, 0, 0, 0)),
                     (123, 0, 40, 33, (0, 0, 0, 0))]


@pytest.mark.parametrize('mismatch', ['links', 'directory', 'deleting', 'size', 'attribute', 'content'])
def test_native_snapshot_refuses_unexpected_file_before_any_state_is_accepted(mismatch):
    calls = []
    def query(handle, kind, information, size):
        assert handle == 123
        calls.append(kind)
        value = information._obj
        if kind == 0:
            value.attributes = 2 if mismatch == 'attribute' else 128
            value.creation, value.access, value.write, value.change = 10, 20, 30, 40
        elif kind == 18:
            value.volume = 7
        elif kind == 1:
            value.links = 2 if mismatch == 'links' else 1
            value.directory = mismatch == 'directory'
            value.deleting = mismatch == 'deleting'
            value.size = len(module.CONTENT) + (mismatch == 'size')
        return 1
    def read(handle, output, size, count, overlapped):
        calls.append('read')
        data = b'bad' if mismatch == 'content' else module.CONTENT
        ctypes.memmove(output, data, len(data)); count._obj.value = len(data); return 1
    api = module.Windows.__new__(module.Windows)
    api.k = SimpleNamespace(GetFileInformationByHandleEx=query, SetFilePointerEx=lambda *_: 1, ReadFile=read)
    with pytest.raises(module.Refused): api.snapshot(module.Handle(api, 123))
    assert ('read' in calls) is (mismatch == 'content')


@pytest.mark.parametrize('failed', ['child', 'terminate', 'owner-close', 'pipe'])
def test_owned_cleanup_attempts_all_independent_steps_and_keeps_uncertainty(failed):
    calls = []
    def call(label):
        calls.append(label)
        if label == failed: raise OSError('private cleanup sentinel')
    attempt = module.Attempt.__new__(module.Attempt)
    attempt.closed = attempt.poisoned = False
    attempt.checkpoint, attempt.checkpoint_locked = None, False
    attempt.child = SimpleNamespace(stop_and_wait=lambda _: call('child'))
    attempt.owner = SimpleNamespace(terminate=lambda **_: call('terminate'), close=lambda: call('owner-close'))
    attempt.pipe = SimpleNamespace(close=lambda: call('pipe'))
    with pytest.raises(module.Refused, match='owned-cleanup-unconfirmed'): attempt.close()
    assert calls == ['child', 'terminate', 'owner-close', 'pipe']
    assert any(record is attempt for record in module._UNCONFIRMED)
    with pytest.raises(module.Refused): attempt.close()
    assert calls == ['child', 'terminate', 'owner-close', 'pipe']


def test_pipe_client_identity_is_compared_to_creation_handle_without_pid_adoption():
    calls = []
    def client(handle, output): output._obj.value = 222; calls.append('client'); return 1
    pipe = module.Pipe.__new__(module.Pipe)
    pipe.api = SimpleNamespace(check=lambda value: value, k=SimpleNamespace(
        GetProcessId=lambda handle: calls.append(('genuine-handle', handle)) or 111,
        GetNamedPipeClientProcessId=client))
    pipe.handle = module.Handle(pipe.api, 8)
    with pytest.raises(module.Refused): pipe.bind(SimpleNamespace(process_handle=9), float('inf'))
    assert calls == [('genuine-handle', 9), 'client']


@pytest.mark.parametrize('payload', [b'{"state":"held"}\n', b'{"state":"held"}\r\n'])
def test_nonblocking_pipe_receives_only_bounded_private_frames(payload):
    pending = bytearray(payload)
    calls = []
    def peek(handle, data, size, read, available, left): available._obj.value = len(pending); return 1
    def read(handle, output, size, received, overlapped):
        calls.append(size)
        chunk = bytes(pending[:size]); del pending[:size]
        ctypes.memmove(output, chunk, len(chunk)); received._obj.value = len(chunk); return 1
    pipe = module.Pipe.__new__(module.Pipe)
    pipe.api = SimpleNamespace(check=lambda value: value, k=SimpleNamespace(PeekNamedPipe=peek, ReadFile=read))
    pipe.handle, pipe.buffer, pipe.received = module.Handle(pipe.api, 8), bytearray(), 0
    assert pipe.receive(float('inf')) == {'state': 'held'}
    assert calls and max(calls) <= module.LIMIT + 1


def test_pipe_overflow_is_rejected_before_json_decoding():
    def peek(handle, data, size, read, available, left): available._obj.value = 10000; return 1
    def read(handle, output, size, received, overlapped):
        assert size == module.LIMIT + 1
        ctypes.memmove(output, b'x' * size, size); received._obj.value = size; return 1
    pipe = module.Pipe.__new__(module.Pipe)
    pipe.api = SimpleNamespace(check=lambda value: value, k=SimpleNamespace(PeekNamedPipe=peek, ReadFile=read))
    pipe.handle, pipe.buffer, pipe.received = module.Handle(pipe.api, 8), bytearray(), 0
    with pytest.raises(module.Refused): pipe.receive(float('inf'))


def successful_receipt():
    value = module.receipt()
    value.update(status='mechanism-observed', phase='complete', failure='none',
        cleanup='owned-handles-closed-fixture-retained', legacy_source_sha256=next(iter(module.SOURCE_HASHES)),
        observed=list(module.OBSERVATIONS), timestamp_equalities={name: dict.fromkeys(
            ('creation_equal', 'access_equal', 'write_equal', 'change_equal'), True) for name in module.TIME_STATES})
    return value


@pytest.mark.parametrize('mutation', ['raw', 'gate', 'count-bool', 'unknown-event', 'order', 'missing',
    'private-time', 'numeric-time', 'private-hash', 'cleanup', 'failure', 'creation-changed', 'write-changed'])
def test_public_receipt_cannot_publish_private_values_or_promote_incomplete_result(mutation):
    value = successful_receipt()
    if mutation == 'raw': value['path'] = 'private-authored-path'
    if mutation == 'gate': value['r19_complete'] = True
    if mutation == 'count-bool': value['candidate_data_writers'] = False
    if mutation == 'unknown-event': value['observed'][0] = 'private-unknown-event'
    if mutation == 'order': value['observed'][0:2] = reversed(value['observed'][0:2])
    if mutation == 'missing': value['observed'].pop()
    if mutation == 'private-time': value['timestamp_equalities']['arm']['change_equal'] = 'private-time'
    if mutation == 'numeric-time': value['timestamp_equalities']['arm']['change_equal'] = 1
    if mutation == 'private-hash': value['legacy_source_sha256'] = 'b' * 64
    if mutation == 'cleanup': value['cleanup'] = 'private-unverified-cleanup'
    if mutation == 'failure': value['failure'] = 'protocol-refused'
    if mutation == 'creation-changed': value['timestamp_equalities']['arm']['creation_equal'] = False
    if mutation == 'write-changed': value['timestamp_equalities']['arm']['write_equal'] = False
    with pytest.raises(module.Refused): module.public_receipt(value)


def test_public_receipt_copies_nested_booleans_and_keeps_all_acceptance_gates_closed():
    original = successful_receipt()
    result = module.public_receipt(original)
    original['timestamp_equalities']['arm']['change_equal'] = False
    assert result['timestamp_equalities']['arm']['change_equal'] is True
    assert result['candidate_data_writers'] == 0 and result['keeper_loss_acceptance'] is False
    assert result['r19_complete'] is result['rights_approval'] is result['production_allowed'] is False


@pytest.fixture
def authored(monkeypatch, tmp_path):
    """Behavior double: no Windows attribute/open/process call is executed."""
    monkeypatch.setattr(module.tempfile, 'gettempdir', lambda: str(tmp_path.resolve()))
    class API:
        def __init__(self):
            self.events, self.lease, self.armed, self.read_handles = [], False, False, []
        def ntfs(self, root): self.events.append('authored-filesystem-double')
        def image(self): return 'owned-python-placeholder'
        def open(self, path, access):
            assert access == module.RESTORE and access & 0x40000000 == 0
            handle = object(); self.read_handles.append(handle); self.events.append('restore-open'); return handle
        def snapshot(self, handle):
            assert handle in self.read_handles
            return snapshot(1 if self.armed else 128, [10, 20, 30, 41])
        def attributes(self, handle, original, armed):
            assert handle in self.read_handles and not self.lease and original == 128
            self.armed = armed; self.events.append('restore-clear')
        def close(self, handle): self.read_handles.remove(handle); self.events.append('restore-close')
    api = API()
    class Attempt:
        def __init__(self, *_): api.lease = True; self.closed = False; api.events.append('owned-lease-start')
        def exchange(self, value):
            if 'root' in value: return {'state': 'held', 'snapshot': snapshot()}
            phase = value['command']; api.armed = phase != 'live-clear'; api.events.append(phase)
            return {'state': phase, 'snapshot': snapshot(1 if api.armed else 128, [10, 20, 30, 41])}
        def close(self):
            if not self.closed:
                api.lease, self.closed = False, True; api.events.append('owned-lease-stop')
    def legacy(_api, root, source, expected, *, checkpoint_value=None, conversion_failure_value=None):
        api.events.append(expected)
        if expected == 'open': assert not api.lease and not api.read_handles and not api.armed
        elif expected == 'readonly-refused': assert not api.lease and not api.read_handles and api.armed
        elif expected == 'sharing-refused': assert api.lease or api.read_handles
        else: pytest.fail('Unexpected authored transition.')
    monkeypatch.setattr(module, 'Windows', lambda: api)
    monkeypatch.setattr(module, 'Attempt', Attempt)
    monkeypatch.setattr(module, 'legacy', legacy)
    return api


def test_authored_state_sequence_never_releases_old_open_during_normal_clear_or_test_restore(authored, tmp_path):
    result = module.experiment()
    assert result['status'] == 'mechanism-observed' and tuple(result['observed']) == module.OBSERVATIONS
    assert not authored.lease and not authored.read_handles and not authored.armed
    assert authored.events.index('owned-lease-stop') < authored.events.index('readonly-refused')
    assert authored.events.index('restore-clear') < len(authored.events) - 1
    assert result['timestamp_equalities']['post-loss']['change_equal'] is False
    roots = list(tmp_path.glob('r19-lock-attribute-*'))
    assert len(roots) == 1 and (roots[0] / 'data/companion-operation.lock').read_bytes() == module.CONTENT
    assert 'private' not in json.dumps(result) and str(tmp_path) not in json.dumps(result)


def test_post_loss_refusal_mismatch_retains_readonly_and_never_clears_for_convenience(authored, monkeypatch, tmp_path):
    previous = module.legacy
    def refuse(api, root, source, expected, *, checkpoint_value=None, conversion_failure_value=None):
        if expected == 'readonly-refused': raise module.Refused('legacy-outcome-differed')
        return previous(api, root, source, expected, checkpoint_value=checkpoint_value,
            conversion_failure_value=conversion_failure_value)
    monkeypatch.setattr(module, 'legacy', refuse)
    result = module.experiment()
    assert result['status'] == 'failed' and result['failure'] == 'legacy-outcome-differed'
    assert authored.armed and not authored.lease and not authored.read_handles
    assert 'restore-clear' not in authored.events
    assert len(list(tmp_path.glob('r19-lock-attribute-*'))) == 1


def test_unsupported_host_refuses_before_creating_a_fixture(monkeypatch):
    def unavailable(): raise module.Refused('unsupported-host')
    monkeypatch.setattr(module, 'Windows', unavailable)
    monkeypatch.setattr(module.tempfile, 'mkdtemp', lambda **_: pytest.fail('No fixture on unsupported host.'))
    result = module.experiment()
    assert result['status'] == 'failed' and result['failure'] == 'unsupported-host'
    assert not result['observed']


def test_nonlocal_or_non_ntfs_temp_refuses_before_any_fixture_write(monkeypatch):
    def refuse(_root): raise module.Refused('fixture-refused')
    monkeypatch.setattr(module, 'Windows', lambda: SimpleNamespace(ntfs=refuse))
    monkeypatch.setattr(module.tempfile, 'mkdtemp', lambda **_: pytest.fail('No unsupported-volume fixture write.'))
    result = module.experiment()
    assert result['status'] == 'failed' and result['failure'] == 'fixture-refused'


def test_fixture_marker_is_bounded_and_ancestor_link_refused_before_marker_read(tmp_path, monkeypatch):
    monkeypatch.setattr(module.tempfile, 'gettempdir', lambda: str(tmp_path.resolve()))
    root = tmp_path / 'r19-lock-attribute-authored'
    root.mkdir(); (root / 'data').mkdir()
    (root / 'data/companion-operation.lock').write_bytes(module.CONTENT)
    marker = root / module.MARKER
    marker.write_bytes(b'x' * (module.LIMIT + 1))
    with pytest.raises(module.Refused): module.fixture(root, 'a' * 32)
    outside = tmp_path / 'outside'; outside.mkdir()
    marker.unlink(); marker.symlink_to(outside / 'never-read')
    with pytest.raises(module.Refused): module.fixture(root, 'a' * 32)


def progress_attempt(frames=None):
    class Wire:
        def __init__(self):
            self.frames = list(frames if frames is not None else [
                *({'kind': 'checkpoint', 'stage': name} for name in module.SCRIPT_STEPS[1:-1]),
                {'state': 'open'}])
            self.deadlines = []
        def send(self, value, deadline): self.deadlines.append(deadline)
        def receive(self, deadline):
            self.deadlines.append(deadline)
            if not self.frames: raise module.Refused('protocol-refused')
            value = self.frames.pop(0)
            if isinstance(value, BaseException): raise value
            return value
        def finish(self, deadline):
            self.deadlines.append(deadline)
            if self.frames: raise module.Refused('protocol-refused')
    attempt = module.Attempt.__new__(module.Attempt)
    attempt.pipe, attempt.checkpoint, attempt.checkpoint_locked = Wire(), module.checkpoint(), False
    attempt.conversion_failure_value = [None]
    return attempt


def test_complete_progress_keeps_terminal_result_and_one_exchange_deadline(monkeypatch):
    monkeypatch.setattr(module.time, 'monotonic', lambda: 100.)
    attempt = progress_attempt()
    assert attempt.script_exchange({'owned': 'grant'}) == {'state': 'open'}
    assert attempt.checkpoint == {'parent_step': 'receive-result', 'script_step': 'operationresult', 'child_state': 'not-created'}
    assert set(attempt.pipe.deadlines) == {110.}


@pytest.mark.parametrize('mutation', ['duplicate', 'skip', 'unknown', 'private-key', 'wrong-order', 'early-result', 'truncated', 'unknown-result'])
def test_progress_rejects_bad_order_and_keeps_only_the_last_complete_checkpoint(mutation):
    attempt = progress_attempt()
    frames = attempt.pipe.frames
    boundary = next(i for i, frame in enumerate(frames) if frame.get('stage') == 'sourceopened')
    if mutation == 'duplicate': frames[boundary] = dict(frames[boundary-1])
    if mutation == 'skip': frames.pop(boundary)
    if mutation == 'unknown': frames[boundary] = {'kind': 'checkpoint', 'stage': 'private-unknown-stage'}
    if mutation == 'private-key': frames[boundary]['raw'] = 'private-path'
    if mutation == 'wrong-order': frames[boundary], frames[boundary+1] = frames[boundary+1], frames[boundary]
    if mutation == 'early-result': frames[boundary] = {'state': 'open'}
    if mutation == 'truncated': frames[boundary] = module.Refused('protocol-refused')
    if mutation == 'unknown-result': frames[-1] = {'state': 'private-unknown-result'}
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert attempt.checkpoint['script_step'] == ('operationentered' if mutation == 'unknown-result' else 'grantvalidated')
    assert attempt.checkpoint_locked and 'private-' not in json.dumps(attempt.checkpoint)


@pytest.mark.parametrize(('stages', 'tail', 'last'), [
    (['connected'], [], 'connected'),
    (['connected', 'grantread'], [], 'grantread'),
    (['connected', 'grantread', 'grantparsed'], [], 'grantparsed'),
    (['connected', 'grantparsed'], [], 'connected'),
    (['connected', 'grantread', 'grantread'], [], 'grantread'),
    (['connected', 'grantread', 'grantvalidated'], [], 'grantread'),
    (['connected', 'grantread'], [None], 'grantread'),
    (['connected', 'grantread'], [{'kind': 'checkpoint', 'stage': 'grantparsed', 'raw': 'private-grant'}], 'grantread'),
    (['connected', 'grantread', 'grantparsed'], [None], 'grantparsed'),
    (['connected', 'grantread', 'grantparsed'], [{'kind': 'checkpoint', 'stage': 'grantvalidated', 'raw': 'private-grant'}], 'grantparsed'),
])
def test_grant_return_checkpoints_never_imply_shape_validation_or_operation(stages, tail, last):
    attempt = progress_attempt([*({'kind': 'checkpoint', 'stage': name} for name in stages), *tail])
    with pytest.raises(module.Refused): attempt.script_exchange({'owned': 'grant'})
    assert attempt.checkpoint == {'parent_step': 'receive-script-progress',
        'script_step': last, 'child_state': 'not-created'}
    assert attempt.checkpoint_locked
    value = module.receipt(); value['baseline_checkpoint'] = attempt.checkpoint
    public = module.public_receipt(value)
    assert public['status'] == 'failed' and public['observed'] == []
    assert public['baseline_checkpoint']['script_step'] == last
    assert 'private-grant' not in json.dumps(public)


def conversion_frame(**changes):
    value = {'kind': 'grant-conversion-failure', 'line': 'nonempty',
        'exceptions': ['cmdlet-invocation', 'argument'], 'chain_end': 'complete',
        'category': 'InvalidArgument'}
    value.update(changes)
    return value


def conversion_attempt(frame=None, trailing=()):
    return progress_attempt([{'kind': 'checkpoint', 'stage': 'connected'},
        {'kind': 'checkpoint', 'stage': 'grantread'}, frame if frame is not None else conversion_frame(), *trailing])


def conversion_receipt(payload=None):
    value = module.receipt()
    value.update(phase='legacy-baseline', failure='protocol-refused',
        legacy_source_sha256=next(iter(module.SOURCE_HASHES)),
        baseline_checkpoint={'parent_step': 'receive-script-progress', 'script_step': 'grantread',
            'child_state': 'unavailable'},
        grant_conversion_failure=payload or {k: v for k, v in conversion_frame().items() if k != 'kind'})
    return value


def test_conversion_failure_is_committed_only_after_eof_and_still_refuses_under_one_deadline(monkeypatch):
    monkeypatch.setattr(module.time, 'monotonic', lambda: 100.)
    attempt = conversion_attempt()
    finish = attempt.pipe.finish
    def complete(deadline):
        assert attempt.conversion_failure_value == [None]
        finish(deadline)
    attempt.pipe.finish = complete
    with pytest.raises(module.Refused, match='protocol-refused'): attempt.script_exchange({})
    expected = {k: v for k, v in conversion_frame().items() if k != 'kind'}
    assert attempt.conversion_failure_value == [expected]
    assert set(attempt.pipe.deadlines) == {110.}
    assert attempt.checkpoint_locked and attempt.checkpoint['script_step'] == 'grantread'
    assert attempt.checkpoint['parent_step'] == 'receive-script-progress'
    assert module.public_receipt(conversion_receipt(expected))['grant_conversion_failure'] == expected


@pytest.mark.parametrize('fault', ['duplicate', 'trailing-progress', 'trailing-terminal', 'unconfirmed-eof'])
def test_conversion_failure_incomplete_termination_keeps_public_default_null(fault, monkeypatch):
    trailing = [conversion_frame()] if fault == 'duplicate' else [
        {'kind': 'checkpoint', 'stage': 'grantparsed'}] if fault == 'trailing-progress' else [
        {'state': 'open'}] if fault == 'trailing-terminal' else []
    attempt = conversion_attempt(trailing=trailing)
    if fault == 'unconfirmed-eof':
        def refuse(deadline): raise module.Refused('protocol-refused')
        monkeypatch.setattr(attempt.pipe, 'finish', refuse)
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert attempt.conversion_failure_value == [None]
    assert attempt.checkpoint_locked and attempt.checkpoint['script_step'] == 'grantread'


def test_conversion_failure_eof_uses_actual_pipe_deadline_without_extending_exchange(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'sleep', lambda value: clock.__setitem__(0, clock[0]+value))
    attempt = conversion_attempt()
    attempt.pipe.buffer = bytearray()
    attempt.pipe.handle = SimpleNamespace(value=1)
    attempt.pipe.api = SimpleNamespace(k=SimpleNamespace(PeekNamedPipe=lambda *_: True))
    monkeypatch.setattr(attempt.pipe, 'finish', lambda deadline: module.Pipe.finish(attempt.pipe, deadline))
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert 10 <= clock[0] < 10.02 and set(attempt.pipe.deadlines) == {10.}
    assert attempt.conversion_failure_value == [None] and attempt.checkpoint_locked
    assert attempt.checkpoint['script_step'] == 'grantread'


@pytest.mark.parametrize('before', [[], ['connected'], ['connected', 'grantread', 'grantparsed'],
    ['connected', 'grantread', 'grantparsed', 'grantvalidated', 'sourceopened']])
def test_conversion_failure_is_not_admitted_at_other_progress_boundaries(before):
    attempt = progress_attempt([*({'kind': 'checkpoint', 'stage': name} for name in before), conversion_frame()])
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert attempt.conversion_failure_value == [None]
    assert attempt.checkpoint['script_step'] == (before[-1] if before else 'not-started')


def test_later_contender_without_baseline_holder_cannot_publish_conversion_context():
    attempt = conversion_attempt(); attempt.conversion_failure_value = None
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert attempt.conversion_failure_value is None


@pytest.mark.parametrize('changes', [
    {'line': None}, {'line': 'private-line'}, {'exceptions': None}, {'exceptions': ()},
    {'exceptions': [True]}, {'exceptions': ['private-type']}, {'exceptions': ['argument'] * 9},
    {'exceptions': []}, {'exceptions': ['argument'] * 7, 'chain_end': 'truncated'},
    {'chain_end': None}, {'chain_end': 'private-end'}, {'category': 5}, {'category': 'private-category'},
    {'raw': 'private-path'},
])
def test_conversion_payload_refuses_unknown_or_inconsistent_data_before_eof(changes):
    attempt = conversion_attempt(conversion_frame(**changes))
    attempt.pipe.finish = lambda *_: pytest.fail('Invalid context cannot reach EOF admission')
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert attempt.conversion_failure_value == [None]
    assert 'private-' not in json.dumps(attempt.checkpoint)


def test_conversion_unknown_complete_and_truncated_are_bounded_distinct_states():
    for line in ('null', 'empty', 'nonempty'):
        for category in module.CONVERSION_CATEGORIES:
            value = {k: v for k, v in conversion_frame(line=line, category=category).items() if k != 'kind'}
            assert module.conversion_failure(value) == value
    for families, ending in (([], 'unknown'), (list(module.CONVERSION_FAMILIES), 'complete'),
            (['unknown'] * 8, 'truncated'), (['unknown'] * 8, 'unknown')):
        value = {k: v for k, v in conversion_frame(exceptions=families, chain_end=ending).items() if k != 'kind'}
        assert module.conversion_failure(value) == value
    maximum = conversion_frame(exceptions=['type-initialization'] * 8,
        chain_end='truncated', category='ResourceUnavailable')
    wire = lambda value: (json.dumps(value, separators=(',', ':')) + '\n').encode('ascii')
    assert len(wire(maximum)) == 302
    assert sum(len(wire(frame)) for frame in ({'kind': 'checkpoint', 'stage': 'connected'},
        {'kind': 'checkpoint', 'stage': 'grantread'}, maximum)) == 386 < module.LIMIT


@pytest.mark.parametrize(('key', 'value'), [('phase', 'post-loss'),
    ('observed', ['writable-open']), ('timestamp_equalities', {'arm': dict.fromkeys(
        ('creation_equal', 'access_equal', 'write_equal', 'change_equal'), True)}),
    ('legacy_source_sha256', None), ('failure', 'unexpected-failure'),
    ('cleanup', 'owned-handles-closed-fixture-retained'),
    ('baseline_checkpoint', {'parent_step': 'receive-result', 'script_step': 'grantread', 'child_state': 'unavailable'}),
    ('baseline_checkpoint', {'parent_step': 'receive-script-progress', 'script_step': 'grantparsed', 'child_state': 'unavailable'})])
def test_public_conversion_context_requires_failed_baseline_grantread_relation(key, value):
    result = conversion_receipt(); result[key] = value
    with pytest.raises(module.Refused): module.public_receipt(result)


def test_otherwise_complete_positive_mechanism_requires_no_conversion_failure():
    value = successful_receipt()
    assert module.public_receipt(value)['grant_conversion_failure'] is None
    value['grant_conversion_failure'] = conversion_receipt()['grant_conversion_failure']
    with pytest.raises(module.Refused): module.public_receipt(value)


def test_confirmed_conversion_context_does_not_override_cleanup_uncertainty(authored, monkeypatch):
    calls = []
    payload = {k: v for k, v in conversion_frame().items() if k != 'kind'}
    def baseline(_api, _root, _source, _expected, *, checkpoint_value=None, conversion_failure_value=None):
        checkpoint_value.update(parent_step='receive-script-progress', script_step='grantread', child_state='unavailable')
        conversion_failure_value[0] = payload
        calls.append('baseline-refused')
        raise module.Refused('owned-cleanup-unconfirmed')
    monkeypatch.setattr(module, 'legacy', baseline)
    result = module.experiment()
    assert calls == ['baseline-refused'] and 'owned-lease-start' not in authored.events
    assert result['failure'] == 'owned-cleanup-unconfirmed' and result['status'] == 'failed'
    assert result['grant_conversion_failure'] == payload
    assert result['cleanup'] == 'unconfirmed-fixture-retained' and result['observed'] == []


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_legacy_conversion_refusal_still_runs_owned_finally_once(monkeypatch, tmp_path, cleanup_fails):
    primary, cleanup = module.Refused('protocol-refused'), module.Refused('owned-cleanup-unconfirmed')
    calls, holder = [], [None]
    payload = {k: v for k, v in conversion_frame().items() if k != 'kind'}
    class Attempt:
        def __init__(self, *args, checkpoint_value=None, conversion_failure_value=None):
            assert conversion_failure_value is holder
            self.checkpoint_locked = False
        def script_exchange(self, value):
            holder[0] = payload
            raise primary
        def close(self):
            calls.append('close')
            if cleanup_fails: raise cleanup
    monkeypatch.setattr(module, 'Attempt', Attempt)
    monkeypatch.setattr(module, 'source_bytes', lambda *_: next(iter(module.SOURCE_HASHES)))
    api = SimpleNamespace(powershell=lambda: 'authored-program')
    with pytest.raises(module.Refused) as caught:
        module.legacy(api, tmp_path, 'authored-digest', 'open',
            checkpoint_value=module.checkpoint(), conversion_failure_value=holder)
    assert caught.value is (cleanup if cleanup_fails else primary)
    assert calls == ['close'] and holder == [payload]


def authored_engine_failure_context(code, stderr):
    labels = {0: 'zero-exit', 31: 'no-finally-or-caught', 33: 'exception-identity'}
    return {'exit': labels.get(code, 'unknown') if type(code) is int else 'unknown',
        'stderr_present': bool(stderr)}


@pytest.mark.parametrize(('code', 'label'), [(0, 'zero-exit'), (31, 'no-finally-or-caught'),
    (32, 'unknown'), (33, 'exception-identity'), (-1, 'unknown'), (123456, 'unknown'),
    (None, 'unknown'), (False, 'unknown'), ('private-exit-value', 'unknown')])
def test_authored_engine_failure_context_never_echoes_private_or_unknown_process_data(code, label):
    for stderr, present in ((b'', False), (b'private-stderr-path-message-trace', True)):
        value = authored_engine_failure_context(code, stderr)
        assert value == {'exit': label, 'stderr_present': present}
        assert 'private-' not in json.dumps(value)


def authored_rethrow_comparison(output, *, success=False, writer_fails=True):
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('Duplicate authored observation key')
            value[key] = item
        return value
    try:
        if type(output) is not bytes or type(success) is not bool or type(writer_fails) is not bool:
            return 'unavailable'
        lines = output.splitlines()
        if len(lines) != (1 if not success else 2 if writer_fails else 3): return 'unavailable'
        frame = json.loads(lines[0], object_pairs_hook=unique)
        keys = ('record_equal', 'exception_equal', 'category_equal', 'identifier_equal', 'finally_observed')
        if (type(frame) is not dict or set(frame) != {'kind', 'baseline', 'instrumented'}
                or type(frame['kind']) is not str or frame['kind'] != 'authored-rethrow-comparison'):
            return 'unavailable'
        for variant in ('baseline', 'instrumented'):
            item = frame[variant]
            if type(item) is not dict or set(item) != set(keys) or any(type(item[key]) is not bool for key in keys):
                return 'unavailable'
        if success:
            if lines[1] != b'owned-catch-ok': return 'unavailable'
            if not writer_fails and json.loads(lines[2], object_pairs_hook=unique) != conversion_frame(exceptions=['argument']):
                return 'unavailable'
        return {variant: {key: frame[variant][key] for key in keys} for variant in ('baseline', 'instrumented')}
    except (ValueError, UnicodeError, TypeError):
        return 'unavailable'


def authored_comparison_frame():
    values = dict.fromkeys(('record_equal', 'exception_equal', 'category_equal', 'identifier_equal', 'finally_observed'), True)
    values['record_equal'] = False
    return {'kind': 'authored-rethrow-comparison', 'baseline': dict(values), 'instrumented': dict(values)}


def authored_rethrow_preserved(comparison):
    # Only the existing strict frame parser supplies this value. Wrapper identity
    # remains an observation; these four preservation predicates are per variant.
    if type(comparison) is not dict or set(comparison) != {'baseline', 'instrumented'}:
        return False
    fields = ('exception_equal', 'category_equal', 'identifier_equal', 'finally_observed')
    return all(type(comparison[variant]) is dict and all(comparison[variant].get(key) is True for key in fields)
        for variant in ('baseline', 'instrumented'))


@pytest.mark.parametrize('variant', ['baseline', 'instrumented'])
@pytest.mark.parametrize('field', ['exception_equal', 'category_equal', 'identifier_equal', 'finally_observed'])
def test_authored_rethrow_preservation_refuses_each_false_field_within_each_variant(variant, field):
    frame = authored_comparison_frame(); frame[variant][field] = False
    comparison = authored_rethrow_comparison(json.dumps(frame).encode('ascii'))
    assert comparison != 'unavailable' and not authored_rethrow_preserved(comparison)


@pytest.mark.parametrize('baseline_wrapper', [False, True])
@pytest.mark.parametrize('instrumented_wrapper', [False, True])
def test_authored_rethrow_preservation_accepts_either_wrapper_observation(baseline_wrapper, instrumented_wrapper):
    frame = authored_comparison_frame()
    frame['baseline']['record_equal'] = baseline_wrapper
    frame['instrumented']['record_equal'] = instrumented_wrapper
    comparison = authored_rethrow_comparison(json.dumps(frame).encode('ascii'))
    assert authored_rethrow_preserved(comparison)


def test_authored_rethrow_comparison_keeps_only_complete_typed_boolean_variants():
    frame = authored_comparison_frame()
    frame['instrumented']['category_equal'] = False
    raw = json.dumps(frame).encode('ascii')
    expected = {key: frame[key] for key in ('baseline', 'instrumented')}
    assert authored_rethrow_comparison(raw) == expected
    assert authored_rethrow_comparison(raw+b'\nowned-catch-ok\n', success=True) == expected
    tail = json.dumps(conversion_frame(exceptions=['argument'])).encode('ascii')
    assert authored_rethrow_comparison(raw+b'\nowned-catch-ok\n'+tail+b'\n', success=True, writer_fails=False) == expected


@pytest.mark.parametrize('mutation', ['absent', 'partial', 'duplicate-frame', 'duplicate-kind',
    'duplicate-nested', 'extra-key', 'missing-variant', 'missing-bool', 'numeric-bool',
    'private-value', 'private-kind', 'extra-variant', 'unknown-tail'])
def test_authored_rethrow_comparison_refuses_malformed_or_private_data_without_echo(mutation):
    frame = authored_comparison_frame()
    if mutation == 'extra-key': frame['raw'] = 'private-path-message'
    if mutation == 'missing-variant': frame.pop('baseline')
    if mutation == 'missing-bool': frame['instrumented'].pop('exception_equal')
    if mutation == 'numeric-bool': frame['baseline']['record_equal'] = 0
    if mutation == 'private-value': frame['baseline']['record_equal'] = 'private-id'
    if mutation == 'private-kind': frame['kind'] = 'private-type'
    if mutation == 'extra-variant': frame['private-variant'] = frame['baseline']
    raw = json.dumps(frame, separators=(',', ':')).encode('ascii')
    if mutation == 'absent': raw = b''
    if mutation == 'partial': raw = raw[:-1]
    if mutation == 'duplicate-frame': raw += b'\n'+raw
    if mutation == 'duplicate-kind': raw = raw.replace(b'{"kind":', b'{"kind":"private-type","kind":', 1)
    if mutation == 'duplicate-nested': raw = raw.replace(b'"record_equal":false', b'"record_equal":false,"record_equal":true', 1)
    if mutation == 'unknown-tail': raw += b'\nprivate-stdout-stderr-trace'
    assert authored_rethrow_comparison(raw) == 'unavailable'
    assert not authored_rethrow_preserved(authored_rethrow_comparison(raw))


@pytest.mark.skipif(sys.platform != 'win32', reason='Authored Windows PowerShell engine semantics unavailable locally')
@pytest.mark.parametrize('writer_fails', [False, True])
def test_authored_powershell_preserves_original_error_context_when_diagnostic_writer_fails(writer_fails):
    # Exact producer fragments; no C7 fixture, legacy source, OS APIs or process helper.
    root = os.environ.get('SystemRoot')
    if not root or not Path(root).is_absolute(): pytest.fail('Authored engine host unavailable')
    executable = Path(root) / 'System32/WindowsPowerShell/v1.0/powershell.exe'
    if not executable.is_file(): pytest.fail('Authored engine host unavailable')
    prefix = r'''
$ErrorActionPreference='Stop'
$line='authored-private-line'
function ConvertFrom-Json { throw $script:original }
'''
    fresh_error = r'''
$script:original=[Management.Automation.ErrorRecord]::new(
    [ArgumentException]::new('authored-private-error'),'authored-private-id',
    [Management.Automation.ErrorCategory]::InvalidArgument,$null)
'''
    baseline = r'''
$baselineInner=$null; $baselineCaught=$null; $baselineFinally=$false
try {
    try { $grant=$line|ConvertFrom-Json }
    catch {
        $baselineInner=$_
        try { } catch { }
        throw
    }
} catch { $baselineCaught=$_ } finally { $baselineFinally=$true }
$baselinePresent=($null -ne $baselineInner -and $null -ne $baselineCaught)
$baselineRecordEqual=($baselinePresent -and [Object]::ReferenceEquals($baselineCaught,$baselineInner))
$baselineExceptionEqual=($baselinePresent -and [Object]::ReferenceEquals($baselineCaught.Exception,$baselineInner.Exception))
$baselineCategoryEqual=($baselinePresent -and $baselineCaught.CategoryInfo.Category -eq $baselineInner.CategoryInfo.Category)
$baselineIdentifierEqual=($baselinePresent -and $baselineCaught.FullyQualifiedErrorId -ceq $baselineInner.FullyQualifiedErrorId)
$baselineFinallyObserved=[bool]$baselineFinally
'''
    instrumented = r'''
class C7AuthoredWriter {
    [bool]$Fail
    [string]$Frame=''
    [void]WriteLine([string]$value) {
        if ($this.Fail) { throw [InvalidOperationException]::new('authored-private-writer') }
        $this.Frame=$value
    }
}
$writer=[C7AuthoredWriter]::new()
$writer.Fail=__FAIL__
$caught=$null; $conversionError=$null; $finallyObserved=$false
'''.replace('__FAIL__', '$true' if writer_fails else '$false')
    script = prefix + fresh_error + baseline + instrumented + fresh_error + module.CONVERSION_PROJECTOR + '\ntry {\n' + module.CONVERSION_CALL + r'''
} catch { $caught=$_ } finally { $finallyObserved=$true }
$instrumentedPresent=($null -ne $conversionError -and $null -ne $caught)
$instrumentedRecordEqual=($instrumentedPresent -and [Object]::ReferenceEquals($caught,$conversionError))
$instrumentedExceptionEqual=($instrumentedPresent -and [Object]::ReferenceEquals($caught.Exception,$conversionError.Exception))
$instrumentedCategoryEqual=($instrumentedPresent -and $caught.CategoryInfo.Category -eq $conversionError.CategoryInfo.Category)
$instrumentedIdentifierEqual=($instrumentedPresent -and $caught.FullyQualifiedErrorId -ceq $conversionError.FullyQualifiedErrorId)
$instrumentedFinallyObserved=[bool]$finallyObserved
function Get-C7AuthoredComparison([bool]$RecordEqual,[bool]$ExceptionEqual,[bool]$CategoryEqual,[bool]$IdentifierEqual,[bool]$FinallyObserved) {
    return '{"record_equal":'+$RecordEqual.ToString().ToLowerInvariant()+
        ',"exception_equal":'+$ExceptionEqual.ToString().ToLowerInvariant()+
        ',"category_equal":'+$CategoryEqual.ToString().ToLowerInvariant()+
        ',"identifier_equal":'+$IdentifierEqual.ToString().ToLowerInvariant()+
        ',"finally_observed":'+$FinallyObserved.ToString().ToLowerInvariant()+'}'
}
[Console]::Out.WriteLine('{"kind":"authored-rethrow-comparison","baseline":'+
    (Get-C7AuthoredComparison $baselineRecordEqual $baselineExceptionEqual $baselineCategoryEqual $baselineIdentifierEqual $baselineFinallyObserved)+
    ',"instrumented":'+(Get-C7AuthoredComparison $instrumentedRecordEqual $instrumentedExceptionEqual $instrumentedCategoryEqual $instrumentedIdentifierEqual $instrumentedFinallyObserved)+'}')
if (-not $finallyObserved -or $null -eq $caught) { exit 31 }
if (-not [Object]::ReferenceEquals($caught.Exception,$conversionError.Exception)) { exit 33 }
[Console]::Out.WriteLine('owned-catch-ok')
if ($writer.Frame -cne '') { [Console]::Out.WriteLine($writer.Frame) }
'''
    import base64
    unavailable = False
    try:
        process = subprocess.Popen([str(executable), '-NoLogo', '-NoProfile', '-NonInteractive',
            '-EncodedCommand', base64.b64encode(script.encode('utf-16le')).decode('ascii')],
            stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        unavailable = True
    if unavailable: pytest.fail('Authored engine process could not start')
    captured, failed = {}, []
    def read(name, stream):
        try:
            captured[name] = stream.read(8193)
            if len(captured[name]) > 8192: process.kill()
        except BaseException: failed.append(True)
        finally:
            try: stream.close()
            except BaseException: failed.append(True)
    readers = [threading.Thread(target=read, args=(name, stream), daemon=True)
        for name, stream in (('out', process.stdout), ('err', process.stderr))]
    for reader in readers: reader.start()
    try:
        code = process.wait(timeout=10)
    except BaseException:
        failed.append(True); code = None
        for operation in (process.kill, lambda: process.wait(timeout=5)):
            try: operation()
            except BaseException: failed.append(True)
    finally:
        for reader in readers: reader.join(timeout=1)
    if failed or any(reader.is_alive() for reader in readers) or any(len(v) > 8192 for v in captured.values()):
        pytest.fail('Authored engine output boundary failed')
    comparison = authored_rethrow_comparison(captured.get('out', b''), success=code == 0, writer_fails=writer_fails)
    if code != 0 or captured.get('err'):
        context = authored_engine_failure_context(code, captured.get('err', b''))
        context['rethrow_comparison'] = comparison
        pytest.fail('Authored engine original-error/finally contract failed: ' + json.dumps(
            context, sort_keys=True, separators=(',', ':')))
    if comparison == 'unavailable': pytest.fail('Authored engine rethrow comparison unavailable')
    if not authored_rethrow_preserved(comparison):
        pytest.fail('Authored engine error-context preservation failed: ' + json.dumps(comparison, sort_keys=True, separators=(',', ':')))
    lines = captured.get('out', b'').splitlines()[1:]
    if not lines or lines[0] != b'owned-catch-ok' or len(lines) != (1 if writer_fails else 2):
        pytest.fail('Authored engine acknowledgement differs')
    if not writer_fails:
        try: value = json.loads(lines[1])
        except ValueError: pytest.fail('Authored engine context is malformed')
        assert value == conversion_frame(exceptions=['argument'])
    if b'authored-private-' in captured.get('out', b''): pytest.fail('Authored context exposed private data')


_UNCONFIRMED_REAL_CONTROLS = []  # Private process/pipe/thread records, never PID adoption/retry.


def closed_real_control_boundary(value):
    fallback = {'refusal': 'unavailable', 'stderr_prefix': 'unavailable', 'cleanup': 'unconfirmed'}
    if (type(value) is not dict or set(value) != set(fallback)
            or type(value['refusal']) is not str
            or value['refusal'] not in {'none', 'spawn-refused', 'reader-setup-refused',
                'wait-deadline', 'wait-refused', 'capture-refused', 'protocol-refused',
                'cleanup-unconfirmed', 'unavailable'}
            or type(value['stderr_prefix']) is not str
            or value['stderr_prefix'] not in {'empty', 'fixed-clixml-prefix', 'other', 'unavailable'}
            or type(value['cleanup']) is not str
            or value['cleanup'] not in {'child-exit-and-readers-finished', 'unconfirmed'}):
        return fallback
    return dict(value)


def closed_real_conversion_observation(value):
    fallback = {'state': 'unavailable', 'context': None, 'stderr_present': False}
    if type(value) is not dict:
        return fallback
    if type(value.get('stderr_present')) is bool:
        fallback['stderr_present'] = value['stderr_present']
    if (set(value) != {'state', 'context', 'stderr_present'} or type(value['state']) is not str
            or value['state'] not in {'parsed', 'shape-refused', 'conversion-refused', 'unavailable'}
            or type(value['stderr_present']) is not bool):
        return fallback
    context = None
    if value['context'] is not None:
        if value['state'] != 'conversion-refused': return fallback
        try: context = module.conversion_failure(value['context'])
        except module.Refused: return fallback
    return {'state': value['state'], 'context': context, 'stderr_present': value['stderr_present']}


def real_conversion_observation(code, output, stderr):
    fallback = {'state': 'unavailable', 'context': None, 'stderr_present': bool(stderr)}
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value: raise ValueError('Duplicate authored control key')
            value[key] = item
        return value
    try:
        if (type(code) is not int or code not in (0, 2) or type(output) is not bytes
                or type(stderr) is not bytes or len(output) > 8192 or len(stderr) > 8192):
            return fallback
        lines = output.splitlines()
        if not 1 <= len(lines) <= 2: return fallback
        frame = json.loads(lines[0], object_pairs_hook=unique)
        if (type(frame) is not dict or set(frame) != {'kind', 'state'}
                or frame['kind'] != 'authored-real-conversion-control'
                or type(frame['state']) is not str
                or frame['state'] not in {'parsed', 'shape-refused', 'conversion-refused'}
                or code != (0 if frame['state'] == 'parsed' else 2)):
            return fallback
        context = None
        if len(lines) == 2:
            if frame['state'] != 'conversion-refused': return fallback
            failure = json.loads(lines[1], object_pairs_hook=unique)
            if (type(failure) is not dict or set(failure) != {'kind', 'line', 'exceptions', 'chain_end', 'category'}
                    or failure['kind'] != 'grant-conversion-failure'):
                return fallback
            context = module.conversion_failure({k: v for k, v in failure.items() if k != 'kind'})
        return closed_real_conversion_observation({'state': frame['state'], 'context': context,
            'stderr_present': bool(stderr)})
    except (ValueError, UnicodeError, TypeError, module.Refused):
        return fallback


CONTROL_PROGRESS_STAGES = ('script-entry', 'before-conversion', 'after-conversion')
CONTROL_PROGRESS_LINES = tuple(
    ('{"kind":"authored-real-conversion-progress","stage":"'+stage+'"}').encode('ascii')
    for stage in CONTROL_PROGRESS_STAGES)
CONTROL_TERMINAL_LINES = {
    state: ('{"kind":"authored-real-conversion-control","state":"'+state+'"}').encode('ascii')
    for state in ('parsed', 'shape-refused', 'conversion-refused')}


def closed_real_control_progress(value):
    fallback = {'last_delivered': 'not-observed', 'protocol': 'not-observed'}
    if (type(value) is not dict or set(value) != {'last_delivered', 'protocol'}
            or type(value['last_delivered']) is not str
            or value['last_delivered'] not in ('not-observed', *CONTROL_PROGRESS_STAGES)
            or type(value['protocol']) is not str
            or value['protocol'] not in {'not-observed', 'ordered-prefix', 'malformed'}
            or value['protocol'] == 'not-observed' and value['last_delivered'] != 'not-observed'
            or value['protocol'] == 'ordered-prefix' and value['last_delivered'] == 'not-observed'):
        return fallback
    return dict(value)


def marked_real_conversion_observation(code, output, stderr):
    """Only exact delivered marker lines; no progress may substitute for a result."""
    unavailable = {'state': 'unavailable', 'context': None, 'stderr_present': bool(stderr)}
    progress = closed_real_control_progress(None)
    if type(output) is not bytes or len(output) > 8192:
        progress['protocol'] = 'malformed'
        return unavailable, progress
    if not output:
        return unavailable, progress
    pieces = output.split(b'\n')
    partial = bool(pieces[-1])
    complete = [line[:-1] if line.endswith(b'\r') else line for line in pieces[:-1]]
    count = 0
    while count < len(CONTROL_PROGRESS_LINES) and count < len(complete):
        if complete[count] != CONTROL_PROGRESS_LINES[count]:
            break
        progress.update(last_delivered=CONTROL_PROGRESS_STAGES[count], protocol='ordered-prefix')
        count += 1
    remaining = complete[count:]
    if partial or remaining and (count < 2 or len(remaining) > 2
            or remaining[0] not in CONTROL_TERMINAL_LINES.values()
            or count == 2 and remaining[0] != CONTROL_TERMINAL_LINES['conversion-refused']
            or any(line in CONTROL_PROGRESS_LINES for line in remaining[1:])):
        progress['protocol'] = 'malformed'
        return unavailable, progress
    if not remaining:
        return unavailable, progress
    observed = real_conversion_observation(code, b'\n'.join(pieces[count:]), stderr)
    if observed['state'] == 'unavailable' and type(code) is int and code in (0, 2):
        progress['protocol'] = 'malformed'
    return observed, progress


@pytest.mark.parametrize('ending', [b'\n', b'\r\n'])
@pytest.mark.parametrize('count', range(4))
def test_delivered_marker_prefix_without_terminal_never_establishes_parsing_success(ending, count):
    raw = ending.join(CONTROL_PROGRESS_LINES[:count])+(ending if count else b'')
    for code in (0, None, -9):
        observed, progress = marked_real_conversion_observation(code, raw, b'')
        assert observed == {'state': 'unavailable', 'context': None, 'stderr_present': False}
        assert progress == {'last_delivered': CONTROL_PROGRESS_STAGES[count-1] if count else 'not-observed',
            'protocol': 'ordered-prefix' if count else 'not-observed'}


@pytest.mark.parametrize('ending', [b'\n', b'\r\n'])
def test_ordered_complete_markers_preserve_original_terminal_and_conversion_context(ending):
    success = ending.join((*CONTROL_PROGRESS_LINES, CONTROL_TERMINAL_LINES['parsed'], b''))
    observed, progress = marked_real_conversion_observation(0, success, b'')
    assert observed == {'state': 'parsed', 'context': None, 'stderr_present': False}
    assert progress == {'last_delivered': 'after-conversion', 'protocol': 'ordered-prefix'}
    failure = conversion_frame()
    refused = ending.join((*CONTROL_PROGRESS_LINES[:2], CONTROL_TERMINAL_LINES['conversion-refused'],
        json.dumps(failure).encode('ascii'), b''))
    observed, progress = marked_real_conversion_observation(2, refused, b'')
    assert observed == {'state': 'conversion-refused',
        'context': {key: value for key, value in failure.items() if key != 'kind'}, 'stderr_present': False}
    assert progress == {'last_delivered': 'before-conversion', 'protocol': 'ordered-prefix'}
    assert marked_real_conversion_observation(0, success, b'private-stderr')[0]['stderr_present'] is True


@pytest.mark.parametrize('count', range(4))
@pytest.mark.parametrize('ending', [b'\n', b'\r\n'])
def test_partial_next_marker_or_terminal_retains_only_complete_delivered_prefix(count, ending):
    prefix = ending.join(CONTROL_PROGRESS_LINES[:count])+(ending if count else b'')
    next_line = CONTROL_PROGRESS_LINES[count] if count < 3 else CONTROL_TERMINAL_LINES['parsed']
    # Even a syntactically complete JSON object without the delivery delimiter
    # is incomplete stdout; a successful process code cannot promote it.
    observed, progress = marked_real_conversion_observation(0, prefix+next_line, b'')
    assert observed['state'] == 'unavailable'
    assert progress == {'last_delivered': CONTROL_PROGRESS_STAGES[count-1] if count else 'not-observed',
        'protocol': 'malformed'}


@pytest.mark.parametrize('mutation', ['reordered', 'duplicate', 'missing-first', 'unknown-stage',
    'extra-key', 'numeric-stage', 'duplicate-key', 'marker-whitespace', 'private-noise',
    'unknown-tail', 'trailing-marker', 'duplicate-terminal', 'duplicate-failure', 'bare-cr', 'over-cap'])
def test_malformed_marker_streams_cannot_hide_noise_or_bypass_original_hard_gate(mutation):
    lines = [*CONTROL_PROGRESS_LINES, CONTROL_TERMINAL_LINES['parsed']]
    if mutation == 'reordered': lines[1], lines[2] = lines[2], lines[1]
    if mutation == 'duplicate': lines.insert(1, lines[0])
    if mutation == 'missing-first': lines.pop(0)
    if mutation == 'unknown-stage': lines[1] = b'{"kind":"authored-real-conversion-progress","stage":"private-stage"}'
    if mutation == 'extra-key': lines[1] = b'{"kind":"authored-real-conversion-progress","stage":"before-conversion","raw":"private-path"}'
    if mutation == 'numeric-stage': lines[1] = b'{"kind":"authored-real-conversion-progress","stage":4}'
    if mutation == 'duplicate-key': lines[1] = b'{"kind":"authored-real-conversion-progress","stage":"before-conversion","stage":"after-conversion"}'
    if mutation == 'marker-whitespace': lines[1] = b' '+lines[1]
    if mutation == 'private-noise': lines.insert(1, b'private-path-error-text')
    if mutation == 'unknown-tail': lines.append(b'private-unknown-tail')
    if mutation == 'trailing-marker': lines.append(CONTROL_PROGRESS_LINES[-1])
    if mutation == 'duplicate-terminal': lines.append(CONTROL_TERMINAL_LINES['parsed'])
    if mutation == 'duplicate-failure':
        lines = [*CONTROL_PROGRESS_LINES[:2], CONTROL_TERMINAL_LINES['conversion-refused'],
            json.dumps(conversion_frame()).encode('ascii'), json.dumps(conversion_frame()).encode('ascii')]
    raw = b'\n'.join((*lines, b''))
    if mutation == 'bare-cr': raw = b'\r'.join((*lines, b''))
    if mutation == 'over-cap': raw += b'private-'+b'x'*8192
    observed, progress = marked_real_conversion_observation(2 if mutation == 'duplicate-failure' else 0, raw, b'')
    assert observed == {'state': 'unavailable', 'context': None, 'stderr_present': False}
    assert progress['protocol'] == 'malformed'
    assert progress['last_delivered'] in ('not-observed', *CONTROL_PROGRESS_STAGES)
    assert 'private' not in json.dumps((observed, progress))


@pytest.mark.parametrize('value', [None, {}, 'private-progress',
    {'last_delivered': 'private-stage', 'protocol': 'ordered-prefix'},
    {'last_delivered': 'after-conversion', 'protocol': 'private-status'},
    {'last_delivered': 'after-conversion', 'protocol': 'not-observed'},
    {'last_delivered': 'not-observed', 'protocol': 'ordered-prefix'},
    {'last_delivered': 'after-conversion', 'protocol': 'ordered-prefix', 'raw': 'private-path'}])
def test_progress_projection_is_closed_and_never_echoes_private_or_inconsistent_metadata(value):
    assert closed_real_control_progress(value) == {'last_delivered': 'not-observed', 'protocol': 'not-observed'}


def run_real_conversion_control(executable, script, environment, *, diagnostic=None, progress=None):
    import base64
    unavailable = {'state': 'unavailable', 'context': None, 'stderr_present': False}
    boundary = {'refusal': 'none', 'stderr_prefix': 'unavailable', 'cleanup': 'unconfirmed'}
    def publish_boundary():
        if diagnostic is not None:
            diagnostic.clear()
            diagnostic.update(closed_real_control_boundary(boundary))
    if progress is not None:
        progress.clear()
        progress.update(closed_real_control_progress(None))
    try:
        process = subprocess.Popen([executable, '-NoProfile', '-NonInteractive', '-EncodedCommand',
            base64.b64encode(script.encode('utf-16le')).decode('ascii')],
            env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW)
    except OSError:
        boundary['refusal'] = 'spawn-refused'
        publish_boundary()
        return unavailable
    captured, failed, uncertain = {}, [], []
    def read(name, stream):
        try:
            captured[name] = stream.read(8193)
            if len(captured[name]) > 8192:
                failed.append(True)
                if boundary['refusal'] == 'none': boundary['refusal'] = 'capture-refused'
                try: process.kill()
                except BaseException: uncertain.append(True)
        except BaseException:
            failed.append(True)
            if boundary['refusal'] == 'none': boundary['refusal'] = 'capture-refused'
        finally:
            try: stream.close()
            except BaseException: uncertain.append(True)
    readers, exited, code = [], False, None
    try:
        boundary['refusal'] = 'reader-setup-refused'
        readers = [{'thread': threading.Thread(target=read, args=(name, stream), daemon=True),
                    'stream': stream, 'attempted': False, 'started': False}
            for name, stream in (('out', process.stdout), ('err', process.stderr))]
        for record in readers:
            record['attempted'] = True
            try: record['thread'].start()
            except BaseException:
                uncertain.append(True)
                raise
            record['started'] = True
        boundary['refusal'] = 'none'
        try:
            code = process.wait(timeout=10); exited = True
        except subprocess.TimeoutExpired:
            boundary['refusal'] = 'wait-deadline'
            raise
        except BaseException:
            boundary['refusal'] = 'wait-refused'
            raise
    except BaseException:
        failed.append(True)
    finally:
        if not exited:
            try: process.kill()
            except BaseException: uncertain.append(True)
            try: code = process.wait(timeout=5); exited = True
            except BaseException: uncertain.append(True)
        if not readers:
            # Construction failed before either start: these pipes have no reader owner.
            for stream in (process.stdout, process.stderr):
                try: stream.close()
                except BaseException: uncertain.append(True)
        for record in readers:
            if record['started']:
                try: record['thread'].join(timeout=1)
                except BaseException: uncertain.append(True)
                try:
                    if record['thread'].is_alive(): uncertain.append(True)
                except BaseException: uncertain.append(True)
            elif not record['attempted']:
                try: record['stream'].close()
                except BaseException: uncertain.append(True)
            # An unconfirmed start may already be running. Never race or retry its close.
    if not exited or uncertain:
        _UNCONFIRMED_REAL_CONTROLS.append({'process': process, 'readers': readers})
        boundary['refusal'] = 'cleanup-unconfirmed'
    else:
        boundary['cleanup'] = 'child-exit-and-readers-finished'
    if 'err' in captured:
        raw = captured['err']
        boundary['stderr_prefix'] = ('empty' if not raw else
            'fixed-clixml-prefix' if raw.startswith(b'#< CLIXML') else 'other')
    if progress is not None:
        marked, delivered = marked_real_conversion_observation(
            code, captured.get('out', b''), captured.get('err', b''))
        progress.clear()
        progress.update(closed_real_control_progress(delivered))
    if failed or uncertain or not exited or any(len(value) > 8192 for value in captured.values()):
        if boundary['refusal'] == 'none': boundary['refusal'] = 'capture-refused'
        publish_boundary()
        unavailable['stderr_present'] = bool(captured.get('err'))
        return unavailable
    observed = (real_conversion_observation(code, captured.get('out', b''), captured.get('err', b''))
        if progress is None else marked)
    if observed['state'] == 'unavailable': boundary['refusal'] = 'protocol-refused'
    publish_boundary()
    return observed


def test_timeout_progress_keeps_only_delivered_marker_without_new_capture_or_wait_budget(monkeypatch):
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    calls, processes = [], []
    partial = b'\n'.join((*CONTROL_PROGRESS_LINES[:2], CONTROL_PROGRESS_LINES[2][:-4]))
    class Process:
        def __init__(self, *_args, **_options):
            self.stdout, self.stderr = io.BytesIO(partial), io.BytesIO(b'')
            processes.append(self)
        def wait(self, timeout):
            calls.append(('wait', timeout))
            if timeout == 10: raise subprocess.TimeoutExpired('authored-child', timeout)
            assert timeout == 5
            return -9
        def kill(self): calls.append(('kill',))
    monkeypatch.setattr(subprocess, 'Popen', Process)
    progress, boundary = {}, {}
    count = len(_UNCONFIRMED_REAL_CONTROLS)
    observed = run_real_conversion_control('authored-program', 'authored-source', {},
        diagnostic=boundary, progress=progress)
    assert observed == {'state': 'unavailable', 'context': None, 'stderr_present': False}
    assert progress == {'last_delivered': 'before-conversion', 'protocol': 'malformed'}
    assert boundary == {'refusal': 'wait-deadline', 'stderr_prefix': 'empty',
        'cleanup': 'child-exit-and-readers-finished'}
    assert calls == [('wait', 10), ('kill',), ('wait', 5)]
    assert len(processes) == 1 and processes[0].stdout.closed and processes[0].stderr.closed
    assert len(_UNCONFIRMED_REAL_CONTROLS) == count


def real_conversion_pair(parent_environment, run):
    # Collect both fresh children before the caller may assert a joint outcome.
    inherited_environment = dict(parent_environment)
    attempt_environment = module.legacy_environment(inherited_environment)
    result = {}
    for variant, environment in (('inherited', inherited_environment), ('attempt', attempt_environment)):
        try: observed = run(environment)
        except Exception: observed = None
        result[variant] = closed_real_conversion_observation(observed)
    return result


def real_conversion_system_environments(parent_environment, executable):
    # The caller obtains this exact image from Windows.powershell(), not PATH.
    # These three fresh controls do not change the actual Attempt environment.
    if executable is None:
        return {}
    image = PureWindowsPath(executable)
    if (not image.is_absolute() or len(image.drive) != 2 or '..' in image.parts
            or tuple(part.casefold() for part in image.parts[-3:]) !=
                ('windowspowershell', 'v1.0', 'powershell.exe')
            or image.parents[2].name.casefold() != 'system32'):
        raise ValueError('Protected Windows PowerShell system search inputs unavailable.')
    folder, system = image.parent, image.parents[2]
    values = {
        'system-path': {'PATH': ';'.join((str(system), str(folder)))},
        'system-modules': {'PSModulePath': str(folder / 'Modules')},
    }
    values['system-path-and-modules'] = {**values['system-path'], **values['system-modules']}
    baseline = module.legacy_environment(parent_environment)
    return {name: {**baseline, **overrides} for name, overrides in values.items()}


def test_system_search_controls_use_only_protected_image_paths_and_independent_filtered_snapshots():
    parent = {'SystemRoot': 'authored-system', 'TEMP': 'authored-temp',
        'PATH': 'private-tools', 'PSModulePath': 'private-modules', 'PRIVATE_KEY': 'private-value'}
    original = dict(parent)
    controls = real_conversion_system_environments(parent,
        r'S:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe')
    baseline = {'SystemRoot': 'authored-system', 'TEMP': 'authored-temp'}
    paths = {'PATH': r'S:\Windows\System32;S:\Windows\System32\WindowsPowerShell\v1.0'}
    modules = {'PSModulePath': r'S:\Windows\System32\WindowsPowerShell\v1.0\Modules'}
    assert controls == {'system-path': {**baseline, **paths},
        'system-modules': {**baseline, **modules}, 'system-path-and-modules': {**baseline, **paths, **modules}}
    assert parent == original and 'private-' not in json.dumps(controls)
    controls['system-path']['TEMP'] = 'changed-authored-value'
    assert controls['system-modules']['TEMP'] == controls['system-path-and-modules']['TEMP'] == parent['TEMP']


@pytest.mark.parametrize('executable', ['powershell.exe', r'S:\tools\pwsh.exe',
    r'S:\Windows\System32\..\System32\WindowsPowerShell\v1.0\powershell.exe'])
def test_system_search_controls_refuse_noncanonical_image_shapes_without_exposing_input(executable):
    with pytest.raises(ValueError, match='^Protected Windows PowerShell system search inputs unavailable\\.$'):
        real_conversion_system_environments({}, executable)
    assert real_conversion_system_environments({}, None) == {}


@pytest.mark.parametrize('refusal', ['none', 'attempt', 'attempt-stderr', 'extra-cleanup', 'writer-cleanup', 'writer-runner'])
def test_seven_control_decision_preserves_actual_pair_and_refuses_uncertain_extra_cleanup(monkeypatch, refusal):
    image = r'S:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    monkeypatch.setattr(module, 'Windows', lambda: SimpleNamespace(powershell=lambda: image))
    monkeypatch.setattr(sys.modules[__name__], 'os', SimpleNamespace(environ={
        'SystemRoot': 'authored-system', 'PRIVATE_KEY': 'private-parent-value'}))
    calls, scripts = [], []
    def run(executable, script, environment, *, diagnostic, progress):
        assert executable == image
        calls.append(dict(environment))
        scripts.append(script)
        if refusal == 'writer-runner' and len(calls) == 6:
            raise OSError('private-new-writer-refusal')
        diagnostic.update(refusal='none', stderr_prefix='empty', cleanup='child-exit-and-readers-finished')
        progress.update(last_delivered='after-conversion', protocol='ordered-prefix')
        if (refusal == 'extra-cleanup' and len(calls) == 5
                or refusal == 'writer-cleanup' and len(calls) == 7):
            diagnostic['cleanup'] = 'unconfirmed'
        state = ('unavailable' if len(calls) > 2 and refusal not in {'attempt', 'attempt-stderr'}
            or refusal == 'attempt' and len(calls) == 2 else 'parsed')
        return {'state': state, 'context': None,
            'stderr_present': refusal == 'attempt-stderr' and len(calls) == 2}
    monkeypatch.setattr(sys.modules[__name__], 'run_real_conversion_control', run)
    if refusal == 'none':
        test_authored_real_conversion_under_inherited_and_attempt_environment()
    else:
        with pytest.raises(pytest.fail.Exception) as failed:
            test_authored_real_conversion_under_inherited_and_attempt_environment()
        assert 'private-' not in str(failed.value) and image not in str(failed.value)
    assert len(calls) == 7
    assert all(script is scripts[0] for script in scripts[:5])
    assert scripts[5] is scripts[6] and scripts[5] != scripts[0]
    assert calls[5] == calls[0] and calls[6] == calls[1]
    assert 'PRIVATE_KEY' in calls[0] and 'PRIVATE_KEY' in calls[5]
    assert all('PRIVATE_KEY' not in calls[index] for index in (1, 2, 3, 4, 6))


def test_real_conversion_pair_measures_both_sets_before_joint_refusal_without_mutating_parent():
    parent = {'SystemRoot': 'authored-root', 'WINDIR': 'authored-windows', 'TEMP': 'authored-temp',
        'tMp': 'authored-tmp', 'LOCALAPPDATA': 'authored-cache', 'ProgramFiles': 'authored-programs',
        'PRIVATE_PROFILE': 'private-path'}
    original = dict(parent); calls = []
    def run(environment):
        calls.append(environment)
        if len(calls) == 1: raise OSError('private-startup-error')
        return {'state': 'parsed', 'context': None, 'stderr_present': False}
    result = real_conversion_pair(parent, run)
    assert len(calls) == 2 and calls[0] == original and calls[0] is not parent
    assert calls[1] == {k: original[k] for k in ('SystemRoot', 'WINDIR', 'TEMP', 'tMp', 'LOCALAPPDATA', 'ProgramFiles')}
    assert parent == original
    assert result['inherited'] == {'state': 'unavailable', 'context': None, 'stderr_present': False}
    assert result['attempt']['state'] == 'parsed' and 'private-' not in json.dumps(result)


@pytest.mark.parametrize(('state', 'code'), [('parsed', 0), ('shape-refused', 2), ('conversion-refused', 2)])
def test_real_conversion_control_accepts_only_matching_typed_terminal_states(state, code):
    raw = json.dumps({'kind': 'authored-real-conversion-control', 'state': state}).encode('ascii')
    assert real_conversion_observation(code, raw, b'') == {'state': state, 'context': None, 'stderr_present': False}
    assert real_conversion_observation(2 if code == 0 else 0, raw, b'')['state'] == 'unavailable'


def test_real_conversion_control_keeps_only_existing_bounded_failure_context():
    first = json.dumps({'kind': 'authored-real-conversion-control', 'state': 'conversion-refused'}).encode('ascii')
    failure = conversion_frame(exceptions=['unknown'] * 8, chain_end='truncated', category='unknown')
    result = real_conversion_observation(2, first+b'\n'+json.dumps(failure).encode('ascii'), b'private-stderr')
    assert result == {'state': 'conversion-refused',
        'context': {k: v for k, v in failure.items() if k != 'kind'}, 'stderr_present': True}
    assert 'private-' not in json.dumps(result)


@pytest.mark.parametrize('mutation', ['absent', 'partial', 'duplicate-frame', 'duplicate-key', 'extra-key',
    'private-state', 'private-context', 'unknown-kind', 'private-tail', 'numeric-state', 'wrong-code',
    'extra-context', 'too-deep', 'oversized'])
def test_real_conversion_control_refuses_malformed_or_private_output_without_echo(mutation):
    frame = {'kind': 'authored-real-conversion-control', 'state': 'conversion-refused'}
    code, failure = 2, conversion_frame()
    if mutation == 'extra-key': frame['raw'] = 'private-path'
    if mutation == 'private-state': frame['state'] = 'private-command'
    if mutation == 'unknown-kind': frame['kind'] = 'private-type'
    if mutation == 'numeric-state': frame['state'] = 1
    if mutation == 'wrong-code': code = 123456
    if mutation == 'private-context': failure['exceptions'] = ['private-error']
    if mutation == 'extra-context': failure['raw'] = 'private-message'
    if mutation == 'too-deep': failure['exceptions'] = ['argument'] * 9
    raw = json.dumps(frame, separators=(',', ':')).encode('ascii')
    if mutation in {'private-context', 'extra-context', 'too-deep'}: raw += b'\n'+json.dumps(failure).encode('ascii')
    if mutation == 'absent': raw = b''
    if mutation == 'partial': raw = raw[:-1]
    if mutation == 'duplicate-frame': raw += b'\n'+raw
    if mutation == 'duplicate-key': raw = raw.replace(b'"state":', b'"state":"private-command","state":', 1)
    if mutation == 'private-tail': raw += b'\nprivate-stdout'
    if mutation == 'oversized': raw = b'private-output' * 1000
    result = real_conversion_observation(code, raw, b'private-stderr')
    assert result == {'state': 'unavailable', 'context': None, 'stderr_present': True}


def test_real_conversion_pair_reprojects_runner_failures_before_any_public_diagnostic():
    result = real_conversion_pair({}, lambda _: {'state': 'private-path', 'context': 'private-value',
        'stderr_present': True, 'raw': 'private-error'})
    assert set(result) == {'inherited', 'attempt'}
    assert all(value == {'state': 'unavailable', 'context': None, 'stderr_present': True} for value in result.values())


def test_legacy_environment_keeps_only_standard_windows_runtime_values_without_mutating_parent():
    parent = {name.upper(): 'authored-'+name for name in module.LEGACY_ENV_NAMES}
    rejected = {'PATH', 'PSModulePath', 'PSMODULEANALYSISCACHEPATH', 'NODE_PATH', 'NODE_OPTIONS',
        'PYTHONHOME', 'PYTHONPATH', 'DOTNET_ROOT', 'VSINSTALLDIR', 'VCINSTALLDIR', 'PRIVATE_PROFILE'}
    parent.update({name: 'private-developer-value' for name in rejected})
    before = dict(parent)
    observed = module.legacy_environment(parent)
    assert set(observed) == {name.upper() for name in module.LEGACY_ENV_NAMES}
    assert all(observed[name] == before[name] for name in observed)
    assert parent == before and not set(observed) & rejected
    assert 'private-' not in json.dumps(observed)


def test_actual_owned_attempt_passes_the_filtered_windows_runtime_snapshot_before_resume(monkeypatch):
    from types import SimpleNamespace
    parent = {'SystemRoot': 'authored-system', 'LOCALAPPDATA': 'authored-cache',
        'ProgramFiles': 'authored-programs', 'PSModulePath': 'private-modules',
        'PATH': 'private-tools', 'PYTHONHOME': 'private-python'}
    before, calls = dict(parent), []
    child = SimpleNamespace(resume_once=lambda: calls.append('resume'))
    class Owner:
        def create_suspended(self, command, *, cwd, env):
            calls.append(('create', command, cwd, dict(env)))
            return child
    class Pipe:
        def __init__(self, _api): self.name = 'authored-pipe'
        def bind(self, owned, _deadline):
            assert owned is child
            calls.append('bind')
    monkeypatch.setattr(module.os, 'environ', parent)
    monkeypatch.setattr(module, 'Pipe', Pipe)
    monkeypatch.setattr(module, 'process_module', lambda: SimpleNamespace(WindowsPreparationProcess=Owner))
    attempt = module.Attempt(object(), lambda name: ['authored-program', name], 'authored-cwd')
    assert attempt.child is child and parent == before
    assert calls == [('create', ['authored-program', 'authored-pipe'], 'authored-cwd',
        {'SystemRoot': 'authored-system', 'LOCALAPPDATA': 'authored-cache', 'ProgramFiles': 'authored-programs'}),
        'resume', 'bind']


@pytest.mark.parametrize('fault', ['start-first', 'start-second', 'stream-close', 'timeout',
    'kill', 'cleanup-wait', 'read', 'read-budget'])
def test_real_conversion_runner_bounds_faults_and_retains_uncertain_ownership(monkeypatch, fault):
    retained, processes, calls = [], [], []
    monkeypatch.setitem(globals(), '_UNCONFIRMED_REAL_CONTROLS', retained)
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    class Output(io.BytesIO):
        def __init__(self, raw, name):
            super().__init__(raw); self.name, self.close_attempts = name, 0
        def read(self, size):
            assert size == 8193
            if fault == 'read' and self.name == 'out': raise OSError('private-read-error')
            return super().read(size)
        def close(self):
            self.close_attempts += 1
            if fault == 'stream-close' and self.name == 'out': raise OSError('private-close-error')
            super().close()
    class Process:
        def __init__(self, command, **options):
            self.stdout = Output(b'x' * 8193 if fault == 'read-budget' else json.dumps(
                {'kind': 'authored-real-conversion-control', 'state': 'parsed'}).encode('ascii'), 'out')
            self.stderr = Output(b'', 'err'); self.waits = 0
            processes.append(self)
        def wait(self, timeout):
            calls.append(('wait', timeout)); self.waits += 1
            if fault in {'timeout', 'kill', 'cleanup-wait'} and self.waits == 1:
                raise subprocess.TimeoutExpired('private-program', timeout)
            if fault == 'cleanup-wait': raise OSError('private-wait-error')
            return 0
        def kill(self):
            calls.append(('kill',))
            if fault == 'kill': raise OSError('private-kill-error')
    monkeypatch.setattr(subprocess, 'Popen', Process)
    if fault.startswith('start-'):
        ordinary = threading.Thread; created = []
        def thread(*args, **kwargs):
            value = ordinary(*args, **kwargs); created.append(value)
            if len(created) == (1 if fault == 'start-first' else 2):
                def refuse(): raise OSError('private-thread-start-error')
                value.start = refuse
            return value
        monkeypatch.setattr(threading, 'Thread', thread)
    diagnostic = {}
    result = run_real_conversion_control('authored-program', 'authored-source', {}, diagnostic=diagnostic)
    assert result == {'state': 'unavailable', 'context': None, 'stderr_present': False}
    assert len(processes) == 1
    if fault in {'start-first', 'start-second', 'stream-close', 'kill', 'cleanup-wait'}:
        assert retained and retained[0]['process'] is processes[0]
        assert retained[0]['readers']
    else:
        assert not retained
    expected_refusal = ('cleanup-unconfirmed' if retained else
        'wait-deadline' if fault == 'timeout' else 'capture-refused')
    assert diagnostic['refusal'] == expected_refusal
    assert diagnostic['cleanup'] == ('unconfirmed' if retained else 'child-exit-and-readers-finished')
    assert closed_real_control_boundary(diagnostic) == diagnostic
    if fault == 'stream-close': assert processes[0].stdout.close_attempts == 1
    if fault in {'start-first', 'start-second', 'timeout', 'kill', 'cleanup-wait'}:
        assert ('kill',) in calls and ('wait', 5) in calls
    assert 'private-' not in json.dumps(result)
    # Release only the authored in-memory streams after the ownership assertions.
    for stream in (processes[0].stdout, processes[0].stderr): io.BytesIO.close(stream)


@pytest.mark.parametrize('mutation', ['extra-key', 'private-refusal', 'private-prefix',
    'private-cleanup', 'numeric-refusal', 'wrong-type', 'absent'])
def test_real_control_boundary_refuses_private_or_malformed_metadata(mutation):
    value = {'refusal': 'none', 'stderr_prefix': 'empty', 'cleanup': 'child-exit-and-readers-finished'}
    if mutation == 'extra-key': value['raw'] = 'private-path'
    if mutation == 'private-refusal': value['refusal'] = 'private-error'
    if mutation == 'private-prefix': value['stderr_prefix'] = 'private-message'
    if mutation == 'private-cleanup': value['cleanup'] = 'private-process'
    if mutation == 'numeric-refusal': value['refusal'] = 42
    if mutation == 'wrong-type': value = 'private-value'
    if mutation == 'absent': value = None
    result = closed_real_control_boundary(value)
    assert result == {'refusal': 'unavailable', 'stderr_prefix': 'unavailable', 'cleanup': 'unconfirmed'}
    assert 'private-' not in json.dumps(result)


@pytest.mark.parametrize(('stderr', 'prefix'), [(b'', 'empty'),
    (b'#< CLIXML\r\nprivate-error-or-progress', 'fixed-clixml-prefix'),
    (b'private-stderr', 'other')])
def test_real_control_parent_boundary_observes_prefix_without_classifying_or_accepting_stderr(monkeypatch, stderr, prefix):
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    class Process:
        def __init__(self, *_args, **_kwargs):
            self.stdout = io.BytesIO(b'{"kind":"authored-real-conversion-control","state":"parsed"}')
            self.stderr = io.BytesIO(stderr)
        def wait(self, timeout):
            assert timeout == 10
            return 0
        def kill(self): pytest.fail('A completed authored child must not be killed.')
    monkeypatch.setattr(subprocess, 'Popen', Process)
    diagnostic = {}
    result = run_real_conversion_control('authored-program', 'authored-source', {}, diagnostic=diagnostic)
    assert diagnostic == {'refusal': 'none', 'stderr_prefix': prefix, 'cleanup': 'child-exit-and-readers-finished'}
    assert result == {'state': 'parsed', 'context': None, 'stderr_present': bool(stderr)}
    # The unchanged paired acceptance still refuses any stderr bytes. A prefix
    # observation cannot classify messages or change that predicate.
    assert (result == {'state': 'parsed', 'context': None, 'stderr_present': False}) == (not stderr)
    assert 'private-' not in json.dumps(diagnostic)


def test_real_control_spawn_refusal_has_only_fixed_parent_metadata(monkeypatch):
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    def refuse(*_args, **_kwargs): raise OSError('private-program-and-path')
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    diagnostic = {}
    result = run_real_conversion_control('authored-program', 'authored-source', {}, diagnostic=diagnostic)
    assert result == {'state': 'unavailable', 'context': None, 'stderr_present': False}
    assert diagnostic == {'refusal': 'spawn-refused', 'stderr_prefix': 'unavailable', 'cleanup': 'unconfirmed'}
    assert 'private-' not in json.dumps(diagnostic)


def real_conversion_literal_script(writer_kind):
    if writer_kind not in {'authored-class', 'string-writer'}:
        raise ValueError('Authored literal writer control unavailable.')
    markers = tuple("[Console]::Out.WriteLine('"+line.decode('ascii')+
        "')\n[Console]::Out.Flush()\n" for line in CONTROL_PROGRESS_LINES)
    preferences = r'''
$ErrorActionPreference='Stop'
$ProgressPreference='SilentlyContinue'
'''
    writer = r'''
class C7LiteralWriter {
    [string]$Frame=''
    [void]WriteLine([string]$value) { $this.Frame=$value }
}
$writer=[C7LiteralWriter]::new()
''' if writer_kind == 'authored-class' else '$writer=[IO.StringWriter]::new()\n'
    body = r'''
$line='{"owned":true}'
$state='conversion-refused'
''' + module.CONVERSION_PROJECTOR + markers[1] + '\ntry {\n' + module.CONVERSION_CALL + markers[2] + r'''
    $names=@($grant.PSObject.Properties.Name)
    if ($names.Count -eq 1 -and $names -ccontains 'owned' -and $grant.owned -is [bool] -and $grant.owned -eq $true) {
        $state='parsed'
    } else { $state='shape-refused' }
} catch { $state='conversion-refused' }
[Console]::Out.WriteLine('{"kind":"authored-real-conversion-control","state":"'+$state+'"}')
'''
    body += ("if ($writer.Frame -cne '') { [Console]::Out.WriteLine($writer.Frame) }\n"
        if writer_kind == 'authored-class' else '[Console]::Out.Write($writer.ToString())\n')
    body += r'''
if ($state -ceq 'parsed') { exit 0 } else { exit 2 }
'''
    if writer_kind == 'string-writer':
        body = 'try {\n'+body+'\n} finally { $writer.Dispose() }\n'
    return markers[0]+preferences+writer+body


@pytest.mark.skipif(sys.platform != 'win32', reason='Authored real Windows PowerShell cmdlet control unavailable locally')
def test_authored_real_conversion_under_inherited_and_attempt_environment():
    # No C7 fixture or grant: exact protected executable, literal input only.
    try: executable = module.Windows().powershell()
    except Exception: executable = None
    script = real_conversion_literal_script('authored-class')
    boundaries, delivered = {}, {}
    def run(environment):
        variant = ('inherited', 'attempt')[len(boundaries)]
        diagnostic = boundaries[variant] = {}
        progress = delivered[variant] = {}
        if executable is None:
            diagnostic.update(closed_real_control_boundary(None))
            return None
        return run_real_conversion_control(executable, script, environment, diagnostic=diagnostic, progress=progress)
    parent_environment = dict(os.environ)
    observed = real_conversion_pair(parent_environment, run)
    system_controls = {}
    for name, environment in real_conversion_system_environments(parent_environment, executable).items():
        diagnostic, progress = {}, {}
        try:
            value = run_real_conversion_control(executable, script, environment, diagnostic=diagnostic, progress=progress)
        except Exception:
            value = None
        system_controls[name] = {'observation': closed_real_conversion_observation(value),
            'boundary': closed_real_control_boundary(diagnostic), 'progress': closed_real_control_progress(progress)}
    writer_script = real_conversion_literal_script('string-writer')
    writer_boundaries, writer_delivered = {}, {}
    def run_writer(environment):
        variant = ('inherited', 'attempt')[len(writer_boundaries)]
        diagnostic, progress = {}, {}
        writer_boundaries[variant], writer_delivered[variant] = diagnostic, progress
        if executable is None:
            return None
        return run_real_conversion_control(executable, writer_script, environment,
            diagnostic=diagnostic, progress=progress)
    writer_observations = real_conversion_pair(parent_environment, run_writer)
    writer_controls = {variant: {'observation': value,
        'boundary': closed_real_control_boundary(writer_boundaries.get(variant)),
        'progress': closed_real_control_progress(writer_delivered.get(variant))}
        for variant, value in writer_observations.items()}
    expected = {'state': 'parsed', 'context': None, 'stderr_present': False}
    if (any(value != expected for value in observed.values()) or any(
            value['boundary']['cleanup'] != 'child-exit-and-readers-finished'
            for value in (*system_controls.values(), *writer_controls.values()))):
        closed = {key: closed_real_control_boundary(boundaries.get(key)) for key in ('inherited', 'attempt')}
        progress = {key: closed_real_control_progress(delivered.get(key)) for key in ('inherited', 'attempt')}
        pytest.fail('Authored real conversion controls refused: ' + json.dumps(observed, sort_keys=True, separators=(',', ':'))
            + '; parent boundaries: ' + json.dumps(closed, sort_keys=True, separators=(',', ':'))
            + '; literal progress: ' + json.dumps(progress, sort_keys=True, separators=(',', ':'))
            + '; system search controls: ' + json.dumps(system_controls, sort_keys=True, separators=(',', ':'))
            + '; StringWriter controls: ' + json.dumps(writer_controls, sort_keys=True, separators=(',', ':')))


def test_changed_wire_does_not_relabel_historical_v2_receipts():
    value = module.receipt()
    value['schema'] = 'proxy-r19-legacy-lock-attribute-mechanism-v2'
    with pytest.raises(module.Refused): module.public_receipt(value)


def test_valid_terminal_cannot_hide_trailing_records_or_become_open_evidence():
    attempt = progress_attempt()
    attempt.pipe.frames.append({'kind': 'checkpoint', 'stage': 'connected'})
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert attempt.checkpoint['script_step'] == 'operationresult' and attempt.checkpoint_locked


def test_progress_deadline_is_not_extended_by_each_short_record(monkeypatch):
    clock = [0.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    attempt = progress_attempt()
    receive = attempt.pipe.receive
    def slow(deadline):
        clock[0] += 3.
        if clock[0] >= deadline: raise module.Refused('protocol-refused')
        return receive(deadline)
    attempt.pipe.receive = slow
    with pytest.raises(module.Refused): attempt.script_exchange({})
    assert attempt.checkpoint['script_step'] == 'grantparsed' and clock[0] == 12.
    assert set(attempt.pipe.deadlines) == {10.}


def test_several_individually_small_frames_share_one_cumulative_receive_cap():
    pending = [bytearray(b'{"padding":"' + b'x' * 2500 + b'"}\n') for _ in range(2)]
    def peek(handle, data, size, read, available, left): available._obj.value = len(pending[0]); return 1
    def read(handle, output, size, received, overlapped):
        chunk = bytes(pending[0][:size]); del pending[0][:size]
        if not pending[0]: pending.pop(0)
        ctypes.memmove(output, chunk, len(chunk)); received._obj.value = len(chunk); return 1
    pipe = module.Pipe.__new__(module.Pipe)
    pipe.api = SimpleNamespace(check=lambda value: value, k=SimpleNamespace(PeekNamedPipe=peek, ReadFile=read))
    pipe.handle, pipe.buffer, pipe.received = module.Handle(pipe.api, 8), bytearray(), 0
    assert pipe.receive(float('inf')) == {'padding': 'x' * 2500}
    with pytest.raises(module.Refused): pipe.receive(float('inf'))
    assert pipe.received == module.LIMIT + 1


@pytest.mark.parametrize('state', ['buffered', 'queued', 'closed', 'other-error', 'deadline'])
def test_terminal_pipe_boundary_rejects_trailing_or_unconfirmed_completion(monkeypatch, state):
    clock = [0.]
    monkeypatch.setattr(module.time, 'monotonic', lambda: clock[0])
    monkeypatch.setattr(module.time, 'sleep', lambda seconds: clock.__setitem__(0, clock[0] + seconds))
    monkeypatch.setattr(ctypes, 'get_last_error', lambda: 109 if state == 'closed' else 233, raising=False)
    def peek(handle, data, size, read, available, left):
        available._obj.value = 1 if state == 'queued' else 0
        return state not in {'closed', 'other-error'}
    pipe = module.Pipe.__new__(module.Pipe)
    pipe.api = SimpleNamespace(k=SimpleNamespace(PeekNamedPipe=peek))
    pipe.handle, pipe.buffer = module.Handle(pipe.api, 8), bytearray(b'extra' if state == 'buffered' else b'')
    if state == 'closed': pipe.finish(.03)
    else:
        with pytest.raises(module.Refused): pipe.finish(.03)
    assert clock[0] <= .03


@pytest.mark.parametrize('native,expected', [(0, 'signaled'), (258, 'not-signaled'), (0xffffffff, 'unavailable')])
def test_child_state_is_observed_from_genuine_handle_before_close_without_changing_cleanup(native, expected):
    calls = []
    attempt = module.Attempt.__new__(module.Attempt)
    attempt.checkpoint, attempt.checkpoint_locked = module.checkpoint(), False
    attempt.closed = attempt.poisoned = False
    attempt.child = SimpleNamespace(created=True, closed=False, process_handle=111,
        stop_and_wait=lambda _: calls.append('stop'))
    attempt.owner = SimpleNamespace(kernel=SimpleNamespace(WaitForSingleObject=lambda handle, ms: calls.append(('signal', handle, ms)) or native),
        terminate=lambda **_: calls.append('drain'), close=lambda: calls.append('owner-close'))
    attempt.pipe = SimpleNamespace(close=lambda: calls.append('pipe-close'))
    attempt.close(); attempt.close()
    assert calls == [('signal', 111, 0), 'stop', 'drain', 'owner-close', 'pipe-close']
    assert attempt.checkpoint['child_state'] == expected and attempt.closed


def test_checkpoint_failure_stage_survives_cleanup_and_query_failure_is_context_only():
    attempt = module.Attempt.__new__(module.Attempt)
    attempt.checkpoint = module.checkpoint(); attempt.checkpoint['parent_step'] = 'bind-client'
    attempt.checkpoint_locked = True; attempt.closed = attempt.poisoned = False
    def unavailable(*_): raise OSError('private query sentinel')
    attempt.child = SimpleNamespace(created=True, closed=False, process_handle=111, stop_and_wait=lambda _: None)
    attempt.owner = SimpleNamespace(kernel=SimpleNamespace(WaitForSingleObject=unavailable), terminate=lambda **_: None, close=lambda: None)
    attempt.pipe = SimpleNamespace(close=lambda: None)
    attempt.close()
    assert attempt.closed and attempt.checkpoint == {'parent_step': 'bind-client', 'script_step': 'not-started', 'child_state': 'unavailable'}


def test_no_signal_query_uses_an_already_closed_creation_record():
    attempt = module.Attempt.__new__(module.Attempt)
    attempt.checkpoint = module.checkpoint()
    attempt.child = SimpleNamespace(created=True, closed=True)
    attempt.owner = SimpleNamespace(kernel=SimpleNamespace(WaitForSingleObject=lambda *_: pytest.fail('No stale handle query.')))
    attempt.observe_child()
    assert attempt.checkpoint['child_state'] == 'unavailable'


@pytest.mark.parametrize('value', [None, {}, {'parent_step': 'private-path', 'script_step': 'not-started', 'child_state': 'not-created'},
    {'parent_step': 'not-started', 'script_step': 'not-started', 'child_state': 1},
    {'parent_step': 'not-started', 'script_step': 'not-started', 'child_state': 'not-created', 'pid': 123}])
def test_checkpoint_public_projection_has_exact_three_finite_keys(value):
    result = successful_receipt(); result['baseline_checkpoint'] = value
    with pytest.raises(module.Refused): module.public_receipt(result)


def test_diagnostic_child_unavailability_never_grants_or_revokes_native_acceptance():
    value = successful_receipt()
    value['baseline_checkpoint']['child_state'] = 'unavailable'
    assert module.public_receipt(value)['keeper_loss_acceptance'] is False
    assert module.public_receipt(value)['status'] == 'mechanism-observed'


@pytest.mark.parametrize('failure,expected', [('pipe', 'create-pipe'), ('create', 'create-owned-process'),
    ('resume', 'resume-owned-process'), ('bind', 'bind-client')])
def test_baseline_start_boundaries_are_recorded_before_failure_and_survive_cleanup(monkeypatch, tmp_path, failure, expected):
    calls = []
    def refuse(): raise module.Refused('protocol-refused')
    class Child:
        created, closed, process_handle = True, False, 111
        def resume_once(self):
            calls.append('resume')
            if failure == 'resume': refuse()
        def stop_and_wait(self, deadline): calls.append('stop')
    class Owner:
        created_children = ()
        kernel = SimpleNamespace(WaitForSingleObject=lambda *_: 0)
        def create_suspended(self, *_, **__):
            calls.append('create')
            if failure == 'create': refuse()
            return Child()
        def terminate(self, **_): calls.append('drain')
        def close(self): calls.append('owner-close')
    class Wire:
        name = 'owned-fixture-pipe'
        def __init__(self, api):
            if failure == 'pipe': refuse()
        def bind(self, child, deadline):
            calls.append('bind')
            if failure == 'bind': refuse()
        def close(self): calls.append('pipe-close')
    monkeypatch.setattr(module, 'Pipe', Wire)
    monkeypatch.setattr(module, 'process_module', lambda: SimpleNamespace(WindowsPreparationProcess=Owner))
    value = module.checkpoint()
    with pytest.raises(module.Refused):
        module.Attempt(SimpleNamespace(), lambda name: ['owned-fixture'], tmp_path, checkpoint_value=value)
    assert value['parent_step'] == expected and value['script_step'] == 'not-started'
    assert value['child_state'] == ('signaled' if failure in {'resume', 'bind'} else 'not-created')
    assert 'private' not in json.dumps(value)
