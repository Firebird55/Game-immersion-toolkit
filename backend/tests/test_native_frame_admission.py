"""Slow OCR may confirm exact captions only while real scoped images keep arriving."""
import json
import uuid

import pytest

from backend.native_frame_admission import MAX_RECEIPTS, NativeFrameAdmissions, NativeFrameReceipt
from backend.prepared_session import PreparedCaptureSession
from backend.tests.test_android_host import host, request
from backend.tests.test_android_receiver import control
from backend.tests.test_android_account_http import account_host, register, headers as account_headers
from backend.tests.test_prepared_session import fixture_library


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


class Scope:
    pass


def binding(*, document='a' * 32, account=0, receiver=None, revision=1):
    return document, account, (receiver or '11111111-1111-4111-8111-111111111111', revision)


def prepared(tmp_path):
    archive, payload = fixture_library(tmp_path / 'input')
    session = PreparedCaptureSession(tmp_path / 'application');session.import_library(archive)
    session.start()
    return session, payload['records'][0]['source_text']


def advance(ledger, clock, session, first, last, *, scope=None):
    for sequence in range(first, last + 1):
        clock.now = (sequence - 1) / 2
        ledger.admit(session, session.generation, sequence, scope or binding())


def observe(ledger, clock, session, sequence, text, *, scope=None, **options):
    with ledger.result(session, session.generation, sequence, scope or binding()) as receipt:
        assert receipt is not None
        return session.observe(session.generation, sequence, [text], now=clock.now, admission=receipt, **options)


def test_serialized_four_second_ocr_confirms_only_with_live_authenticated_admissions(tmp_path):
    session, text = prepared(tmp_path);clock = Clock();ledger = NativeFrameAdmissions(clock=clock)
    advance(ledger, clock, session, 1, 9)  # First image finishes after four seconds.
    assert observe(ledger, clock, session, 1, text) == []
    advance(ledger, clock, session, 10, 17)  # Newest queued image also takes four seconds.
    lines = observe(ledger, clock, session, 9, text)
    assert len(lines) == 1 and lines[0]['text_id'] == 'owned:line'
    assert lines[0]['audio_source'] == 'original' and session.audio_path(lines[0]['id']).is_file()


def test_no_receipt_keeps_three_second_gap_and_boolean_cannot_enable_exception(tmp_path):
    session, text = prepared(tmp_path)
    assert session.observe(session.generation, 1, [text], now=4) == []
    assert session.observe(session.generation, 9, [text], now=8) == []
    with pytest.raises(ValueError, match='opaque'):
        session.observe(session.generation, 10, [text], now=8.1, admission=True)
    assert len(session.observe(session.generation, 11, [text], now=8.2)) == 1


@pytest.mark.parametrize('change', ['gap', 'document', 'account', 'receiver', 'revision', 'session', 'generation'])
def test_old_callback_cannot_cross_admission_or_owner_scope(change):
    session = Scope();clock = Clock();ledger = NativeFrameAdmissions(clock=clock)
    scope = binding();generation = 1
    ledger.admit(session, generation, 1, scope)
    current = session
    if change == 'gap': clock.now = 4
    elif change == 'document': scope = binding(document='b' * 32)
    elif change == 'account': scope = binding(account=2)
    elif change == 'receiver': scope = binding(receiver=str(uuid.uuid4()))
    elif change == 'revision': scope = binding(revision=2)
    elif change == 'session': current = Scope()
    elif change == 'generation': generation = 2
    ledger.admit(current, generation, 2, scope)
    with ledger.result(session, 1, 1, binding()) as receipt:
        assert receipt is None
    # An old callback cannot pop an equally numbered current-scope receipt.
    with ledger.result(current, generation, 2, scope) as receipt:
        assert receipt is not None


def test_receipts_are_bounded_one_use_unforgeable_and_revoked_after_pause():
    session = Scope();clock = Clock();ledger = NativeFrameAdmissions(clock=clock);scope = binding()
    for sequence in range(1, MAX_RECEIPTS + 2): ledger.admit(session, 1, sequence, scope)
    assert len(ledger._pending) == MAX_RECEIPTS
    with ledger.result(session, 1, 1, scope) as receipt: assert receipt is None
    with ledger.result(session, 1, 999, scope) as receipt: assert receipt is None
    with ledger.result(session, 1, 2, scope) as receipt:
        key = receipt.authorize(session, 1, 2)
        forged = NativeFrameReceipt(ledger, key, 2, clock.now)
        with pytest.raises(ValueError): forged.authorize(session, 1, 2)
    with pytest.raises(ValueError): receipt.authorize(session, 1, 2)
    with ledger.result(session, 1, 2, scope) as replay: assert replay is None
    with ledger.result(session, 1, 3, scope) as receipt:
        ledger.reset()
        with pytest.raises(ValueError): receipt.authorize(session, 1, 3)


def test_recent_liveness_and_bounded_callback_age_are_both_required():
    session = Scope();clock = Clock();ledger = NativeFrameAdmissions(clock=clock)
    ledger.admit(session, 1, 1, binding());clock.now = 4
    with ledger.result(session, 1, 1, binding()) as receipt: assert receipt is None
    clock.now = 0;ledger.reset();ledger.admit(session, 1, 1, binding())
    for sequence in range(2, 39):
        clock.now = sequence - 1;ledger.admit(session, 1, sequence, binding())
    with ledger.result(session, 1, 1, binding()) as receipt: assert receipt is None


@pytest.mark.parametrize('mode', ['real_gap', 'unleased', 'menu', 'fuzzy_before', 'fuzzy_after'])
def test_live_frames_cannot_preserve_menu_fuzzy_or_disconnected_confirmation(tmp_path, mode):
    session, text = prepared(tmp_path);clock = Clock();ledger = NativeFrameAdmissions(clock=clock)
    scope = (*binding()[:2], None) if mode == 'unleased' else binding()
    fuzzy = 'Follow the river beyond the bridgo.'
    assert session.index.match_line_groups([fuzzy], session.settings.get().fuzzy_threshold)[0].kind == 'fuzzy'
    advance(ledger, clock, session, 1, 9, scope=scope)
    assert not observe(ledger, clock, session, 1, fuzzy if mode == 'fuzzy_before' else text, scope=scope)
    if mode == 'real_gap':
        clock.now = 8;ledger.admit(session, session.generation, 17, scope)
        second = 17
    else:
        advance(ledger, clock, session, 10, 17, scope=scope);second = 9
    assert not observe(ledger, clock, session, second, fuzzy if mode == 'fuzzy_after' else text,
        scope=scope, dialogue_menu=mode == 'menu')
    assert session.history.count() == 0


def test_long_completion_gap_retires_publisher_predecessor_contexts(tmp_path):
    session, text = prepared(tmp_path);clock = Clock();ledger = NativeFrameAdmissions(clock=clock)
    advance(ledger, clock, session, 1, 9);observe(ledger, clock, session, 1, text)
    predecessor = object();floating = object()
    session.contexts[('dialogue', 'cinematic')] = predecessor
    session.floating_contexts['old'] = floating
    session.nte_context.anchor = 'old-native-graph-anchor'
    advance(ledger, clock, session, 10, 17);observe(ledger, clock, session, 9, text)
    assert predecessor not in session.contexts.values() and floating not in session.floating_contexts.values()
    assert session.nte_context.anchor is None


def test_live_images_do_not_keep_a_short_authored_tutorial_successor_armed(tmp_path):
    from backend.tests.test_endfield_layout_context import step_rows
    from backend.tests.test_prepared_capture_parity import prepared as prepare_rows
    session = prepare_rows(tmp_path, step_rows());session.update_settings({'capture_unvoiced': True});session.start()
    clock = Clock();ledger = NativeFrameAdmissions(clock=clock)
    anchor = 'Keep performing the authored training sequence.'
    advance(ledger, clock, session, 1, 9)
    assert not observe(ledger, clock, session, 1, anchor, channel='fullframe')
    advance(ledger, clock, session, 10, 10)
    assert observe(ledger, clock, session, 9, anchor, channel='fullframe')
    advance(ledger, clock, session, 11, 25)
    assert not observe(ledger, clock, session, 17, 'Wait!', channel='fullframe')
    advance(ledger, clock, session, 26, 26)
    assert not observe(ledger, clock, session, 25, 'Wait!', channel='fullframe')


class NativeDimensions:
    def submit(self, raw, generation, sequence, locale):
        assert raw.startswith(b'\x89PNG')
        return json.dumps({'width': 1600, 'height': 240})


def test_real_http_admission_and_native_callbacks_use_same_one_use_lease(host, tmp_path, monkeypatch):
    from backend import prepared_session
    session_archive, payload = fixture_library(tmp_path / 'input')
    host.session.import_library(session_archive)
    host.session.update_settings({'region': {'left': 0, 'top': 0, 'width': 1, 'height': 1}})
    host.native = NativeDimensions();clock = Clock();host.frame_admissions = NativeFrameAdmissions(clock=clock)
    monkeypatch.setattr(prepared_session.time, 'monotonic', clock)
    identity = str(uuid.uuid4());_, active = control(host, identity, 1, 'start');generation = active['generation']
    def admit(sequence):
        clock.now = (sequence - 1) / 2
        assert request(host, 'POST', '/api/capture/frame', b'\x89PNG-authored-dimensions-fixture', headers={
            'Content-Type': 'image/png', 'X-Toolkit-Document-Epoch': host.document_epoch,
            'X-Toolkit-Receiver-Id': identity, 'X-Toolkit-Receiver-Revision': '1',
            'X-Toolkit-Generation': str(generation), 'X-Toolkit-Frame': str(sequence)})[0] == 202
    raw = json.dumps({'width': 1600, 'height': 240,
        'blocks': [{'text': payload['records'][0]['source_text'], 'rect': [40, 70, 1200, 145]}]})
    for sequence in range(1, 10): admit(sequence)
    assert host.accept_ocr(generation, 1, raw) == []
    assert host.accept_ocr(generation, 999, 'unknown callbacks must not be parsed') == []
    for sequence in range(10, 18): admit(sequence)
    emitted = host.accept_ocr(generation, 9, raw)
    assert len(emitted) == 1
    assert host.accept_ocr(generation, 9, 'replayed callbacks must not be parsed') == []
    assert host.session.audio_path(emitted[0]['id']).is_file()
    host.pause()
    assert host.accept_ocr(generation, 17, 'paused callbacks must not be parsed') == []
    assert not host.frame_admissions._pending


@pytest.mark.parametrize('change', ['pause', 'rotation', 'settings', 'library', 'document', 'stop', 'session'])
def test_host_scope_changes_fence_already_admitted_native_callbacks(host, tmp_path, change):
    from backend.models import CaptureRegion
    archive, _ = fixture_library(tmp_path / 'input');host.session.import_library(archive)
    host.native = NativeDimensions();identity = str(uuid.uuid4())
    _, active = control(host, identity, 1, 'start');generation = active['generation']
    assert host.submit_frame(b'\x89PNG-fixture', generation, 1, identity, '1', host.document_epoch)[1] == 202
    if change == 'pause': host.pause()
    elif change == 'rotation':
        host.native.submit = lambda *args: json.dumps({'width': 240, 'height': 1600})
        assert host.submit_frame(b'\x89PNG-fixture', generation, 2, identity, '1', host.document_epoch)[1] == 409
    elif change == 'settings': host.session.update_settings({'region': CaptureRegion(left=0, top=0, width=1, height=1).model_dump()})
    elif change == 'library':
        newer, _ = fixture_library(tmp_path / 'update', text='The next update contains another complete sentence.')
        host.session.import_library(newer)
    elif change == 'document': host.replace_document()
    elif change == 'stop': assert control(host, identity, 2, 'stop')[0] == 200
    elif change == 'session':
        replacement, _ = prepared(tmp_path / 'other-account')
        replacement.generation = generation;host._session = replacement
    assert host.accept_ocr(generation, 1, 'obsolete OCR must not be parsed') == []


def test_real_account_switch_and_return_revoke_native_callback_receipts(account_host, tmp_path):
    host = account_host
    first = register(host, 'first')
    archive, _ = fixture_library(tmp_path / 'first-library')
    host.session.import_library(archive)
    host.native = NativeDimensions()
    identity = str(uuid.uuid4())
    status, active = request(host, 'POST', '/api/capture/receiver', json.dumps({
        'id': identity, 'revision': 1, 'action': 'start',
        'expected_generation': host.session.generation}).encode(),
        headers={**account_headers(host), 'X-Toolkit-Document-Epoch': host.document_epoch})
    assert status == 200
    generation = active['generation']
    assert host.submit_frame(b'\x89PNG-fixture', generation, 1, identity, '1', host.document_epoch)[1] == 202
    old_session = host.session
    old_account_generation = host.account_generation
    register(host, 'second')
    assert host.session is not old_session and host.account_generation > old_account_generation
    assert host.accept_ocr(generation, 1, 'other owner callback must not be parsed') == []
    assert request(host, 'POST', '/api/lexirise/accounts/select',
        json.dumps({'id': first}).encode(), headers=account_headers(host))[0] == 200
    assert host.account_generation > old_account_generation
    assert host.accept_ocr(generation, 1, 'returned owner callback must not be parsed') == []
    assert not host.frame_admissions._pending
