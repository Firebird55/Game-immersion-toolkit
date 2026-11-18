import base64
import hashlib
import json
from collections import deque
from types import SimpleNamespace

import pytest

from backend.android_zzz_catalogue import AndroidCatalogueReader, CHUNK, IDENTITY, run_stage
from backend.game_data_protocol import GameDataError


class AuthoredTicket:
    def __init__(self, events):
        self.events = deque([dict(type='started', identity=IDENTITY), *events])
        self.sent = []
        self.cancelled = False

    def poll(self, interval):
        assert interval == 250
        return json.dumps(self.events.popleft())

    def send(self, raw):
        assert len(raw) <= 33_000
        self.sent.append(json.loads(raw))

    def cancel(self):
        self.cancelled = True


def input_digest(root):
    source = root / 'design-1.blk'
    content = b'P' * CHUNK + b'author'
    source.write_bytes(content)
    return {'design-1.blk': hashlib.sha256(content).hexdigest()}


def authored(root, events, *, mode='text', check=lambda: None):
    ticket = AuthoredTicket(events)
    ctx = SimpleNamespace(game='zzz', directory=root, request=SimpleNamespace(content_mode=mode), check=check)
    calls = []
    def begin(operation, spec):
        calls.append((operation, json.loads(spec)))
        return ticket
    worker = SimpleNamespace(proof=lambda: IDENTITY, begin=begin)
    return ctx, worker, ticket, calls


def read_source():
    return [{'type':'read', 'id':1, 'name':'design-1.blk'}, {'type':'pull', 'id':1}, {'type':'pull', 'id':1}]


def write_output(name, identifier, content):
    return [{'type':'write', 'id':identifier, 'name':name, 'size':len(content)},
            {'type':'chunk', 'id':identifier, 'data':base64.b64encode(content).decode()}]


def test_stage_moves_only_scoped_bytes_and_returns_a_complete_pending_directory(tmp_path):
    receipts = input_digest(tmp_path)
    spec = {'design':['design-1.blk'], 'locales':['ja'], 'includeAudio':False}
    files = {'catalogue-output.json': b'{"stage":true}', 'voice-directory.json': b'null\n',
             'links.json': b'[]\n', 'texts-ja.json': b'{}\n'}
    events = read_source()
    for identifier, (name, content) in enumerate(files.items(), start=2):
        events.extend(write_output(name, identifier, content))
    ctx, worker, ticket, calls = authored(tmp_path, events + [{'type':'complete'}])
    published = tmp_path / 'existing-library.json'
    published.write_text('previous generation')

    staged = run_stage(worker, 'catalogue', spec, tmp_path, receipts, ctx)

    assert calls == [('catalogue', spec)]
    assert staged.parent == tmp_path and staged != tmp_path
    assert {path.name:path.read_bytes() for path in staged.iterdir()} == files
    assert ticket.sent[0] == dict(type='input', id=1, size=CHUNK + 6, sha256=receipts['design-1.blk'])
    assert [base64.b64decode(row['data']) for row in ticket.sent[1:3]] == [b'P' * CHUNK, b'author']
    assert ticket.cancelled and published.read_text() == 'previous generation'


@pytest.mark.parametrize('failed_event', [
    {'type':'failed'},
    {'type':'complete'},
    {'type':'read', 'id':3, 'name':'another-1.blk'},
    {'type':'write', 'id':3, 'name':'audio-resource.flex', 'size':1},
])
def test_failed_or_incomplete_stage_drops_pending_files_and_keeps_previous_library(tmp_path, failed_event):
    receipts = input_digest(tmp_path)
    spec = {'design':['design-1.blk'], 'locales':['ja'], 'includeAudio':False}
    events = read_source() + write_output('links.json', 2, b'[]\n') + [failed_event]
    ctx, worker, ticket, _ = authored(tmp_path, events)
    previous = tmp_path / 'previous-generation'
    previous.write_bytes(b'old')

    with pytest.raises(GameDataError):
        run_stage(worker, 'catalogue', spec, tmp_path, receipts, ctx)

    assert previous.read_bytes() == b'old'
    assert ticket.cancelled and not list(tmp_path.glob('zzz-catalogue-*'))


def test_scope_cancellation_stops_worker_and_removes_only_pending_stage(tmp_path):
    receipts = input_digest(tmp_path)
    events = read_source() + write_output('scene-plan-output.json', 2, b'{}\n') + [{'type':'complete'}]
    def check():
        if ticket.sent and ticket.sent[-1] == {'type':'pull', 'id':2}:
            raise GameDataError('preparation_cancelled', 'Game preparation stopped.', 409)
    ctx, worker, ticket, _ = authored(tmp_path, events, check=check)

    with pytest.raises(GameDataError, match='Game preparation stopped'):
        run_stage(worker, 'scene-plan', {'design':['design-1.blk']}, tmp_path, receipts, ctx)

    assert ticket.cancelled and not list(tmp_path.glob('zzz-catalogue-*'))


def test_reader_binds_verified_input_and_places_only_expected_output_in_workspace(tmp_path, monkeypatch):
    from backend import android_zzz_catalogue
    work = tmp_path / 'work'
    work.mkdir()
    receipts = input_digest(work)
    events = read_source() + write_output('scene-plan-output.json', 2, b'{"owned":true}') + [{'type': 'complete'}]
    ctx, worker, ticket, _ = authored(tmp_path, events)
    native = object()

    def capability(owner):
        assert owner is native
        return worker

    monkeypatch.setattr(android_zzz_catalogue, 'create_android_catalogue', capability)
    reader = AndroidCatalogueReader(native)
    reader.run_operation('scene-plan', {'design': ['design-1.blk']}, work, ctx)
    assert ticket.sent[0]['sha256'] == receipts['design-1.blk']
    assert json.loads((work / 'scene-plan-output.json').read_bytes()) == {'owned': True}
    assert set(path.name for path in work.iterdir()) == {'design-1.blk', 'scene-plan-output.json'}
    assert not list(tmp_path.glob('zzz-catalogue-*'))


@pytest.mark.parametrize('spec', [
    {'includeAudio':True, 'locales':['ja']},
    {'includeAudio':False, 'locales':['ja'], 'voiceDirectory':['1.blk.voice-directory']},
    {'includeAudio':False, 'locales':['ja'], 'design':['../design-1.blk']},
])
def test_invalid_role_fails_before_native_execution(tmp_path, spec):
    ctx, worker, _, calls = authored(tmp_path, [])
    with pytest.raises(GameDataError):
        run_stage(worker, 'catalogue', spec, tmp_path, {}, ctx)
    assert not calls and not list(tmp_path.glob('zzz-catalogue-*'))
