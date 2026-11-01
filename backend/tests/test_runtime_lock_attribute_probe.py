"""Authored boundary fixtures only; these never establish Windows behavior."""
import base64
import copy
import ctypes
import io
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
from types import SimpleNamespace

import pytest

from backend import runtime_lock_attribute_probe as module



def test_current_source_rebind_admits_only_reviewed_checkout_variants_and_exact_operation():
    # The whole source changed only in its router; this fixed mechanism still
    # invokes the exact original operation definition, never the new router.
    source = module.SOURCE.read_bytes().replace(b'\r\n', b'\n')
    assert module.SOURCE_HASHES == frozenset({
        'c3735131417eb01d93e5fb19138f64997bf771a0b4d5f913d7b4f08aef0f350f',
        '9c05279ddeea90b7a2fb4cd7f917ad44ca798e98b693276ea5455ff547350056'})
    assert {hashlib.sha256(source).hexdigest(), hashlib.sha256(source.replace(b'\n', b'\r\n')).hexdigest()} == module.SOURCE_HASHES
    declaration = b'function Enter-CompanionOperation'
    assert source.count(declaration) == 1
    start = source.index(declaration)
    end = source.index(b'\nfunction ', start)
    assert hashlib.sha256(source[start:end]).hexdigest() == 'bb8315f2cce15d5e1b3c561556c64ee772ed915cde9acb11e14f12694bbd51e0'
    helper = (module.ROOT/'backend/windows_preparation_process.py').read_bytes().replace(b'\r\n', b'\n')
    assert module.HELPER_HASHES == frozenset({
        'c71f83072fc60aa1efd78a960a6e7b5793b041b030fbac392c50c3b04519718e',
        '53136e53af4b96a8a1fd3192f07c8a8c79f287ebac307156a90814af7ff03119'})
    assert {hashlib.sha256(helper).hexdigest(), hashlib.sha256(helper.replace(b'\n', b'\r\n')).hexdigest()} == module.HELPER_HASHES
    assert 'c0cb1b456c029e8cb843501ffaf17cf2b054bdfecad8e788dd35d9a85ae2d3ef' not in module.SOURCE_HASHES
    assert '24a6995cc1d4d9260a9afe3049fbdf5d927cfddcfd405095ebcd49674e7234d0' not in module.HELPER_HASHES


@pytest.mark.skipif(sys.platform != 'win32', reason='Windows PowerShell source AST parser unavailable locally')
def test_current_operation_powershell_ast_extent_matches_the_reviewed_definition():
    source = str(module.SOURCE).replace("'", "''")
    script = r"""$ErrorActionPreference='Stop'
$tokens=$null; $errors=$null
$ast=[Management.Automation.Language.Parser]::ParseFile('__SOURCE__',[ref]$tokens,[ref]$errors)
$defs=@($ast.FindAll({param($node) $node -is [Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -ceq 'Enter-CompanionOperation'},$true))
if ($errors -or $defs.Count -ne 1) { exit 2 }
$text=$defs[0].Extent.Text.Replace("`r`n","`n")
$sha=[Security.Cryptography.SHA256]::Create()
try { $hash=([BitConverter]::ToString($sha.ComputeHash([Text.Encoding]::UTF8.GetBytes($text)))).Replace('-','').ToLowerInvariant() }
finally { $sha.Dispose() }
if ($hash -cne '1db508d342287f3be154fa97a4018db9d3802331bd0306a2fc50b288255208af') { exit 3 }
[Console]::WriteLine('C7AST|reviewed-definition')
""".replace('__SOURCE__', source)
    try:
        result = subprocess.run([module.Windows().powershell(), '-NoProfile', '-NonInteractive', '-EncodedCommand',
            base64.b64encode(script.encode('utf-16le')).decode('ascii')],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        pytest.fail('Fixed source AST check could not finish.', pytrace=False)
    status_ok = result.returncode == 0
    envelope_ok = result.stdout == b'C7AST|reviewed-definition\r\n' and result.stderr == b''
    assert status_ok, 'Fixed source AST check refused the operation definition.'
    assert envelope_ok, 'Fixed source AST check returned an unexpected envelope.'

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
def authored_source(monkeypatch, tmp_path):
    """Pin isolated behavior-test bytes, never repin the historical experiment."""
    source = tmp_path / 'authored-source.ps1'
    content = b'# Authored fixture; no production PowerShell execution.\n'
    source.write_bytes(content)
    monkeypatch.setattr(module, 'SOURCE', source)
    monkeypatch.setattr(module, 'SOURCE_HASHES', frozenset({hashlib.sha256(content).hexdigest()}))
    return source


@pytest.fixture
def authored(monkeypatch, tmp_path, authored_source):
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
    def legacy(_api, root, source, expected, *, checkpoint_value=None):
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
    def refuse(api, root, source, expected, *, checkpoint_value=None):
        if expected == 'readonly-refused': raise module.Refused('legacy-outcome-differed')
        return previous(api, root, source, expected, checkpoint_value=checkpoint_value)
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


def test_nonlocal_or_non_ntfs_temp_refuses_before_any_fixture_write(monkeypatch, authored_source):
    def refuse(_root): raise module.Refused('fixture-refused')
    monkeypatch.setattr(module, 'Windows', lambda: SimpleNamespace(ntfs=refuse))
    monkeypatch.setattr(module.tempfile, 'mkdtemp', lambda **_: pytest.fail('No unsupported-volume fixture write.'))
    result = module.experiment()
    assert result['status'] == 'failed' and result['failure'] == 'fixture-refused'


def test_unpinned_source_refuses_before_any_fixture_write(tmp_path, monkeypatch):
    source = tmp_path / 'unreviewed-source.ps1'
    source.write_bytes(b'# Deliberately outside the historical reviewed source hashes.\n')
    monkeypatch.setattr(module, 'SOURCE', source)
    monkeypatch.setattr(module, 'Windows', lambda: SimpleNamespace(
        ntfs=lambda _: pytest.fail('Unpinned source must fail before volume inspection.')))
    monkeypatch.setattr(module.tempfile, 'mkdtemp', lambda **_: pytest.fail('No unpinned-source fixture write.'))
    result = module.experiment()
    assert result['status'] == 'failed' and result['failure'] == 'source-changed'
    assert not result['observed'] and result['legacy_source_sha256'] is None
    assert result['production_allowed'] is result['r19_complete'] is False


@pytest.mark.parametrize('kind', ['oversized', 'symlink'])
def test_fixture_marker_is_bounded_and_link_refused_before_marker_read(tmp_path, monkeypatch, kind):
    monkeypatch.setattr(module.tempfile, 'gettempdir', lambda: str(tmp_path.resolve()))
    root = tmp_path / 'r19-lock-attribute-authored'
    root.mkdir(); (root / 'data').mkdir()
    (root / 'data/companion-operation.lock').write_bytes(module.CONTENT)
    marker = root / module.MARKER
    if kind == 'oversized':
        marker.write_bytes(b'x' * (module.LIMIT + 1))
    else:
        outside = tmp_path / 'outside'; outside.mkdir()
        try:
            marker.symlink_to(outside / 'never-read')
        except OSError as error:
            if getattr(error, 'winerror', None) == 1314:
                pytest.skip('Windows symbolic-link privilege is unavailable')
            raise
    with pytest.raises(module.Refused): module.fixture(root, 'a' * 32)


def progress_attempt(frames=None):
    class Wire:
        def __init__(self):
            self.frames = list(frames if frames is not None else [
                *({'kind': 'checkpoint', 'stage': name} for name in module.SCRIPT_STEPS[1:-1]),
                {'state': 'open'}])
            self.deadlines = []
        def send_legacy_grant(self, value, deadline): self.deadlines.append(deadline)
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


_UNCONFIRMED_CODEC_CONTROLS = []  # Private process/pipe/thread records, never PID adoption/retry.


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


def run_grant_codec_control(executable, script, environment, *, diagnostic=None, cwd=None, observe=None):
    import base64
    unavailable = ({'state': 'unavailable', 'stderr_present': False} if observe is None
        else observe(None, b'', b''))
    boundary = {'refusal': 'none', 'stderr_prefix': 'unavailable', 'cleanup': 'unconfirmed'}
    def publish_boundary():
        if diagnostic is not None:
            diagnostic.clear()
            diagnostic.update(closed_real_control_boundary(boundary))
    try:
        options = {} if cwd is None else {'cwd': cwd}
        process = subprocess.Popen([executable, '-NoProfile', '-NonInteractive', '-EncodedCommand',
            base64.b64encode(script.encode('utf-16le')).decode('ascii')],
            env=environment, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NO_WINDOW, **options)
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
        _UNCONFIRMED_CODEC_CONTROLS.append({'process': process, 'readers': readers})
        boundary['refusal'] = 'cleanup-unconfirmed'
    else:
        boundary['cleanup'] = 'child-exit-and-readers-finished'
    if 'err' in captured:
        raw = captured['err']
        boundary['stderr_prefix'] = ('empty' if not raw else
            'fixed-clixml-prefix' if raw.startswith(b'#< CLIXML') else 'other')
    if failed or uncertain or not exited or any(len(value) > 8192 for value in captured.values()):
        if boundary['refusal'] == 'none': boundary['refusal'] = 'capture-refused'
        publish_boundary()
        if observe is not None:
            return observe(None, captured.get('out', b''), captured.get('err', b''))
        unavailable['stderr_present'] = bool(captured.get('err'))
        return unavailable
    observed = (grant_codec_observation if observe is None else observe)(
        code, captured.get('out', b''), captured.get('err', b''))
    if observed['state'] == 'unavailable': boundary['refusal'] = 'protocol-refused'
    publish_boundary()
    return observed


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
def test_grant_codec_runner_bounds_faults_and_retains_uncertain_ownership(monkeypatch, fault):
    retained, processes, calls = [], [], []
    monkeypatch.setitem(globals(), '_UNCONFIRMED_CODEC_CONTROLS', retained)
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
                {'kind': 'authored-c7g5-codec', 'positive': True, 'negative': True, 'reader': True}).encode('ascii'), 'out')
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
    result = run_grant_codec_control('authored-program', 'authored-source', {}, diagnostic=diagnostic)
    assert result == {'state': 'unavailable', 'stderr_present': False}
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
            self.stdout = io.BytesIO(b'{"kind":"authored-c7g5-codec","positive":true,"negative":true,"reader":true}')
            self.stderr = io.BytesIO(stderr)
        def wait(self, timeout):
            assert timeout == 10
            return 0
        def kill(self): pytest.fail('A completed authored child must not be killed.')
    monkeypatch.setattr(subprocess, 'Popen', Process)
    diagnostic = {}
    result = run_grant_codec_control('authored-program', 'authored-source', {}, diagnostic=diagnostic)
    assert diagnostic == {'refusal': 'none', 'stderr_prefix': prefix, 'cleanup': 'child-exit-and-readers-finished'}
    assert result == {'state': 'passed', 'stderr_present': bool(stderr)}
    # The unchanged paired acceptance still refuses any stderr bytes. A prefix
    # observation cannot classify messages or change that predicate.
    assert (result == {'state': 'passed', 'stderr_present': False}) == (not stderr)
    assert 'private-' not in json.dumps(diagnostic)


def test_real_control_spawn_refusal_has_only_fixed_parent_metadata(monkeypatch):
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    def refuse(*_args, **_kwargs): raise OSError('private-program-and-path')
    monkeypatch.setattr(subprocess, 'Popen', refuse)
    diagnostic = {}
    result = run_grant_codec_control('authored-program', 'authored-source', {}, diagnostic=diagnostic)
    assert result == {'state': 'unavailable', 'stderr_present': False}
    assert diagnostic == {'refusal': 'spawn-refused', 'stderr_prefix': 'unavailable', 'cleanup': 'unconfirmed'}
    assert 'private-' not in json.dumps(diagnostic)


@pytest.mark.parametrize('version', [1, 2, 3, 4])
def test_v5_cannot_relabel_any_historical_receipt(version):
    value = module.receipt()
    value['schema'] = 'proxy-r19-legacy-lock-attribute-mechanism-v'+str(version)
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

def grant_value(**changes):
    value = {'root': r'S:\r19-authored\owned', 'source': r'S:\r19-authored\companion-runtime.ps1', 'sha256': 'a'*64}
    value.update(changes)
    return value


def reference_grant_frame(frame):
    """Complete sender-frame reference, not proof of pipe EOF after its LF."""
    if type(frame) is not bytes or not 1 <= len(frame) <= 4096 or not frame.endswith(b'\n') or frame.count(b'\n') != 1 or b'\r' in frame:
        raise ValueError('Authored frame refused.')
    parts = frame[:-1].split(b'|')
    if len(parts) != 4 or parts[0] != b'C7G5': raise ValueError('Authored frame refused.')
    values = []
    for token in parts[1:]:
        raw = base64.b64decode(token, validate=True)
        if not raw or len(raw) > 3072 or base64.b64encode(raw) != token or raw.startswith(b'\xef\xbb\xbf'):
            raise ValueError('Authored frame refused.')
        text = raw.decode('utf-8', errors='strict')
        if any(character in text for character in ('\0', '\r', '\n')): raise ValueError('Authored frame refused.')
        values.append(text)
    if len(values[2]) != 64 or any(character not in '0123456789abcdef' for character in values[2]):
        raise ValueError('Authored frame refused.')
    return dict(zip(('root', 'source', 'sha256'), values))


def bad_grant_frames():
    ordinary = module.legacy_grant_bytes(grant_value())
    parts = ordinary[:-1].split(b'|')
    def replace(index, value):
        values = list(parts); values[index] = value
        return b'|'.join(values)+b'\n'
    return {
        'version': ordinary.replace(b'C7G5', b'C7G4', 1),
        'extra-field': ordinary[:-1]+b'|eA==\n',
        'missing-field': b'|'.join(parts[:-1])+b'\n',
        'empty-field': replace(1, b''),
        'whitespace': replace(1, parts[1]+b' '),
        'bad-padding': replace(1, b'eA==='),
        'pad-bits': replace(1, b'eB=='),
        'bad-alphabet': replace(1, b'???='),
        'invalid-utf8': replace(1, base64.b64encode(b'\xff')),
        'bom': replace(1, base64.b64encode(b'\xef\xbb\xbfx')),
        'nul': replace(1, base64.b64encode(b'x\0y')),
        'decoded-cr': replace(1, base64.b64encode(b'x\ry')),
        'decoded-lf': replace(1, base64.b64encode(b'x\ny')),
        'upper-digest': replace(3, base64.b64encode(b'A'*64)),
        'short-digest': replace(3, base64.b64encode(b'a'*63)),
        'nonhex-digest': replace(3, base64.b64encode(b'g'*64)),
        'crlf': ordinary[:-1]+b'\r\n',
        'no-terminator': ordinary[:-1],
        'wire-nul': ordinary.replace(b'C7G5', b'C7\x005', 1),
        'wire-nonascii': ordinary.replace(b'C7G5', b'C7\xff5', 1),
    }


@pytest.mark.parametrize('value', [grant_value(), grant_value(root=r'S:\r19-authored\中文 ; $literal',
    source="S:\\r19-authored\\源 'quote'.ps1"), grant_value(root='x'*1497, source='y'*1503)])
def test_canonical_sender_preserves_exact_three_utf8_values_and_wire_boundary(value):
    frame = module.legacy_grant_bytes(value)
    assert reference_grant_frame(frame) == value
    assert frame.startswith(b'C7G5|') and len(frame) <= 4096
    assert len(frame[:-1].split(b'|')) == 4 and frame.count(b'\n') == 1
    if len(value['root']) == 1497: assert len(frame) == 4096


@pytest.mark.parametrize('field', ['root', 'source', 'sha256'])
@pytest.mark.parametrize('invalid', [None, False, 1, '', 'private\0value', 'private\rvalue',
    'private\nvalue', '\ufeffprivate-value', '\ud800', 'x'*3073])
def test_canonical_sender_refuses_untyped_empty_control_invalid_utf8_or_oversized_fields(field, invalid):
    with pytest.raises(module.Refused) as error: module.legacy_grant_bytes(grant_value(**{field: invalid}))
    assert str(error.value) == 'protocol-refused' and 'private' not in str(error.value)


@pytest.mark.parametrize('mutation', ['missing', 'extra', 'raw-bytes', 'wrong-dict', 'upper-digest', 'nonhex', 'total-cap'])
def test_canonical_sender_cannot_accept_raw_wire_extra_fields_or_noncanonical_digest(mutation):
    value = grant_value()
    if mutation == 'missing': value.pop('source')
    if mutation == 'extra': value['private-key'] = 'private-value'
    if mutation == 'raw-bytes': value = b'C7G5|private-wire\n'
    if mutation == 'wrong-dict': value = [('root', 'private-value')]
    if mutation == 'upper-digest': value['sha256'] = 'A'*64
    if mutation == 'nonhex': value['sha256'] = 'g'*64
    if mutation == 'total-cap': value.update(root='x'*1498, source='y'*1503)
    with pytest.raises(module.Refused) as error: module.legacy_grant_bytes(value)
    assert error.value.code == 'protocol-refused'


@pytest.mark.parametrize('name', tuple(bad_grant_frames()))
def test_complete_frame_reference_rejects_noncanonical_inputs_used_by_native_decoder_cases(name):
    with pytest.raises((ValueError, UnicodeError)): reference_grant_frame(bad_grant_frames()[name])


def test_complete_sender_frame_has_no_second_record_and_does_not_claim_future_pipe_eof():
    frame = module.legacy_grant_bytes(grant_value())
    with pytest.raises(ValueError): reference_grant_frame(frame+b'private-extra-line\n')
    assert reference_grant_frame(frame) == grant_value()
    # The exact native reader consumes one bounded line, not the future pipe.
    # Its StringReader preflight separately verifies that tail remains unread.


def test_legacy_sender_uses_canonical_bytes_and_original_nonblocking_write_loop_deadline(monkeypatch):
    now, writes = [0.], []
    def write(_handle, data, size, count, _overlapped):
        writes.append(bytes(data.raw[:min(size, 3)])); count._obj.value = min(size, 3)
        return 1
    pipe = module.Pipe.__new__(module.Pipe)
    pipe.handle = SimpleNamespace(value=8)
    pipe.api = SimpleNamespace(k=SimpleNamespace(WriteFile=write))
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: now[0], sleep=lambda _seconds: None))
    pipe.send_legacy_grant(grant_value(), 1)
    assert b''.join(writes) == module.legacy_grant_bytes(grant_value())
    writes.clear(); now[0] = 1
    with pytest.raises(module.Refused): pipe.send_legacy_grant(grant_value(), 1)
    assert writes == []
    pipe.send = lambda *_: pytest.fail('Legacy grant cannot route through JSON send.')
    now[0] = 0; pipe.send_legacy_grant(grant_value(), 1)


@pytest.mark.parametrize('fault', ['refused-write', 'invalid-count', 'zero-until-deadline'])
def test_canonical_send_faults_cannot_ignore_count_or_restart_the_original_deadline(monkeypatch, fault):
    now, calls = [0.], []
    def write(_handle, _data, size, count, _overlapped):
        calls.append(size)
        count._obj.value = size+1 if fault == 'invalid-count' else 0
        return 0 if fault == 'refused-write' else 1
    pipe = module.Pipe.__new__(module.Pipe)
    pipe.handle = SimpleNamespace(value=8)
    pipe.api = SimpleNamespace(k=SimpleNamespace(WriteFile=write))
    monkeypatch.setattr(module, 'time', SimpleNamespace(monotonic=lambda: now[0],
        sleep=lambda _seconds: now.__setitem__(0, now[0]+.6)))
    with pytest.raises(module.Refused) as error: pipe.send_legacy_grant(grant_value(), 1)
    assert error.value.code == 'protocol-refused'
    assert len(calls) == (2 if fault == 'zero-until-deadline' else 1)


@pytest.mark.parametrize('payload', [{}, False, 'private-context', {'line': 'nonempty', 'exceptions': ['argument']}])
def test_v5_conversion_diagnostic_is_strictly_null_for_every_receipt(payload):
    value = module.receipt(); value['grant_conversion_failure'] = payload
    with pytest.raises(module.Refused): module.public_receipt(value)
    value = successful_receipt(); value['grant_conversion_failure'] = payload
    with pytest.raises(module.Refused): module.public_receipt(value)


@pytest.mark.parametrize('stages', [['connected'], ['connected', 'grantread'],
    ['connected', 'grantread', 'grantparsed']])
def test_v5_rejects_historical_conversion_frame_without_adopting_it_as_progress(stages):
    old_frame = {'kind': 'grant-conversion-failure', 'line': 'nonempty',
        'exceptions': ['argument'], 'chain_end': 'complete', 'category': 'InvalidArgument'}
    attempt = progress_attempt([*({'kind': 'checkpoint', 'stage': stage} for stage in stages), old_frame])
    attempt.pipe.finish = lambda *_: pytest.fail('Unknown v4 frame cannot reach terminal EOF admission.')
    with pytest.raises(module.Refused): attempt.script_exchange(grant_value())
    assert attempt.checkpoint_locked and attempt.checkpoint['script_step'] == stages[-1]
    assert module.receipt()['grant_conversion_failure'] is None


@pytest.mark.parametrize('cleanup_fails', [False, True])
def test_legacy_grant_refusal_preserves_primary_or_cleanup_error_and_closes_owned_attempt_once(monkeypatch, tmp_path, cleanup_fails):
    primary, cleanup = module.Refused('protocol-refused'), module.Refused('owned-cleanup-unconfirmed')
    calls = []
    class Attempt:
        def __init__(self, *args, checkpoint_value=None): self.checkpoint_locked = False
        def script_exchange(self, value):
            assert set(value) == {'root', 'source', 'sha256'}
            raise primary
        def close(self):
            calls.append('close')
            if cleanup_fails: raise cleanup
    monkeypatch.setattr(module, 'Attempt', Attempt)
    monkeypatch.setattr(module, 'source_bytes', lambda *_: next(iter(module.SOURCE_HASHES)))
    with pytest.raises(module.Refused) as error:
        module.legacy(SimpleNamespace(powershell=lambda: 'authored-program'), tmp_path,
            next(iter(module.SOURCE_HASHES)), 'open', checkpoint_value=module.checkpoint())
    assert error.value is (cleanup if cleanup_fails else primary) and calls == ['close']


def closed_grant_codec_observation(value):
    fallback = {'state': 'unavailable', 'stderr_present': False}
    if type(value) is not dict:
        return fallback
    if type(value.get('stderr_present')) is bool:
        fallback['stderr_present'] = value['stderr_present']
    if (set(value) != {'state', 'stderr_present'} or type(value['state']) is not str
            or value['state'] not in {'passed', 'failed', 'unavailable'}
            or type(value['stderr_present']) is not bool):
        return fallback
    return dict(value)


def grant_codec_observation(code, output, stderr):
    unavailable = {'state': 'unavailable', 'stderr_present': bool(stderr)}
    try:
        if type(code) is not int or code not in (0, 2) or type(output) is not bytes or len(output) > 8192 or type(stderr) is not bytes or len(stderr) > 8192:
            return unavailable
        def unique(pairs):
            value = {}
            for key, item in pairs:
                if key in value: raise ValueError('Authored codec frame differs.')
                value[key] = item
            return value
        lines = output.splitlines()
        if len(lines) != 1: return unavailable
        value = json.loads(lines[0], object_pairs_hook=unique)
        if (type(value) is not dict or set(value) != {'kind', 'positive', 'negative', 'reader'}
                or value['kind'] != 'authored-c7g5-codec'
                or any(type(value[key]) is not bool for key in ('positive', 'negative', 'reader'))):
            return unavailable
        good = all(value[key] for key in ('positive', 'negative', 'reader'))
        if code != (0 if good else 2): return unavailable
        return {'state': 'passed' if good else 'failed', 'stderr_present': bool(stderr)}
    except (ValueError, UnicodeError, TypeError):
        return unavailable


@pytest.mark.parametrize('mutation', ['absent', 'partial', 'duplicate-key', 'extra-key', 'private-kind', 'numeric-bool', 'multiple', 'wrong-exit', 'oversized'])
def test_codec_preflight_observation_refuses_malformed_private_or_inconsistent_frames(mutation):
    frame = {'kind': 'authored-c7g5-codec', 'positive': True, 'negative': True, 'reader': True};code = 0
    if mutation == 'extra-key': frame['private-path'] = 'private-value'
    if mutation == 'private-kind': frame['kind'] = 'private-type'
    if mutation == 'numeric-bool': frame['reader'] = 1
    raw = json.dumps(frame).encode('ascii')
    if mutation == 'absent': raw = b''
    if mutation == 'partial': raw = raw[:-1]
    if mutation == 'duplicate-key': raw = raw.replace(b'"reader": true', b'"reader": true,"reader":false')
    if mutation == 'multiple': raw += b'\n'+raw
    if mutation == 'wrong-exit': code = 2
    if mutation == 'oversized': raw += b' '*8192
    result = grant_codec_observation(code, raw, b'private-stderr')
    assert result == {'state': 'unavailable', 'stderr_present': True}
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('field', ['positive', 'negative', 'reader'])
def test_every_failed_native_codec_axis_requires_failed_exit_and_cannot_pass(field):
    value = {'kind': 'authored-c7g5-codec', 'positive': True, 'negative': True, 'reader': True}
    value[field] = False
    raw = json.dumps(value).encode('ascii')
    assert grant_codec_observation(2, raw, b'') == {'state': 'failed', 'stderr_present': False}
    assert grant_codec_observation(0, raw, b'')['state'] == 'unavailable'


@pytest.mark.parametrize('refusal', ['none', 'inherited', 'attempt', 'cleanup', 'private-runner'])
def test_v5_native_pair_measures_both_exact_maps_before_hard_decision_and_closed_diagnostic(monkeypatch, refusal):
    image = r'S:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    parent = {'SystemRoot': 'authored-root', 'TEMP': 'authored-temp', 'PATH': 'private-tools'}
    monkeypatch.setattr(module, 'Windows', lambda: SimpleNamespace(powershell=lambda: image))
    monkeypatch.setitem(globals(), 'os', SimpleNamespace(environ=parent))
    calls = []
    def run(executable, script, environment, *, diagnostic):
        assert executable == image
        calls.append(dict(environment))
        diagnostic.update(refusal='none', stderr_prefix='empty', cleanup='child-exit-and-readers-finished')
        if refusal == 'cleanup' and len(calls) == 2: diagnostic['cleanup'] = 'unconfirmed'
        if refusal == 'private-runner': return {'state': 'private-state', 'stderr_present': True, 'raw': 'private-value'}
        failed = refusal == ('inherited' if len(calls) == 1 else 'attempt')
        return {'state': 'failed' if failed else 'passed', 'stderr_present': False}
    monkeypatch.setitem(globals(), 'run_grant_codec_control', run)
    if refusal == 'none': test_actual_c7g5_decoder_under_inherited_and_exact_attempt_environment()
    else:
        with pytest.raises(pytest.fail.Exception) as failed:
            test_actual_c7g5_decoder_under_inherited_and_exact_attempt_environment()
        assert 'private-' not in str(failed.value) and image not in str(failed.value)
    assert calls == [parent, module.legacy_environment(parent)]
    assert parent['PATH'] == 'private-tools'


def grant_codec_script():
    positive = module.legacy_grant_bytes(grant_value())
    unicode_value = grant_value(root=r'S:\r19-authored\中文 ; $literal', source="S:\\r19-authored\\源 'quote'.ps1")
    unicode_frame = module.legacy_grant_bytes(unicode_value)
    def b64(raw): return base64.b64encode(raw).decode('ascii')
    # Fixed short authored vectors; no private path/source/grant is included.
    positives = ','.join("'"+b64(frame)+"'" for frame in (positive, unicode_frame))
    negatives = ','.join("'"+b64(frame)+"'" for frame in bad_grant_frames().values())
    roots = ','.join("'"+b64(value['root'].encode('utf-8'))+"'" for value in (grant_value(), unicode_value))
    sources = ','.join("'"+b64(value['source'].encode('utf-8'))+"'" for value in (grant_value(), unicode_value))
    sha_token = b64(b'a'*64)
    return "$ErrorActionPreference='Stop'\n$ProgressPreference='SilentlyContinue'\n" + module.LEGACY_GRANT_DECODER + r'''
$positive=$true; $negative=$true; $readerGood=$true
$utf8=[Text.UTF8Encoding]::new($false,$true)
$frames=@(__POSITIVES__); $roots=@(__ROOTS__); $sources=@(__SOURCES__)
for ($index=0; $index -lt 2; $index++) {
    $codecReader=[IO.StringReader]::new([Text.Encoding]::ASCII.GetString([Convert]::FromBase64String($frames[$index])))
    try {
        $value=Convert-C7Grant (Read-C7GrantLine $codecReader)
        $expectedRoot=$utf8.GetString([Convert]::FromBase64String($roots[$index]))
        $expectedSource=$utf8.GetString([Convert]::FromBase64String($sources[$index]))
        $names=@($value.PSObject.Properties.Name)
        if ($names.Count -ne 3 -or $names -cnotcontains 'root' -or $names -cnotcontains 'source' -or
            $names -cnotcontains 'sha256' -or $value.root -isnot [string] -or $value.source -isnot [string] -or
            $value.sha256 -isnot [string] -or -not [string]::Equals($value.root,$expectedRoot,[StringComparison]::Ordinal) -or
            -not [string]::Equals($value.source,$expectedSource,[StringComparison]::Ordinal) -or
            -not [string]::Equals($value.sha256,('a'*64),[StringComparison]::Ordinal)) { $positive=$false }
    } catch { $positive=$false } finally { $codecReader.Dispose() }
}
$bad=@(__NEGATIVES__)
$refused=0
foreach ($encoded in $bad) {
    $codecReader=[IO.StringReader]::new([Text.Encoding]::ASCII.GetString([Convert]::FromBase64String($encoded)))
    try { $value=Convert-C7Grant (Read-C7GrantLine $codecReader); $negative=$false }
    catch { $refused++ } finally { $codecReader.Dispose() }
}
if ($bad.Count -ne __NEGATIVE_COUNT__ -or $refused -ne __NEGATIVE_COUNT__) { $negative=$false }
$boundary='C7G5|'+('eHh4'*499)+'|'+('eXl5'*501)+'|__SHA__'+[char]10
$codecReader=[IO.StringReader]::new($boundary)
try {
    $value=Convert-C7Grant (Read-C7GrantLine $codecReader)
    if ($boundary.Length -ne 4096 -or $value.root -cne ('x'*1497) -or $value.source -cne ('y'*1503)) { $readerGood=$false }
} catch { $readerGood=$false } finally { $codecReader.Dispose() }
$codecReader=[IO.StringReader]::new($boundary.Substring(0,4095)+'x'+[char]10)
try { $value=Convert-C7Grant (Read-C7GrantLine $codecReader); $readerGood=$false }
catch { } finally { $codecReader.Dispose() }
$codecReader=[IO.StringReader]::new([Text.Encoding]::ASCII.GetString([Convert]::FromBase64String($frames[0]))+'tail')
try {
    $value=Convert-C7Grant (Read-C7GrantLine $codecReader)
    if ($codecReader.Read() -ne 116) { $readerGood=$false }
} catch { $readerGood=$false } finally { $codecReader.Dispose() }
[Console]::Out.WriteLine('{"kind":"authored-c7g5-codec","positive":'+$positive.ToString().ToLowerInvariant()+
    ',"negative":'+$negative.ToString().ToLowerInvariant()+',"reader":'+$readerGood.ToString().ToLowerInvariant()+'}')
if ($positive -and $negative -and $readerGood) { exit 0 } else { exit 2 }
'''.replace('__POSITIVES__', positives).replace('__NEGATIVES__', negatives).replace('__NEGATIVE_COUNT__', str(len(bad_grant_frames()))).replace('__ROOTS__', roots).replace('__SOURCES__', sources).replace('__SHA__', sha_token)


def measure_grant_codec_pair(parent, run):
    snapshot = dict(parent)
    result = {}
    for name, environment in (('inherited', snapshot), ('attempt', module.legacy_environment(snapshot))):
        boundary = {}
        try: value = run(environment, boundary)
        except Exception: value = {'state': 'unavailable', 'stderr_present': False}
        result[name] = {'observation': closed_grant_codec_observation(value),
            'boundary': closed_real_control_boundary(boundary)}
    return result


@pytest.mark.skipif(sys.platform != 'win32', reason='Exact v5 .NET grant decoder unavailable locally')
def test_actual_c7g5_decoder_under_inherited_and_exact_attempt_environment():
    try: executable = module.Windows().powershell()
    except Exception: executable = None
    script = grant_codec_script()
    if executable is not None: assert_windows_command_capacity(executable, script)
    def run(environment, boundary):
        if executable is None: return {'state': 'unavailable', 'stderr_present': False}
        return run_grant_codec_control(executable, script, environment, diagnostic=boundary)
    results = measure_grant_codec_pair(dict(os.environ), run)
    if any(value['observation'] != {'state': 'passed', 'stderr_present': False}
            or value['boundary']['cleanup'] != 'child-exit-and-readers-finished' for value in results.values()):
        pytest.fail('Authored C7G5 codec controls refused: '+json.dumps(results,sort_keys=True,separators=(',',':')))


# Separate test-only observations. None of these is a legacy-operation result.
OPERATION_MARKERS = {
    'prefix': ('fixture-validated', 'before-join-data', 'after-join-data',
        'before-create-directory', 'after-create-directory', 'before-join-lock',
        'after-join-lock', 'complete'),
    'managed-io': ('fixture-validated', 'before-open', 'open-returned', 'closed', 'complete'),
}
BOOTSTRAP_PHASES = ('unavailable', 'image', 'paths', 'core', 'import', 'module', 'assembly', 'visible', 'complete')
BOOTSTRAP_ERRORS = ('guard', 'binding', 'close', 'other')
MODULE_GUARD_ERRORS = ('guard-count', 'guard-type', 'guard-name', 'guard-path', 'guard-base')
BASE_ROLE_ERRORS = ('guard-base-system-home', 'guard-base-manifest-parent', 'guard-base-other', 'guard-base-unavailable')
_UNCONFIRMED_OPERATION_FIXTURES = []  # Private roots/actual owners, never printed or retried.


def operation_observation(kind, code, output, stderr):
    result = {'state': 'unavailable', 'last_marker': 'not-started', 'stderr_present': bool(stderr),
        'bootstrap_phase': 'unavailable', 'bootstrap_error': 'unavailable'}
    if (kind not in OPERATION_MARKERS or type(output) is not bytes or len(output) > 8192
            or type(stderr) is not bytes or len(stderr) > 8192):
        return result
    expected = OPERATION_MARKERS[kind]
    position = 0
    complete = output.split(b'\n')[:-1]
    # A failure record is admitted only as the sole complete terminal after the
    # validated fixture, with exit2 and no stderr. No partial/captured timeout
    # output can turn into bootstrap context or an operation success.
    for index, line in enumerate(complete):
        if line.endswith(b'\r'): line = line[:-1]
        if line.startswith(b'C7B|'):
            if (position != 1 or index != 1 or len(complete) != 2 or not output.endswith(b'\n')
                    or type(code) is not int or code != 2 or stderr):
                return result
            parts = line.split(b'|')
            if len(parts) != 3: return result
            phases = {value.encode('ascii'): value for value in BOOTSTRAP_PHASES}
            errors = {value.encode('ascii'): value for value in (*BOOTSTRAP_ERRORS, *MODULE_GUARD_ERRORS, *BASE_ROLE_ERRORS)}
            if (parts[1] in phases and parts[2] in errors
                    and (errors[parts[2]] not in (*MODULE_GUARD_ERRORS, *BASE_ROLE_ERRORS) or parts[1] == b'module')):
                result.update(bootstrap_phase=phases[parts[1]], bootstrap_error=errors[parts[2]])
            return result
        if position >= len(expected) or line != ('C7O|'+expected[position]).encode('ascii'):
            return result
        result['last_marker'] = expected[position]
        position += 1
    if (output.endswith(b'\n') and position == len(expected)
            and type(code) is int and code == 0):
        result.update(state='passed', bootstrap_phase='complete', bootstrap_error='none')
    return result


def closed_operation_observation(kind, value):
    fallback = {'state': 'unavailable', 'last_marker': 'not-started', 'stderr_present': False,
        'bootstrap_phase': 'unavailable', 'bootstrap_error': 'unavailable'}
    if (kind not in OPERATION_MARKERS or type(value) is not dict or set(value) != set(fallback)
            or type(value['state']) is not str or value['state'] not in {'passed', 'unavailable'}
            or type(value['last_marker']) is not str
            or value['last_marker'] not in ('not-started', *OPERATION_MARKERS[kind])
            or type(value['stderr_present']) is not bool
            or type(value['bootstrap_phase']) is not str or value['bootstrap_phase'] not in BOOTSTRAP_PHASES
            or type(value['bootstrap_error']) is not str
            or value['bootstrap_error'] not in ('unavailable', 'none', *BOOTSTRAP_ERRORS, *MODULE_GUARD_ERRORS, *BASE_ROLE_ERRORS)):
        return fallback
    success = value['state'] == 'passed'
    reported_error = value['bootstrap_error'] in (*BOOTSTRAP_ERRORS, *MODULE_GUARD_ERRORS, *BASE_ROLE_ERRORS)
    if (success and (value['last_marker'] != 'complete' or value['bootstrap_phase'] != 'complete'
            or value['bootstrap_error'] != 'none')
            or not success and value['bootstrap_error'] == 'none'
            or reported_error and (success or value['last_marker'] != 'fixture-validated' or value['stderr_present'])
            or value['bootstrap_error'] in (*MODULE_GUARD_ERRORS, *BASE_ROLE_ERRORS) and value['bootstrap_phase'] != 'module'
            or value['bootstrap_error'] == 'unavailable' and value['bootstrap_phase'] != 'unavailable'):
        return fallback
    return dict(value)


class OperationFixture:
    marker_name = '.r19-c7-operation-control'

    def __init__(self, base=None):
        base = Path(tempfile.gettempdir() if base is None else base).absolute()
        module.guarded(base)
        self.root = Path(tempfile.mkdtemp(prefix='r19-c7-operation-', dir=base))
        self.closed = False
        self.streams = []
        # Retain from creation, even if nonce/marker/identity setup then fails.
        _UNCONFIRMED_OPERATION_FIXTURES.append(self)
        self.nonce = module.uuid.uuid4().hex
        self.marker = ('owned-c7-operation:'+self.nonce).encode('ascii')
        info = module.guarded(self.root)
        self.identity = info.st_dev, info.st_ino
        stream = (self.root/self.marker_name).open('xb')
        self.streams.append(stream)
        try:
            if stream.write(self.marker) != len(self.marker):
                raise ValueError('Authored operation fixture refused.')
        finally:
            stream.close()
            self.streams.remove(stream)
        self.validate()

    def validate(self):
        if self.streams:
            raise ValueError('Authored operation fixture refused.')
        info = module.guarded(self.root)
        if not module.stat.S_ISDIR(info.st_mode) or (info.st_dev, info.st_ino) != self.identity:
            raise ValueError('Authored operation fixture refused.')
        path = self.root/self.marker_name
        info = module.guarded(path)
        if not module.stat.S_ISREG(info.st_mode) or info.st_size != len(self.marker) or info.st_nlink != 1:
            raise ValueError('Authored operation fixture refused.')
        stream = path.open('rb')
        self.streams.append(stream)
        try:
            if stream.read(len(self.marker)+1) != self.marker:
                raise ValueError('Authored operation fixture refused.')
        finally:
            stream.close()
            self.streams.remove(stream)

    def remove_after_confirmed_cleanup(self):
        self.validate()
        # Only the fixed authored entries may be removed. Never recurse, chmod,
        # follow a link, delete an unknown entry or use an automatic destructor.
        allowed = {self.marker_name, 'data', 'io.lock'}
        if set(os.listdir(self.root))-allowed:
            raise ValueError('Authored operation fixture refused.')
        data = self.root/'data'
        if 'data' in os.listdir(self.root):
            info = module.guarded(data)
            if not module.stat.S_ISDIR(info.st_mode) or os.listdir(data):
                raise ValueError('Authored operation fixture refused.')
            data.rmdir()
        file = self.root/'io.lock'
        if 'io.lock' in os.listdir(self.root):
            info = module.guarded(file)
            if not module.stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_size != 0:
                raise ValueError('Authored operation fixture refused.')
            file.unlink()
        (self.root/self.marker_name).unlink()
        self.root.rmdir()
        self.closed = True
        _UNCONFIRMED_OPERATION_FIXTURES.remove(self)


def operation_bootstrap_control():
    # Only the exact shared fragment is caught; fixture and operation bodies
    # retain their existing behavior. Original ErrorRecord remains private.
    return "try {\n" + module.LEGACY_SYSTEM_MODULE + r'''
} catch {
    $C7BootstrapFailure=$_
    $phase='unavailable'; $category='other'
    if ($C7BootstrapPhase -is [string] -and $C7BootstrapPhase -cin @('image','paths','core','import','module','assembly','visible','complete')) {
        $phase=$C7BootstrapPhase
    }
    $exception=$C7BootstrapFailure.Exception
    for ($depth=0; $depth -lt 4 -and $null -ne $exception; $depth++) {
        if ($exception.Message -ceq 'System module close unconfirmed.') { $category='close'; break }
        if ($exception.Message -ceq 'System module refused.') { $category='guard'; break }
        if ($exception -is [Management.Automation.ParameterBindingException]) { $category='binding'; break }
        $exception=$exception.InnerException
    }
    if ($phase -ceq 'module' -and $category -ceq 'guard') {
        try {
            if ($loaded.Count -ne 1) { $category='guard-count' }
            elseif ($loaded[0] -isnot [Management.Automation.PSModuleInfo]) { $category='guard-type' }
            elseif ($loaded[0].Name -cne 'Microsoft.PowerShell.Management') { $category='guard-name' }
            elseif (-not [string]::Equals($loaded[0].Path,$manifest,[StringComparison]::OrdinalIgnoreCase)) { $category='guard-path' }
            elseif (-not [string]::Equals($loaded[0].ModuleBase,[IO.Path]::GetDirectoryName($manifest),[StringComparison]::OrdinalIgnoreCase)) { $category='guard-base' }
        } catch {
            $C7BootstrapClassificationFailure=$_
            $category='other'
        }
    }
    if ($phase -ceq 'module' -and $category -ceq 'guard-base') {
        $category='guard-base-unavailable'
        try {
            $base=$loaded[0].ModuleBase
            if ($base -is [string]) {
                if ([string]::Equals($base,$systemHome,[StringComparison]::OrdinalIgnoreCase)) { $category='guard-base-system-home' }
                elseif ([string]::Equals($base,[IO.Path]::GetDirectoryName($manifest),[StringComparison]::OrdinalIgnoreCase)) { $category='guard-base-manifest-parent' }
                else { $category='guard-base-other' }
            }
        } catch { $C7BaseRoleClassificationFailure=$_ }
    }
    [Console]::Out.WriteLine('C7B|'+$phase+'|'+$category)
    exit 2
}
'''


def operation_control_script(kind, nonce):
    if kind not in OPERATION_MARKERS or type(nonce) is not str or not module.re.fullmatch('[0-9a-f]{32}', nonce):
        raise ValueError('Authored operation source refused.')
    # No root/source/profile path is in the command. CurrentDirectory is the
    # fresh Popen cwd, validated privately by the parent before the child starts.
    script = r'''$ErrorActionPreference='Stop'
$Root=[Environment]::CurrentDirectory
if (-not [IO.Path]::IsPathRooted($Root) -or
    -not [string]::Equals([IO.Path]::GetFullPath($Root),$Root,[StringComparison]::OrdinalIgnoreCase) -or
    ([int][IO.File]::GetAttributes($Root) -band 1040) -ne 16) { throw 'Authored fixture refused.' }
$marker=[IO.Path]::Combine($Root,'.r19-c7-operation-control')
if (([int][IO.File]::GetAttributes($marker) -band 1040) -ne 0) { throw 'Authored fixture refused.' }
$expected=[Text.Encoding]::ASCII.GetBytes('owned-c7-operation:__NONCE__')
$source=[IO.File]::Open($marker,[IO.FileMode]::Open,[IO.FileAccess]::Read,[IO.FileShare]::Read)
try {
    if ($source.Length -ne $expected.Length) { throw 'Authored fixture refused.' }
    for ($index=0; $index -lt $expected.Length; $index++) {
        if ($source.ReadByte() -ne $expected[$index]) { throw 'Authored fixture refused.' }
    }
    if ($source.ReadByte() -ne -1) { throw 'Authored fixture refused.' }
} finally { $source.Dispose() }
[Console]::Out.WriteLine('C7O|fixture-validated')
'''.replace('__NONCE__', nonce) + operation_bootstrap_control()
    if kind == 'prefix':
        script += r'''[Console]::Out.WriteLine('C7O|before-join-data')
$data = Join-Path $Root 'data'
[Console]::Out.WriteLine('C7O|after-join-data')
[Console]::Out.WriteLine('C7O|before-create-directory')
New-Item -ItemType Directory -Path $data -Force | Out-Null
[Console]::Out.WriteLine('C7O|after-create-directory')
[Console]::Out.WriteLine('C7O|before-join-lock')
$path = Join-Path $data 'companion-operation.lock'
[Console]::Out.WriteLine('C7O|after-join-lock')
'''
    else:
        script += r'''$path=[IO.Path]::Combine($Root,'io.lock')
$file=$null
[Console]::Out.WriteLine('C7O|before-open')
try {
    $file=[IO.File]::Open($path,[IO.FileMode]::OpenOrCreate,[IO.FileAccess]::ReadWrite,[IO.FileShare]::None)
    [Console]::Out.WriteLine('C7O|open-returned')
} finally {
    if ($null -ne $file) { $file.Dispose(); [Console]::Out.WriteLine('C7O|closed') }
}
'''
    return script + "[Console]::Out.WriteLine('C7O|complete')\nexit 0\n"


def measure_operation_controls(executable, parent, *, run=run_grant_codec_control, make=OperationFixture):
    environment = module.legacy_environment(dict(parent))
    results = {kind: {'observation': operation_observation(kind, None, b'', b''),
        'boundary': closed_real_control_boundary(None), 'fixture': 'not-created'}
        for kind in OPERATION_MARKERS}
    for kind in OPERATION_MARKERS:
        boundary, fixture = {}, None
        value = operation_observation(kind, None, b'', b'')
        fixture_state = 'retained'
        try:
            fixture = make()
            fixture.validate()
            value = run(executable, operation_control_script(kind, fixture.nonce), dict(environment),
                diagnostic=boundary, cwd=fixture.root,
                observe=lambda code, out, err: operation_observation(kind, code, out, err))
        except Exception:
            value = operation_observation(kind, None, b'', b'')
        boundary = closed_real_control_boundary(boundary)
        if boundary['cleanup'] == 'child-exit-and-readers-finished' and fixture is not None:
            try:
                fixture.remove_after_confirmed_cleanup()
                fixture_state = 'removed-after-confirmed-cleanup'
            except Exception:
                pass  # The private fixture remains owned/retained; never retry.
        results[kind] = {'observation': closed_operation_observation(kind, value),
            'boundary': boundary, 'fixture': fixture_state}
        if boundary['cleanup'] != 'child-exit-and-readers-finished' or fixture_state == 'retained':
            break  # Never start B while A ownership or fixture cleanup is unknown.
    return results


def require_operation_controls(results):
    if (set(results) != set(OPERATION_MARKERS) or any(
            value['observation'] != {'state': 'passed', 'last_marker': 'complete', 'stderr_present': False,
                'bootstrap_phase': 'complete', 'bootstrap_error': 'none'}
            or value['boundary'] != {'refusal': 'none', 'stderr_prefix': 'empty',
                'cleanup': 'child-exit-and-readers-finished'}
            or value['fixture'] != 'removed-after-confirmed-cleanup' for value in results.values())):
        pytest.fail('Authored C7 operation controls refused: '+json.dumps(results,sort_keys=True,separators=(',',':')))


@pytest.mark.skipif(sys.platform != 'win32', reason='Protected Windows operation boundary controls unavailable locally')
def test_actual_preopen_prefix_and_separate_managed_io_under_attempt_environment():
    try: executable = module.Windows().powershell()
    except Exception: pytest.fail('Authored operation executable unavailable.')
    assert_windows_command_capacity(executable, module.LEGACY_SCRIPT.replace('__PIPE__', 'r19-lock-attribute-'+'a'*32))
    for kind in OPERATION_MARKERS:
        assert_windows_command_capacity(executable, operation_control_script(kind, 'a'*32))
    require_operation_controls(measure_operation_controls(executable, dict(os.environ)))


def operation_output(kind, *, count=None, newline=b'\r\n'):
    markers = OPERATION_MARKERS[kind] if count is None else OPERATION_MARKERS[kind][:count]
    return b''.join(('C7O|'+item).encode('ascii')+newline for item in markers)


@pytest.mark.parametrize('kind', tuple(OPERATION_MARKERS))
@pytest.mark.parametrize('mutation', ['duplicate', 'reordered', 'unknown', 'trailing', 'blank',
    'unterminated', 'partial', 'private', 'oversized', 'exit', 'stderr'])
def test_operation_markers_require_exact_order_and_complete_terminal_without_private_output(kind, mutation):
    raw = operation_output(kind); code, err = 0, b''
    if mutation == 'duplicate': raw = raw.splitlines(keepends=True)[0]+raw
    if mutation == 'reordered': raw = operation_output(kind, count=2).splitlines(keepends=True)[1]+raw
    if mutation == 'unknown': raw = b'C7O|private-unknown\n'+raw
    if mutation == 'trailing': raw += b'private-tail\n'
    if mutation == 'blank': raw += b'\n'
    if mutation == 'unterminated': raw = raw[:-2]
    if mutation == 'partial': raw = operation_output(kind, count=2)+b'C7O|priv'
    if mutation == 'private': raw = b'private-path\n'
    if mutation == 'oversized': raw += b'x'*8192
    if mutation == 'exit': code = 2
    if mutation == 'stderr': err = b'private-stderr'
    result = operation_observation(kind, code, raw, err)
    assert result['state'] == ('passed' if mutation == 'stderr' else 'unavailable')
    assert result['stderr_present'] is (mutation == 'stderr')
    assert 'priv' not in json.dumps(result)
    if mutation == 'partial': assert result['last_marker'] == OPERATION_MARKERS[kind][1]
    if mutation == 'unterminated': assert result['last_marker'] == OPERATION_MARKERS[kind][-2]


@pytest.mark.parametrize('kind', tuple(OPERATION_MARKERS))
@pytest.mark.parametrize('newline', [b'\n', b'\r\n'])
def test_operation_timeout_can_preserve_only_last_complete_marker_and_never_success(kind, newline):
    raw = operation_output(kind, count=2, newline=newline)
    assert operation_observation(kind, None, raw, b'') == {
        'state': 'unavailable', 'last_marker': OPERATION_MARKERS[kind][1], 'stderr_present': False,
        'bootstrap_phase': 'unavailable', 'bootstrap_error': 'unavailable'}
    assert operation_observation(kind, None, operation_output(kind), b'')['state'] == 'unavailable'
    assert operation_observation(kind, 0, operation_output(kind, newline=newline), b'') == {
        'state': 'passed', 'last_marker': 'complete', 'stderr_present': False,
        'bootstrap_phase': 'complete', 'bootstrap_error': 'none'}


@pytest.mark.parametrize('mutation', ['extra', 'private-marker', 'private-state', 'numeric', 'false-pass'])
def test_operation_projection_cannot_print_an_injected_private_runner_value(mutation):
    value = {'state': 'passed', 'last_marker': 'complete', 'stderr_present': False,
                'bootstrap_phase': 'complete', 'bootstrap_error': 'none'}
    if mutation == 'extra': value['raw'] = 'private-path'
    if mutation == 'private-marker': value['last_marker'] = 'private-path'
    if mutation == 'private-state': value['state'] = 'private-state'
    if mutation == 'numeric': value['stderr_present'] = 1
    if mutation == 'false-pass': value['last_marker'] = 'before-join-data'
    observed = closed_operation_observation('prefix', value)
    assert observed == {'state': 'unavailable', 'last_marker': 'not-started', 'stderr_present': False,
        'bootstrap_phase': 'unavailable', 'bootstrap_error': 'unavailable'}
    assert 'private' not in json.dumps(observed)


@pytest.mark.parametrize('mutation', ['marker-bytes', 'marker-size', 'root-link', 'marker-link', 'unknown-entry'])
def test_private_operation_fixture_refuses_changed_nonce_links_and_unknown_entries_before_cleanup(tmp_path, mutation):
    fixture = OperationFixture(tmp_path)
    marker = fixture.root/fixture.marker_name
    outside = tmp_path/'outside'; outside.mkdir()
    sentinel = outside/'sentinel'; sentinel.write_bytes(b'private-owned-outside')
    moved = None
    if mutation == 'marker-bytes': marker.write_bytes(b'x'*len(fixture.marker))
    if mutation == 'marker-size': marker.write_bytes(fixture.marker+b'x')
    if mutation == 'root-link':
        moved = fixture.root.with_name(fixture.root.name+'-moved')
        fixture.root.rename(moved); fixture.root.symlink_to(outside, target_is_directory=True)
    if mutation == 'marker-link': marker.unlink(); marker.symlink_to(sentinel)
    if mutation == 'unknown-entry': (fixture.root/'unexpected-private-file').write_bytes(b'keep')
    with pytest.raises((ValueError, module.Refused)): fixture.remove_after_confirmed_cleanup()
    assert fixture in _UNCONFIRMED_OPERATION_FIXTURES and not fixture.closed
    assert sentinel.read_bytes() == b'private-owned-outside'
    if mutation == 'unknown-entry': assert (fixture.root/'unexpected-private-file').read_bytes() == b'keep'
    # These synthetic fixtures have no process. Restore only our test mutations
    # explicitly, outside the control's deliberately non-retrying cleanup path.
    if moved:
        fixture.root.unlink(); moved.rename(fixture.root)
    if mutation == 'marker-link': marker.unlink()
    marker.write_bytes(fixture.marker)
    if mutation == 'unknown-entry': (fixture.root/'unexpected-private-file').unlink()
    fixture.remove_after_confirmed_cleanup()


@pytest.mark.parametrize('failure', ['none', 'timeout', 'stderr', 'unknown-observation', 'cleanup', 'fixture-cleanup'])
def test_operation_pair_owns_private_cwds_and_only_cleanup_uncertainty_blocks_second_child(tmp_path, failure):
    calls, fixtures = [], []
    parent = {'SystemRoot': 'authored-system', 'TEMP': str(tmp_path), 'PATH': 'private-tools'}
    before = dict(parent)
    def make():
        fixture = OperationFixture(tmp_path); fixtures.append(fixture); return fixture
    def run(executable, script, environment, *, diagnostic, cwd, observe):
        index = len(calls); fixture = fixtures[index]
        assert executable == 'authored-protected-image' and cwd == fixture.root
        assert str(cwd) not in script and str(tmp_path) not in script
        assert environment == module.legacy_environment(parent) and 'PATH' not in environment
        assert fixture.marker == ('owned-c7-operation:'+fixture.nonce).encode('ascii')
        fixture.validate(); calls.append(cwd)
        if index == 0: (cwd/'data').mkdir()
        else:
            with (cwd/'io.lock').open('xb') as stream: assert stream.write(b'') == 0
        diagnostic.update(refusal='none', stderr_prefix='empty', cleanup='child-exit-and-readers-finished')
        kind = tuple(OPERATION_MARKERS)[index]
        if index == 0 and failure == 'timeout':
            diagnostic['refusal'] = 'wait-deadline'
            return observe(None, operation_output(kind, count=2), b'')
        if index == 0 and failure == 'cleanup': diagnostic['cleanup'] = 'unconfirmed'
        if index == 0 and failure == 'fixture-cleanup': (cwd/'unknown').touch()
        if index == 0 and failure == 'unknown-observation':
            return {'state': 'private-state', 'last_marker': str(cwd), 'stderr_present': False}
        return observe(0, operation_output(kind), b'private-stderr' if index == 0 and failure == 'stderr' else b'')
    result = measure_operation_controls('authored-protected-image', parent, run=run, make=make)
    assert parent == before and len(calls) == (1 if failure in {'cleanup', 'fixture-cleanup'} else 2)
    assert len(set(calls)) == len(calls) and str(tmp_path) not in json.dumps(result)
    assert set(result) == set(OPERATION_MARKERS)
    if failure in {'cleanup', 'fixture-cleanup'}:
        assert result['managed-io']['fixture'] == 'not-created'
        assert result['managed-io']['observation']['last_marker'] == 'not-started'
    if failure == 'none': require_operation_controls(result)
    else:
        with pytest.raises(pytest.fail.Exception): require_operation_controls(result)
    for fixture in fixtures:
        if not fixture.closed:
            assert fixture.root.exists() and fixture in _UNCONFIRMED_OPERATION_FIXTURES
            if failure == 'fixture-cleanup': (fixture.root/'unknown').unlink()
            fixture.remove_after_confirmed_cleanup()  # No actual child was created by this fake.
        assert not fixture.root.exists()


def test_operation_runner_passes_private_cwd_only_to_popen_and_observes_partial_timeout(monkeypatch, tmp_path):
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    calls = []
    class Process:
        def __init__(self, command, **kwargs):
            assert str(tmp_path) not in repr(command) and kwargs['cwd'] == tmp_path
            assert kwargs['env'] == {'SystemRoot': 'authored-system'}
            self.stdout = io.BytesIO(operation_output('prefix', count=2)); self.stderr = io.BytesIO(b'')
            self.waits = 0
        def wait(self, timeout):
            calls.append(('wait', timeout)); self.waits += 1
            if self.waits == 1: raise subprocess.TimeoutExpired('private-program', timeout)
            return 0
        def kill(self): calls.append(('kill',))
    monkeypatch.setattr(subprocess, 'Popen', Process)
    boundary = {}
    result = run_grant_codec_control('authored-image', 'authored-source', {'SystemRoot': 'authored-system'},
        cwd=tmp_path, diagnostic=boundary,
        observe=lambda code, out, err: operation_observation('prefix', code, out, err))
    assert result == {'state': 'unavailable', 'last_marker': 'before-join-data', 'stderr_present': False,
        'bootstrap_phase': 'unavailable', 'bootstrap_error': 'unavailable'}
    assert boundary == {'refusal': 'wait-deadline', 'stderr_prefix': 'empty',
        'cleanup': 'child-exit-and-readers-finished'}
    assert calls == [('wait', 10), ('kill',), ('wait', 5)]


@pytest.mark.parametrize('mode', ['xb', 'rb'])
def test_operation_fixture_retains_actual_stream_on_unconfirmed_marker_close(tmp_path, monkeypatch, mode):
    original = Path.open
    streams, fixtures = [], []
    class CloseFault:
        def __init__(self, stream): self.stream, self.closes = stream, 0
        def write(self, value): return self.stream.write(value)
        def read(self, count): return self.stream.read(count)
        def close(self):
            self.closes += 1
            raise OSError('private-marker-close')
    def open_file(path, actual_mode='r', *args, **kwargs):
        stream = original(path, actual_mode, *args, **kwargs)
        if path.name == OperationFixture.marker_name and actual_mode == mode:
            value = CloseFault(stream); streams.append(value); return value
        return stream
    prior = list(_UNCONFIRMED_OPERATION_FIXTURES)
    monkeypatch.setattr(Path, 'open', open_file)
    with pytest.raises(OSError): OperationFixture(tmp_path)
    fixture = next(value for value in _UNCONFIRMED_OPERATION_FIXTURES if value not in prior)
    assert fixture.streams == streams and streams[0].closes == 1
    with pytest.raises(ValueError): fixture.remove_after_confirmed_cleanup()
    assert streams[0].closes == 1 and fixture.root.exists() and not fixture.closed
    # Explicitly release this authored injected resource; production cleanup
    # never retries an uncertain stream close or removes its fixture.
    streams[0].stream.close(); fixture.streams.clear()
    monkeypatch.setattr(Path, 'open', original)
    fixture.remove_after_confirmed_cleanup()


def assert_windows_command_capacity(executable, script):
    # Match WindowsPreparationProcess/CreateProcess quoting and UTF-16/NUL cap.
    command = [executable, '-NoProfile', '-NonInteractive', '-EncodedCommand',
        base64.b64encode(script.encode('utf-16le')).decode('ascii')]
    units = len(subprocess.list2cmdline(command).encode('utf-16le'))//2+1
    assert units <= 32767, 'Authored C7 command exceeds the Windows command-line cap.'
    return command


def test_shared_os_bootstrap_is_compact_and_leaves_legacy_operation_protocol_bytes_exact():
    fragment = module.LEGACY_SYSTEM_MODULE
    assert 0 < len(fragment) <= 6400 and fragment.isascii()
    assert module.LEGACY_SCRIPT.count(fragment) == 1
    before, after = module.LEGACY_SCRIPT.split(fragment)
    assert before.endswith("    Write-C7Checkpoint 'definitionbound'\n")
    assert after.startswith("    $state='unclassified-refusal'; $file=$null\n    Write-C7Checkpoint 'operationentered'")
    import hashlib
    assert hashlib.sha256((before+after).encode('utf-8')).hexdigest() == (
        '1369b4058e30cb7e56653fccc256301bece35d19d4613318f87fd8b71df09c2c')
    assert fragment not in grant_codec_script()
    for kind in OPERATION_MARKERS:
        script = operation_control_script(kind, 'a'*32)
        assert script.count(fragment) == 1
        assert script.index("C7O|fixture-validated") < script.index(fragment)
        assert script.index(fragment)+len(fragment) <= script.index('C7O|before-')
        assert 'Enter-CompanionOperation' not in script


def test_os_bootstrap_requires_real_core_manifest_cmdlet_and_same_protected_gac_origins():
    fragment = module.LEGACY_SYSTEM_MODULE
    required = (
        "[Environment+SpecialFolder]::System", "[Environment+SpecialFolder]::Windows",
        '$current.MainModule.FileName', '$current.Dispose()', '$C7ModuleOwners.Add($current)',
        '[void]$C7ModuleOwners.Remove($current)', "$C7ModuleErrors.Add($_)",
        'Modules\\Microsoft.PowerShell.Management\\Microsoft.PowerShell.Management.psd1',
        '[IO.Path]::GetFullPath($Path)', '[IO.File]::GetAttributes($paths[$index])', '-band 1088',
        '$Assembly.IsDynamic', '$Assembly.GlobalAssemblyCache', '$Assembly.Location',
        '[Reflection.AssemblyName]::GetAssemblyName($path).FullName -cne $Assembly.FullName',
        'Microsoft.NET\\assembly\\GAC_MSIL', 'GetPublicKeyToken()',
        "'Microsoft.PowerShell.Core\\Import-Module'", "'Microsoft.PowerShell.Core\\Get-Command'",
        "'ImportModuleCommand'", "'GetCommandCommand'", '[object]::ReferenceEquals',
        '-Name $manifest -PassThru -Scope Local -NoClobber -Cmdlet Join-Path,New-Item',
        '-Function @() -Alias @() -Variable @()', '$loaded[0].Path', '$loaded[0].ModuleBase',
        '$loaded[0].ExportedCmdlets', "'JoinPathCommand'", "'NewItemCommand'", "'OutNullCommand'",
        '-ListImported -All -CommandType Alias,Function,Filter,Cmdlet',
        '[Management.Automation.CmdletInfo]', '[Management.Automation.PSModuleInfo]',
    )
    assert all(item in fragment for item in required)
    guard = fragment.split('function Assert-C7SystemPath', 1)[1].split('function Get-C7AssemblyPath', 1)[0]
    reverse_walk = guard.index('for ($index=$paths.Count-1; $index -ge 0; $index--)')
    assert 'GetAttributes' not in guard[:reverse_walk]
    assert guard.index('$paths.Add($item)') < reverse_walk
    assert '$requiredDirectory=($index -ne 0 -or $Directory)' in guard[reverse_walk:]
    assert fragment.index('Assert-C7SystemPath $manifest $false') < fragment.index('$loaded=@(& $import')
    assert fragment.index('$current.Dispose()') < fragment.index('[void]$C7ModuleOwners.Remove($current)')
    for forbidden in ('$env:', 'PSModulePath', '-ListAvailable', '-Force', 'Import-PSSession',
            'Add-Type', 'Get-AuthenticodeSignature', '\nJoin-Path ', '\nNew-Item ', 'WriteLine', 'Write-C7Checkpoint'):
        assert forbidden not in fragment
    # These are source contracts. Only actual Windows controls execute PS guards.
    assert fragment.count('.Dispose()') == 1
    assert fragment.count('$loaded=@(& $import') == 1


@pytest.mark.parametrize('image', [
    r'S:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe',
    r'S:\Authored OS with space\WindowsPowerShell\v1.0\powershell.exe',
    'S:\\'+'界'*1000+r'\WindowsPowerShell\v1.0\powershell.exe',
])
def test_actual_legacy_and_control_command_builders_fit_windows_utf16_cap(monkeypatch, tmp_path, image):
    commands, closes = [], []
    class Attempt:
        def __init__(self, _api, command, _root, *, checkpoint_value=None):
            commands.append(command('r19-lock-attribute-'+'a'*32))
        def script_exchange(self, _value): return {'state': 'open'}
        def close(self): closes.append('close')
    monkeypatch.setattr(module, 'Attempt', Attempt)
    source_hash = module.source_bytes(module.SOURCE, module.SOURCE_HASHES)
    module.legacy(SimpleNamespace(powershell=lambda: image), tmp_path, source_hash, 'open')
    assert closes == ['close'] and len(commands) == 1
    scripts = [module.LEGACY_SCRIPT.replace('__PIPE__', 'r19-lock-attribute-'+'a'*32),
        *(operation_control_script(kind, 'a'*32) for kind in OPERATION_MARKERS)]
    assert commands[0] == assert_windows_command_capacity(image, scripts[0])
    for script in scripts:
        command = assert_windows_command_capacity(image, script)
        assert command[0] == image and command[1:4] == ['-NoProfile', '-NonInteractive', '-EncodedCommand']
        assert base64.b64decode(command[4]).decode('utf-16le') == script


def test_command_capacity_contract_counts_quoted_utf16_units_including_terminator():
    script = module.LEGACY_SCRIPT.replace('__PIPE__', 'r19-lock-attribute-'+'a'*32)
    image = 'S:\\'+'😀'*1500+r'\powershell.exe'
    command = [image, '-NoProfile', '-NonInteractive', '-EncodedCommand',
        base64.b64encode(script.encode('utf-16le')).decode('ascii')]
    assert len(subprocess.list2cmdline(command))+1 < 32767
    assert len(subprocess.list2cmdline(command).encode('utf-16le'))//2+1 > 32767
    with pytest.raises(AssertionError, match='Authored C7 command exceeds'):
        assert_windows_command_capacity(image, script)


def bootstrap_error_output(phase='import', error='binding', *, newline=b'\n'):
    return b'C7O|fixture-validated'+newline+b'C7B|'+phase.encode('ascii')+b'|'+error.encode('ascii')+newline


@pytest.mark.parametrize('phase', BOOTSTRAP_PHASES)
@pytest.mark.parametrize('error', BOOTSTRAP_ERRORS)
def test_closed_bootstrap_failure_admits_only_finite_terminal_context_and_never_success(phase, error):
    value = operation_observation('prefix', 2, bootstrap_error_output(phase,error), b'')
    assert value == {'state':'unavailable','last_marker':'fixture-validated','stderr_present':False,
        'bootstrap_phase':phase,'bootstrap_error':error}
    assert closed_operation_observation('prefix', value) == value


@pytest.mark.parametrize('kind', tuple(OPERATION_MARKERS))
@pytest.mark.parametrize('error', (*MODULE_GUARD_ERRORS, *BASE_ROLE_ERRORS))
def test_module_guard_categories_are_closed_failures_only_at_the_existing_module_phase(kind, error):
    value=operation_observation(kind,2,bootstrap_error_output('module',error),b'')
    assert value=={'state':'unavailable','last_marker':'fixture-validated','stderr_present':False,
        'bootstrap_phase':'module','bootstrap_error':error}
    assert closed_operation_observation(kind,value)==value
    forged=dict(value,state='passed',last_marker='complete')
    assert closed_operation_observation(kind,forged)['bootstrap_error']=='unavailable'
    results={name:{'observation':dict(value),'boundary':{'refusal':'protocol-refused','stderr_prefix':'empty',
        'cleanup':'child-exit-and-readers-finished'},'fixture':'removed-after-confirmed-cleanup'} for name in OPERATION_MARKERS}
    with pytest.raises(pytest.fail.Exception):require_operation_controls(results)


@pytest.mark.parametrize('phase', tuple(value for value in BOOTSTRAP_PHASES if value!='module'))
@pytest.mark.parametrize('error', (*MODULE_GUARD_ERRORS, *BASE_ROLE_ERRORS))
def test_module_guard_categories_refuse_every_other_wire_and_projected_phase(phase, error):
    observed=operation_observation('prefix',2,bootstrap_error_output(phase,error),b'')
    assert observed['bootstrap_phase']==observed['bootstrap_error']=='unavailable'
    forged={'state':'unavailable','last_marker':'fixture-validated','stderr_present':False,
        'bootstrap_phase':phase,'bootstrap_error':error}
    projected=closed_operation_observation('prefix',forged)
    assert projected['bootstrap_phase']==projected['bootstrap_error']=='unavailable'


@pytest.mark.parametrize('phase,error', [('import','binding'),('module','guard-path'),
    *(('module', error) for error in BASE_ROLE_ERRORS)])
@pytest.mark.parametrize('kind', tuple(OPERATION_MARKERS))
@pytest.mark.parametrize('mutation', ['no-fixture', 'after-operation', 'duplicate', 'trailing', 'partial-tail',
    'unknown-phase', 'unknown-error', 'extra-field', 'zero-exit', 'bool-exit', 'stderr', 'deadline',
    'unterminated', 'embedded-cr', 'bom', 'nonascii', 'phase-case', 'after-success', 'none-error',
    'future-guard', 'guard-case', 'nul'])
def test_bootstrap_failure_context_refuses_wrong_order_private_bytes_partial_and_deadline(kind, mutation, phase, error):
    raw=bootstrap_error_output(phase,error);code=2;err=b''
    if mutation=='no-fixture': raw=raw.split(b'\n',1)[1]
    if mutation=='after-operation': raw=operation_output(kind,count=2)+raw.split(b'\n',1)[1]
    if mutation=='duplicate': raw+=raw.split(b'\n',1)[1]
    if mutation=='trailing': raw+=b'\n'
    if mutation=='partial-tail': raw+=b'private unfinished'
    if mutation=='unknown-phase': raw=bootstrap_error_output('private-path','binding')
    if mutation=='unknown-error': raw=bootstrap_error_output('import','private-message')
    if mutation=='extra-field': raw=raw[:-1]+b'|private-field\n'
    if mutation=='zero-exit':code=0
    if mutation=='bool-exit':code=True
    if mutation=='stderr':err=b'private stderr'
    if mutation=='deadline':code=None
    if mutation=='unterminated':raw=raw[:-1]
    if mutation=='embedded-cr':raw=raw.replace(phase.encode('ascii'),b'im\rport')
    if mutation=='bom':raw=raw.replace(b'C7B|',b'\xef\xbb\xbfC7B|')
    if mutation=='nonascii':raw=raw.replace(phase.encode('ascii'),b'\xff')
    if mutation=='phase-case':raw=bootstrap_error_output('IMPORT','binding')
    if mutation=='after-success':raw=operation_output(kind)+raw.split(b'\n',1)[1]
    if mutation=='none-error':raw=bootstrap_error_output('import','none')
    if mutation=='future-guard':raw=bootstrap_error_output('module','guard-origin')
    if mutation=='guard-case':raw=bootstrap_error_output('module','guard-Path')
    if mutation=='nul':raw=raw[:-1]+b'\0\n'
    result=operation_observation(kind,code,raw,err)
    assert result['state']=='unavailable'
    assert result['bootstrap_phase']==result['bootstrap_error']=='unavailable'
    assert 'private' not in json.dumps(result)


@pytest.mark.parametrize('kind', tuple(OPERATION_MARKERS))
def test_bootstrap_error_frame_crlf_still_requires_joint_cleanup_and_has_no_pass_path(kind):
    value=operation_observation(kind,2,bootstrap_error_output(newline=b'\r\n'),b'')
    assert value['bootstrap_phase']=='import' and value['bootstrap_error']=='binding'
    result={name:{'observation':dict(value),'boundary':{'refusal':'protocol-refused','stderr_prefix':'empty',
        'cleanup':'child-exit-and-readers-finished'},'fixture':'removed-after-confirmed-cleanup'} for name in OPERATION_MARKERS}
    with pytest.raises(pytest.fail.Exception):require_operation_controls(result)


@pytest.mark.parametrize('field,value', [('bootstrap_phase','private-path'),('bootstrap_error','private-error'),
    ('bootstrap_phase',True),('bootstrap_error',True),('bootstrap_error','none')])
def test_bootstrap_projection_rejects_private_untyped_or_false_success_fields(field,value):
    result=operation_observation('prefix',2,bootstrap_error_output(),b'')
    result[field]=value
    observed=closed_operation_observation('prefix',result)
    assert observed['bootstrap_phase']==observed['bootstrap_error']=='unavailable'
    assert 'private' not in json.dumps(observed)


def test_phase_assignments_are_only_producer_delta_and_control_catch_has_one_closed_output():
    import hashlib,re
    fragment=module.LEGACY_SYSTEM_MODULE
    stripped=re.sub(r"^\$C7BootstrapPhase='(?:image|paths|core|import|module|assembly|visible|complete)'\n",'',fragment,flags=re.MULTILINE)
    assert hashlib.sha256(stripped.encode()).hexdigest() == '0836deb4e157e212f5c83aa8477b1df026657696f69e14d2906c142c1e36950d'
    phases=re.findall(r"^\$C7BootstrapPhase='([^']+)'$",fragment,re.MULTILINE)
    assert phases==list(BOOTSTRAP_PHASES[1:])
    wrapper=operation_bootstrap_control()
    assert wrapper.startswith('try {\n'+fragment)
    catch=wrapper[len('try {\n'+fragment):]
    assert catch.startswith('\n} catch {')
    assert '$C7BootstrapFailure=$_' in catch
    assert catch.count('[Console]::Out.WriteLine')==1
    assert "[Console]::Out.WriteLine('C7B|'+$phase+'|'+$category)" in catch
    assert 'exit 2' in catch and 'throw ' not in catch
    assert 'Write-C7Checkpoint' not in wrapper and wrapper not in module.LEGACY_SCRIPT
    for kind in OPERATION_MARKERS:
        script=operation_control_script(kind,'a'*32)
        assert script.count(wrapper)==1
        assert script.index('C7O|fixture-validated') < script.index(wrapper)
        assert script.index(wrapper)+len(wrapper) <= script.index('C7O|before-')


def test_module_failure_classifier_uses_only_original_short_circuit_metadata_and_safe_fallbacks():
    import re
    fragment=module.LEGACY_SYSTEM_MODULE
    original=fragment.split("$C7BootstrapPhase='module'\nif (",1)[1].split(") { throw 'System module refused.' }",1)[0]
    original_predicates=re.split(r'\s+-or\s+',original)
    catch=operation_bootstrap_control()[len('try {\n'+fragment):]
    classifier=catch.split("    if ($phase -ceq 'module' -and $category -ceq 'guard') {\n",1)[1]
    classifier=classifier.split("    if ($phase -ceq 'module' -and $category -ceq 'guard-base') {\n",1)[0]
    predicates=re.findall(r"(?:if|elseif) \((.*?)\) \{ \$category='(guard-[a-z]+)' \}",classifier)
    assert [value[0] for value in predicates]==original_predicates
    assert tuple(value[1] for value in predicates)==MODULE_GUARD_ERRORS
    # No final else means a changed/no-longer-failing predicate keeps guard.
    # A classifier exception retains its own ErrorRecord without replacing the
    # original bootstrap failure. These are source checks, not a PS engine run.
    assert "else {" not in classifier
    assert classifier.endswith("        } catch {\n            $C7BootstrapClassificationFailure=$_\n            $category='other'\n        }\n    }\n")
    assert catch.count('$C7BootstrapFailure=$_')==1
    assert classifier.count('$C7BootstrapClassificationFailure=$_')==1
    assert '$C7BootstrapFailure' not in classifier
    assert classifier.count("$category='")==6
    assert not any(value in classifier for value in ('WriteLine','Write-C7Checkpoint','Import-Module',
        'GetAttributes','.Open(','.Dispose(','.Location','Get-Command','exit ','throw '))


@pytest.mark.parametrize('phase,error', [('import','binding'), *(('module', error) for error in BASE_ROLE_ERRORS)])
def test_both_operation_controls_keep_closed_bootstrap_failure_and_cleanup_without_success(monkeypatch, tmp_path, phase, error):
    monkeypatch.setattr(subprocess, 'CREATE_NO_WINDOW', 0, raising=False)
    fixtures, processes = [], []
    class Process:
        def __init__(self, command, **options):
            assert options['cwd'] == fixtures[-1].root
            script=base64.b64decode(command[-1]).decode('utf-16le')
            assert script.count(operation_bootstrap_control()) == 1
            self.stdout=io.BytesIO(bootstrap_error_output(phase,error))
            self.stderr=io.BytesIO(b'')
            processes.append(self)
        def wait(self, timeout):
            assert timeout == 10
            return 2
        def kill(self): pytest.fail('A confirmed diagnostic failure must not be killed.')
    def make():
        fixture=OperationFixture(tmp_path);fixtures.append(fixture);return fixture
    monkeypatch.setattr(subprocess, 'Popen', Process)
    results=measure_operation_controls('authored-image', {'SystemRoot':'authored-system'}, make=make)
    assert len(processes)==len(fixtures)==2
    for value in results.values():
        assert value['observation']=={'state':'unavailable','last_marker':'fixture-validated',
            'stderr_present':False,'bootstrap_phase':phase,'bootstrap_error':error}
        assert value['boundary']=={'refusal':'protocol-refused','stderr_prefix':'empty',
            'cleanup':'child-exit-and-readers-finished'}
        assert value['fixture']=='removed-after-confirmed-cleanup'
    assert all(fixture.closed and not fixture.root.exists() for fixture in fixtures)
    assert all(process.stdout.closed and process.stderr.closed for process in processes)
    assert str(tmp_path) not in json.dumps(results)
    with pytest.raises(pytest.fail.Exception):require_operation_controls(results)


def test_base_role_projection_is_exact_control_only_text_and_has_no_new_origin_or_io():
    import hashlib,re
    assert BASE_ROLE_ERRORS == ('guard-base-system-home', 'guard-base-manifest-parent',
        'guard-base-other', 'guard-base-unavailable')
    wrapper=operation_bootstrap_control()
    start=wrapper.index("    if ($phase -ceq 'module' -and $category -ceq 'guard-base') {\n")
    end=wrapper.index("    [Console]::Out.WriteLine('C7B|'+$phase+'|'+$category)",start)
    role=wrapper[start:end]
    assert len(role)==633 and role.count('$base=$loaded[0].ModuleBase')==1
    assert re.findall(r"\$category='([^']+)'",role)==[BASE_ROLE_ERRORS[-1],*BASE_ROLE_ERRORS[:3]]
    assert "if ($base -is [string])" in role
    assert "[string]::Equals($base,$systemHome,[StringComparison]::OrdinalIgnoreCase)" in role
    assert "[string]::Equals($base,[IO.Path]::GetDirectoryName($manifest),[StringComparison]::OrdinalIgnoreCase)" in role
    assert role.endswith("        } catch { $C7BaseRoleClassificationFailure=$_ }\n    }\n")
    assert '$C7BootstrapFailure' not in role
    assert not any(value in role for value in ('WriteLine','Import-Module','Get-Command',
        'GetAttributes','.Open(','.Dispose(','.Location','GetFullPath','Trim','exit ','throw '))
    # This is the complete prior wrapper, including original classifier and
    # terminal. Removing only the role block must preserve its exact bytes.
    assert hashlib.sha256(wrapper.replace(role,'',1).encode()).hexdigest()==(
        'fcb26a0d3c73368a8a5acf33d4e970e5887bbeac58dd51c547deb1341cfbdb21')
    assert len(module.LEGACY_SYSTEM_MODULE)==6194
    assert wrapper not in module.LEGACY_SCRIPT and role not in module.LEGACY_SCRIPT


def test_control_only_base_role_projection_fits_original_windows_command_transport():
    image=r'C:\Windows\System32\WindowsPowerShell\v1.0\powershell.exe'
    expected={'prefix':26694,'managed-io':26470}
    for kind, units in expected.items():
        script=operation_control_script(kind,'a'*32)
        command=assert_windows_command_capacity(image,script)
        assert len(subprocess.list2cmdline(command).encode('utf-16le'))//2+1==units
        assert script.count("[Console]::Out.WriteLine('C7B|'+$phase+'|'+$category)")==1
    # The actual Windows test also checks its protected executable before
    # either control. This conventional path is a portable text-only fixture.
    legacy=module.LEGACY_SCRIPT.replace('__PIPE__','r19-lock-attribute-'+'a'*32)
    command=assert_windows_command_capacity(image,legacy)
    assert len(subprocess.list2cmdline(command).encode('utf-16le'))//2+1==31126


@pytest.mark.parametrize('error', BASE_ROLE_ERRORS)
@pytest.mark.parametrize('field,value', [('state','passed'),('last_marker','complete'),
    ('stderr_present',True),('bootstrap_phase','visible'),('bootstrap_error',True),
    ('bootstrap_error',{'private':'untyped'}),('private','private-value')])
def test_base_role_projection_refuses_wrong_state_private_untyped_or_other_phase(error, field, value):
    observed=operation_observation('prefix',2,bootstrap_error_output('module',error),b'')
    forged=dict(observed);forged[field]=value
    result=closed_operation_observation('prefix',forged)
    assert result['bootstrap_phase']==result['bootstrap_error']=='unavailable'
    assert 'private' not in json.dumps(result)
