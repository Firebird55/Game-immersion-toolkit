import asyncio
import threading
import time
import sys
import json
from types import SimpleNamespace
import pytest

from fastapi.testclient import TestClient

from backend.runtime_handoff import CaptureHandoff
from backend.runtime_workers import RequestBarrier, ResumableExecutor, WriterBarrierMiddleware
from backend.tests.test_subtitle_capture import fixture_service


@pytest.fixture
def candidate_binding(monkeypatch):
    from backend import api
    from backend.runtime_writers import RuntimeWriterGate
    monkeypatch.setenv('PROXY_TRANSCRIPT_STANDBY', '1')
    monkeypatch.setattr(api.app.router, 'lifespan_context', api.lifespan)
    monkeypatch.setattr(api.app, 'middleware_stack', None)
    monkeypatch.setattr(api.app, 'user_middleware', list(api.app.user_middleware))
    monkeypatch.setitem(api.app.state._state, '_candidate_writer_gate', None)
    return api, RuntimeWriterGate(closed_candidate=True)


@pytest.mark.parametrize('changed', ['built-stack', 'duplicate-writer', 'missing-writer', 'changed-order'])
def test_candidate_configuration_refuses_changed_middleware_without_partial_binding(candidate_binding, changed):
    api, gate = candidate_binding
    source_order = list(api.app.user_middleware)
    if changed == 'built-stack': api.app.middleware_stack = object()
    if changed == 'duplicate-writer': api.app.user_middleware.append(source_order[3])
    if changed == 'missing-writer': api.app.user_middleware.pop(3)
    if changed == 'changed-order': api.app.user_middleware[:2] = source_order[1::-1]
    before = tuple(api.app.user_middleware)
    with pytest.raises(RuntimeError): api.closed_candidate_app(gate)
    assert tuple(api.app.user_middleware) == before
    assert api.app.router.lifespan_context is api.lifespan and api.app.state._candidate_writer_gate is None


@pytest.mark.parametrize('changed', ['replaced-record-no-runtime', 'replaced-record-open-gate',
    'original-record-changed-callback', 'positional-argument', 'list-arguments', 'extra-keyword',
    'missing-keyword', 'dict-subclass'])
def test_candidate_configuration_refuses_same_class_writer_or_argument_rebinding_before_effects(candidate_binding, monkeypatch, changed):
    from starlette.middleware import Middleware
    from backend.runtime_writers import RuntimeWriterGate, RuntimeWriterMiddleware
    api, gate = candidate_binding
    original = api.app.user_middleware[3]
    assert original is api._RUNTIME_WRITER_MIDDLEWARE
    assert original.kwargs['current_runtime'] is api._RUNTIME_WRITER_CALLBACK
    constructor_calls, handler_calls = [], []
    def constructor(**_options): constructor_calls.append('Runtime'); pytest.fail('Changed middleware constructed Runtime')
    monkeypatch.setattr(api, 'Runtime', constructor)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(request_writers=gate, _candidate_writer_gate=gate,
        capture=SimpleNamespace(start=lambda: handler_calls.append('capture'))), raising=False)
    callback = lambda: SimpleNamespace(request_writers=RuntimeWriterGate())
    if changed.startswith('replaced-record'):
        alternate = (lambda: None) if changed == 'replaced-record-no-runtime' else callback
        api.app.user_middleware[3] = Middleware(RuntimeWriterMiddleware, current_runtime=alternate)
    if changed == 'original-record-changed-callback': monkeypatch.setitem(original.kwargs, 'current_runtime', callback)
    if changed == 'positional-argument': monkeypatch.setattr(original, 'args', (callback,))
    if changed == 'list-arguments': monkeypatch.setattr(original, 'args', [])
    if changed == 'extra-keyword': monkeypatch.setitem(original.kwargs, 'other_runtime', callback)
    if changed == 'missing-keyword': monkeypatch.delitem(original.kwargs, 'current_runtime')
    if changed == 'dict-subclass':
        class AlteredKeywords(dict): pass
        monkeypatch.setattr(original, 'kwargs', AlteredKeywords(original.kwargs))
    before = tuple(api.app.user_middleware)
    with pytest.raises(RuntimeError, match='writer middleware binding changed'):
        with TestClient(api.closed_candidate_app(gate), base_url='http://127.0.0.1:18767') as client:
            client.post('/api/capture/start')
    assert constructor_calls == handler_calls == []
    assert tuple(api.app.user_middleware) == before
    assert api.app.router.lifespan_context is api.lifespan and api.app.state._candidate_writer_gate is None


@pytest.mark.parametrize('changed', ['same-class-no-runtime', 'same-class-open-gate', 'original-record-callback'])
def test_candidate_lifespan_rechecks_original_writer_binding_before_constructors(candidate_binding, monkeypatch, changed):
    from starlette.middleware import Middleware
    from backend.runtime_writers import RuntimeWriterGate, RuntimeWriterMiddleware
    api, gate = candidate_binding
    app = api.closed_candidate_app(gate)
    original = app.user_middleware[1]
    constructor_calls, handler_calls = [], []
    def constructor(**_options): constructor_calls.append('Runtime'); pytest.fail('Changed startup constructed Runtime')
    monkeypatch.setattr(api, 'Runtime', constructor)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(request_writers=gate, _candidate_writer_gate=gate,
        capture=SimpleNamespace(start=lambda: handler_calls.append('capture'))), raising=False)
    callback = (lambda: None) if changed == 'same-class-no-runtime' else lambda: SimpleNamespace(request_writers=RuntimeWriterGate())
    if changed.startswith('same-class'):
        app.user_middleware[1] = Middleware(RuntimeWriterMiddleware, current_runtime=callback)
    else:
        monkeypatch.setitem(original.kwargs, 'current_runtime', callback)
    with pytest.raises(RuntimeError, match='writer middleware binding changed'):
        with TestClient(app, base_url='http://127.0.0.1:18767') as client:
            client.post('/api/capture/start')
    assert constructor_calls == handler_calls == []
    assert gate.closed_candidate and not gate._accepting


def test_candidate_lifespan_rejects_late_equal_record_without_calling_equality(candidate_binding, monkeypatch):
    from starlette.middleware import Middleware
    from backend.runtime_writers import RuntimeWriterGate, RuntimeWriterMiddleware
    api, gate = candidate_binding
    app = api.closed_candidate_app(gate)
    equality_calls, constructor_calls, handler_calls = [], [], []
    class EqualMiddleware(Middleware):
        def __eq__(self, other):
            equality_calls.append(other)
            return True
    other_runtime = SimpleNamespace(request_writers=RuntimeWriterGate())
    original = app.user_middleware[1]
    app.user_middleware[1] = EqualMiddleware(RuntimeWriterMiddleware, current_runtime=lambda: other_runtime)
    assert app.user_middleware[1] is not original
    def constructor(**_options): constructor_calls.append('Runtime'); pytest.fail('Equal record constructed Runtime')
    monkeypatch.setattr(api, 'Runtime', constructor)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(request_writers=gate, _candidate_writer_gate=gate,
        status=lambda: handler_calls.append('status')), raising=False)
    with pytest.raises(RuntimeError, match='writer middleware binding changed'):
        with TestClient(app, base_url='http://127.0.0.1:18767') as client:
            client.get('/api/status')
    assert equality_calls == constructor_calls == handler_calls == []
    assert gate.closed_candidate and not gate._accepting


@pytest.mark.parametrize('invalid', ['missing', 'wrong-type', 'ordinary-gate', 'no-standby'])
def test_candidate_configuration_rejects_invalid_gate_before_any_runtime_constructor(candidate_binding, monkeypatch, invalid):
    from backend.runtime_writers import RuntimeWriterGate
    api, gate = candidate_binding
    monkeypatch.setattr(api, 'Runtime', lambda **_: pytest.fail('Invalid startup constructed Runtime'))
    if invalid == 'missing': gate = None
    if invalid == 'wrong-type': gate = SimpleNamespace(closed_candidate=True)
    if invalid == 'ordinary-gate': gate = RuntimeWriterGate()
    if invalid == 'no-standby': monkeypatch.delenv('PROXY_TRANSCRIPT_STANDBY')
    with pytest.raises(RuntimeError, match='exact closed gate and standby'):
        api.closed_candidate_app(gate)


@pytest.mark.parametrize('replacement', ['missing', 'none', 'wrong-type', 'ordinary-gate', 'other-closed-gate'])
def test_candidate_lifespan_refuses_lost_binding_without_open_runtime_fallback(candidate_binding, monkeypatch, replacement):
    from backend.runtime_writers import RuntimeWriterGate
    api, gate = candidate_binding
    app = api.closed_candidate_app(gate)
    bound = app.router.lifespan_context
    monkeypatch.setattr(api, 'Runtime', lambda **_: pytest.fail('Lost binding constructed Runtime'))
    values = {'none': None, 'wrong-type': object(), 'ordinary-gate': RuntimeWriterGate(),
              'other-closed-gate': RuntimeWriterGate(closed_candidate=True)}
    if replacement == 'missing': del app.state._candidate_writer_gate
    else: app.state._candidate_writer_gate = values[replacement]
    async def run():
        with pytest.raises(RuntimeError, match='gate binding changed'):
            async with bound(app): pytest.fail('Lost binding admitted a lifespan')
    asyncio.run(run())


def test_candidate_default_lifespan_cannot_drop_its_explicit_gate(candidate_binding, monkeypatch):
    api, gate = candidate_binding
    app = api.closed_candidate_app(gate)
    monkeypatch.setattr(api, 'Runtime', lambda **_: pytest.fail('Missing gate constructed an open Runtime'))
    async def run():
        with pytest.raises(RuntimeError, match='binding is missing'):
            async with api.lifespan(app): pytest.fail('Missing gate admitted a lifespan')
    asyncio.run(run())


def test_candidate_lifespan_refuses_runtime_replacing_exact_gate_before_warmup(candidate_binding, monkeypatch):
    from backend.runtime_writers import RuntimeWriterGate
    api, gate = candidate_binding
    app = api.closed_candidate_app(gate)
    def constructor(*, candidate_gate):
        assert candidate_gate is gate
        return SimpleNamespace(request_writers=RuntimeWriterGate(), _candidate_writer_gate=gate)
    monkeypatch.setattr(api, 'Runtime', constructor)
    async def run():
        with pytest.raises(RuntimeError, match='Runtime gate binding changed'):
            async with app.router.lifespan_context(app): pytest.fail('Wrong Runtime gate admitted a lifespan')
    asyncio.run(run())


@pytest.mark.parametrize('invalid', ['ordinary-gate', 'wrong-type', 'no-standby'])
def test_candidate_runtime_rejects_invalid_gate_before_service_construction(monkeypatch, invalid):
    from backend import api
    from backend.runtime_writers import RuntimeWriterGate
    monkeypatch.setenv('PROXY_TRANSCRIPT_STANDBY', '1')
    monkeypatch.setattr(api, 'ToolkitUpdater', lambda *_: pytest.fail('Invalid gate reached a service constructor'))
    gate = RuntimeWriterGate(closed_candidate=True)
    if invalid == 'ordinary-gate': gate = RuntimeWriterGate()
    if invalid == 'wrong-type': gate = object()
    if invalid == 'no-standby': monkeypatch.delenv('PROXY_TRANSCRIPT_STANDBY')
    with pytest.raises(RuntimeError, match='exact closed gate and standby'): api.Runtime(candidate_gate=gate)


def test_real_candidate_lifespan_keeps_same_closed_gate_during_warmup_and_after_ready(tmp_path, candidate_binding, monkeypatch):
    """Real owned stores/lifespan + ASGI; native OCR and all accounts are authored."""
    import httpx
    from starlette.websockets import WebSocketDisconnect
    from backend.accounts import AccountStore
    from backend.lexirise import LexiriseService
    from backend.runtime_writers import RuntimeWriterGate, WritersQuiescing
    api, gate = candidate_binding
    entered, release, finished = threading.Event(), threading.Event(), threading.Event()
    instances, constructor_checks, forbidden = [], [], []
    original, toolkit = api.Runtime, api.ToolkitUpdater
    class ObservedRuntime(original):
        def __new__(cls, **_options):
            value = super().__new__(cls); instances.append(value); return value
    def first_service(root):
        value = instances[0]
        assert value.request_writers is gate and value._candidate_writer_gate is gate and value.standby
        with pytest.raises(WritersQuiescing): value.request_writers.capture_ticket()
        constructor_checks.append('closed-before-first-service')
        return toolkit(root)
    def reject_remote(request):
        pytest.fail('A closed candidate attempted a remote account operation')
    transport = httpx.MockTransport(reject_remote)
    def protect(*_args, **_options): pytest.fail('Authored candidate reached DPAPI')
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path/'profile'))
    monkeypatch.setenv('PROXY_TRANSCRIPT_PROJECT_ROOT', str(tmp_path))
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path/'data')
    monkeypatch.setattr(api, 'RUNTIME_LAYOUT', api.discover_layout())
    monkeypatch.setattr(api, 'Runtime', ObservedRuntime)
    monkeypatch.setattr(api, 'ToolkitUpdater', first_service)
    monkeypatch.setattr(api, 'AccountStore', lambda: AccountStore(tmp_path/'profile/accounts.dpapi', protect=protect, transport=transport))
    monkeypatch.setattr(api, 'LexiriseService', lambda directory, **options: LexiriseService(
        directory, **options, api_key='lx_authored_candidate_test_only', transport=transport))
    monkeypatch.setattr(api.HitoTextIndex, 'ensure_game_files', lambda *_: None)
    async def warm(_capture):
        def work():
            entered.set()
            try: assert release.wait(5)
            finally: finished.set()
        await asyncio.to_thread(work)
    monkeypatch.setattr(api.CaptureService, 'warmup', warm)
    original_order = tuple(api.app.user_middleware)
    app = api.closed_candidate_app(gate)
    assert tuple(app.user_middleware) == (original_order[0], original_order[3], original_order[1], original_order[2], *original_order[4:])
    with pytest.raises(RuntimeError, match='already bound'): api.closed_candidate_app(gate)
    paths = [('POST','/api/capture/start'), ('POST','/api/ingest'), ('GET','/api/setup'),
             ('GET','/api/status'), ('GET','/api/lines/1/reading'), ('GET','/api/mobile-export/zzz'),
             ('PATCH','/api/lexirise/settings'), ('POST','/api/runtime/quiesce?writers=true'),
             ('POST','/api/runtime/activate?writers=true')]
    try:
        with TestClient(app, base_url='http://127.0.0.1:18767') as client:
            current = instances[0]
            assert constructor_checks == ['closed-before-first-service']
            assert api.runtime is current and current.request_writers is gate and entered.wait(1)
            assert not current.warm_task.done() and not current.capture.snapshot().running
            assert client.get('/api/health').json() == {'status':'ok'}
            assert client.get('/api/runtime/ready').json() == {'ready':False,'standby':True}
            for _ in range(2):
                for method, path in paths:
                    response = client.request(method, path, content=b'invalid JSON must not reach body validation',
                                              headers={'X-Proxy-Transcript':'update'})
                    assert response.status_code == 503 and response.headers['Retry-After'] == '1'
                preflight = client.options('/api/capture/start', headers={'Origin':'http://127.0.0.1:3000',
                    'Access-Control-Request-Method':'POST', 'Access-Control-Request-Headers':'x-proxy-transcript'})
                assert preflight.status_code == 503 and preflight.headers['Retry-After'] == '1'
                assert client.options('/api/health', headers={'Origin':'http://127.0.0.1:3000',
                    'Access-Control-Request-Method':'GET'}).status_code == 200
                with client.websocket_connect('/api/ws', headers={'Host':'127.0.0.1:18767'}) as socket:
                    with pytest.raises(WebSocketDisconnect) as closed: socket.receive_json()
                assert closed.value.code == 1013 and current.hub.clients == set()
                with pytest.raises(WebSocketDisconnect) as denied:
                    with client.websocket_connect('/api/ws', headers={'Host':'127.0.0.1:18767','Origin':'https://example.test'}):
                        pytest.fail('Untrusted candidate WebSocket accepted')
                assert denied.value.code == 1008
                assert not current.warm_task.done() and not current.warm_task.cancelled()
                assert not current._updates_started and current.request_writers is gate
            # Activation must refuse before all pool, SQL, capture and reader effects.
            def effect(*_args, **_options): forbidden.append('effect'); pytest.fail('Closed candidate reopened work')
            monkeypatch.setattr(current.capture, 'start', effect)
            monkeypatch.setattr(current.capture, 'import_handoff', effect)
            monkeypatch.setattr(current.capture, 'resume_workers', effect)
            monkeypatch.setattr(current._reading_registry, 'reopen_creation', effect)
            monkeypatch.setattr(current._reading_registry, 'resume_pools', effect)
            async def activation():
                for strict in (False, True):
                    with pytest.raises(WritersQuiescing): await current.activate_handoff(CaptureHandoff(running=True), writers=strict)
            client.portal.call(activation)
            for operation in (current.activate_workers, current.admit_requests, current.resume_writers, current._resume_writer_pools,
                              lambda: current._resume_sql_handoff(time.monotonic()+1), current.start_updates, gate.resume):
                with pytest.raises(WritersQuiescing): operation()
            assert forbidden == [] and not current._updates_started
            # Replacing the actual request gate is refusal, never an open fallback.
            current.request_writers = RuntimeWriterGate()
            assert client.get('/api/health').status_code == 503
            with client.websocket_connect('/api/ws', headers={'Host':'127.0.0.1:18767'}) as socket:
                with pytest.raises(WebSocketDisconnect) as closed: socket.receive_json()
            assert closed.value.code == 1013
            with pytest.raises(WritersQuiescing): current.admit_requests()
            current.request_writers = gate
            release.set()
            async def await_warm(): await asyncio.wait_for(asyncio.shield(current.warm_task), 2)
            client.portal.call(await_warm)
            assert finished.is_set() and client.get('/api/runtime/ready').json() == {'ready':True,'standby':True}
            assert client.post('/api/runtime/activate', json={'running':True}, headers={'X-Proxy-Transcript':'update'}).status_code == 503
            assert not current.capture.snapshot().running and forbidden == []
        assert instances[0].request_writers is gate
        with pytest.raises(WritersQuiescing): gate.resume()
    finally:
        release.set()


def test_closed_candidate_websocket_rejects_before_hub_or_status_access(monkeypatch):
    from backend import api
    from backend.runtime_writers import RuntimeWriterGate
    from starlette.websockets import WebSocketDisconnect
    # Missing hub/status deliberately makes any pre-admission access fail.
    gate = RuntimeWriterGate(closed_candidate=True)
    monkeypatch.setattr(api, 'runtime', SimpleNamespace(request_writers=gate, _candidate_writer_gate=gate), raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:18767')
    with client.websocket_connect('/api/ws', headers={'Host':'127.0.0.1:18767'}) as socket:
        with pytest.raises(WebSocketDisconnect) as closed: socket.receive_json()
    assert closed.value.code == 1013


def test_real_runtime_initializes_standby_without_starting_capture_or_updates(tmp_path, monkeypatch):
    from backend import api
    monkeypatch.setenv('LOCALAPPDATA', str(tmp_path))
    monkeypatch.setenv('PROXY_TRANSCRIPT_PROJECT_ROOT', str(tmp_path))
    monkeypatch.setenv('PROXY_TRANSCRIPT_STANDBY', '1')
    monkeypatch.setattr(api, 'RUNTIME_LAYOUT', api.discover_layout())
    monkeypatch.setattr(api, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(api, 'DATA_DIR', tmp_path / 'data')
    monkeypatch.setattr(api.HitoTextIndex, 'ensure_game_files', lambda *_: None)
    async def run():
        runtime = api.Runtime()
        try:
            assert runtime.standby and not runtime._updates_started
            assert runtime.request_barrier.paused and not runtime.request_writers._accepting
            assert runtime.warm_task is None and runtime.index_task is None
            assert not runtime.capture.snapshot().running
        finally:
            await runtime.capture.close()
            runtime._reading_registry.shutdown(time.monotonic()+2)
            runtime.voice_assets.close()
            runtime.pragmata_voice_assets.close()
            for voices in runtime.game_voice_assets.values():
                voices.close()
    asyncio.run(run())


def test_handoff_preserves_session_and_duplicate_suppression(tmp_path):
    old, match, _, _ = fixture_service(tmp_path / 'old')
    fresh, _, _, _ = fixture_service(tmp_path / 'fresh')
    fresh.transcript = old.transcript
    old.transcript.add(match, old.session_id)
    old._can_emit('dialogue\0'+match.text_id+'\0'+match.english, time.monotonic())
    try:
        state = CaptureHandoff.model_validate(old.export_handoff(True).model_dump())
        fresh.import_handoff(state)
        assert fresh.session_id == old.session_id
        assert not fresh._can_emit('cinematic\0'+match.text_id+'\0'+match.english, time.monotonic())
        assert fresh._can_emit('dialogue\0another-line\0A new sentence.', time.monotonic())
        assert old.transcript.count() == 1
    finally:
        old._executor.shutdown()
        fresh._executor.shutdown()


def test_quiescing_capture_drains_native_work_before_exporting_state(tmp_path):
    capture, _, _, _ = fixture_service(tmp_path)
    entered, release = threading.Event(), threading.Event()
    def native_work():
        entered.set()
        assert release.wait(3)
    capture._executor.submit(native_work)
    assert entered.wait(1)
    async def run():
        capture._task = asyncio.create_task(asyncio.sleep(100))
        stopping = asyncio.create_task(capture.stop())
        await asyncio.sleep(.03)
        assert not stopping.done()
        assert capture._scan_epoch == 1
        release.set()
        assert await stopping
    try:
        asyncio.run(run())
    finally:
        release.set()
        capture._executor.shutdown()


def test_runtime_activation_requires_local_action_and_ready_candidate(monkeypatch):
    from backend import api
    calls = []
    capture = SimpleNamespace(native_stop_pending=False, snapshot=lambda: SimpleNamespace(running=False),
        import_handoff=lambda state: calls.append(('import', state.session_id)), start=lambda: calls.append('capture'))
    fake = SimpleNamespace(textmaps=SimpleNamespace(ready=True), pragmata=None, hito=None,
        game_indexes={}, warm_task=SimpleNamespace(done=lambda: False), standby=True,
        accounts=SimpleNamespace(status=lambda: {'active': 'account-one'}),
        languages=SimpleNamespace(selected=lambda *_: 'zh-Hans', prepared=lambda *_: {'targets': ['en']}),
        language_state=lambda *_: {'ready': True},
        capture=capture, start_updates=lambda: calls.append('updates'))
    fake._handoff_lock, fake._writer_handoff, fake._handoff_drains = asyncio.Lock(), False, []
    fake._sql_handoff = None
    fake._handoff_until = lambda deadline: api.Runtime._handoff_until(fake, deadline)
    fake._handoff_step = lambda operation, deadline, **options: api.Runtime._handoff_step(fake, operation, deadline, **options)
    fake._prepare_recovery_requests = lambda deadline: None
    fake._pin_request_stop = lambda: None  # This fixture isolates HTTP action/readiness.
    fake._pause_outer_requests = lambda: asyncio.sleep(0)
    fake._resume_sql_handoff = lambda deadline: None
    fake._resume_writer_pools = lambda deadline: None
    fake._clear_handoff_drains = lambda: None
    fake.request_barrier = RequestBarrier()
    fake._check_owned_drain = lambda: None
    fake.resume_writers = lambda: None
    fake.admit_requests = lambda deadline: None
    fake.activate_handoff = lambda payload, **options: api.Runtime.activate_handoff(fake, payload, **options)
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    assert not client.get('/api/runtime/ready?game=zzz').json()['ready']
    assert client.post('/api/runtime/activate', json={'running': True}).status_code == 403
    headers = {'X-Proxy-Transcript': 'update'}
    assert client.post('/api/runtime/activate', headers=headers, json={'running': True}).status_code == 409
    assert calls == []
    fake.warm_task = None
    response = client.post('/api/runtime/activate', headers=headers, json={'running': True, 'session_id': 'same-session'})
    assert response.status_code == 200
    assert calls == [('import', 'same-session'), 'capture', 'updates']


def test_standby_readiness_uses_only_the_active_accounts_prepared_language(monkeypatch):
    from backend import api
    states = []
    selected = {'account-one': 'nl', 'account-two': 'fr'}
    prepared = {('beyond', 'nl'): {'targets': ['zh-hans']}}
    active = ['account-one']
    ready = [True]
    def language_state(game, locale):
        states.append((game, locale))
        return {'ready': ready[0]}
    fake = SimpleNamespace(textmaps=None, pragmata=None, hito=SimpleNamespace(ready=True),
        game_indexes={'beyond': SimpleNamespace(ready=False)}, warm_task=None, standby=True,
        accounts=SimpleNamespace(status=lambda: {'active': active[0]}),
        languages=SimpleNamespace(selected=lambda game, account: selected.get(account),
                                  prepared=lambda game, locale: prepared.get((game, locale))),
        language_state=language_state)
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    assert client.get('/api/runtime/ready?game=beyond').json() == {'ready': True, 'standby': True}
    assert states == [('beyond', 'nl')]
    ready[0] = False
    assert not client.get('/api/runtime/ready?game=beyond').json()['ready']
    active[0] = 'account-two'
    fake.game_indexes['beyond'].ready = True
    states.clear()
    assert not client.get('/api/runtime/ready?game=beyond').json()['ready']
    assert states == []  # Never fall back to another account or prepare French.
    active[0] = 'legacy-account-without-selection'
    assert client.get('/api/runtime/ready?game=beyond').json()['ready']
    fake.game_indexes['beyond'].source_locale = 'nl'
    assert not client.get('/api/runtime/ready?game=beyond').json()['ready']
    assert states == []
    assert client.get('/api/runtime/ready?game=hito').json()['ready']
    assert not client.get('/api/runtime/ready?game=unknown').json()['ready']


@pytest.mark.parametrize('query', ['', '?writers=true'])
def test_public_handoff_drains_all_writers_before_capture_transfer(monkeypatch, query):
    from backend import api
    from backend.runtime_writers import RuntimeWriterGate, WritersQuiescing
    calls, running = [], [True]
    async def stop_updates(**_options):
        assert running[0]
        calls.append('updates')
    async def stop_capture(_timeout):
        calls.append('capture')
        running[0] = False
    fake = api.Runtime.__new__(api.Runtime)
    fake._request_stop = None
    fake.standby, fake._quiesce_task, fake._handoff_state = False, None, None
    fake._writer_handoff, fake._handoff_lock, fake._handoff_drains = False, asyncio.Lock(), []
    fake.request_barrier, fake.request_writers = RequestBarrier(), RuntimeWriterGate()
    fake.stop_updates = stop_updates
    fake._sql_handoff = None
    fake._freeze_sql_handoff = lambda payload, deadline: payload  # Producer-order fixture, not SQL authority.
    fake.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=running[0]), quiesce=stop_capture,
        export_handoff=lambda active: CaptureHandoff(running=active, session_id='continued'))
    fake.mobile_exports = SimpleNamespace(drain=lambda: calls.append('manual-exports'))
    fake.automatic_exports = SimpleNamespace(picker=SimpleNamespace(drain=lambda: calls.append('automatic-picker')))
    fake.installation = SimpleNamespace(pause=lambda: calls.append('setup-pause'),
        quiesce=lambda _timeout: calls.append('setup'))
    fake._reading_registry = SimpleNamespace(stop_creation=lambda _deadline: calls.append('reader-admission'),
        quiesce_owned=lambda _deadline: calls.append('reading'))
    fake.capture.drain_publications = lambda: asyncio.sleep(0)
    fake.map_task = None
    fake.hito = SimpleNamespace(close=lambda: calls.append('hito'))
    fake._voice_pools = lambda: []
    fake._verify_background_stopped = lambda: None
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    client = TestClient(api.app, base_url='http://127.0.0.1:8767')
    response = client.post('/api/runtime/quiesce'+query, headers={'X-Proxy-Transcript': 'update'})
    assert response.status_code == 200, response.text
    assert response.json()['running'] and response.json()['session_id'] == 'continued'
    assert fake.standby and not running[0]
    with pytest.raises(WritersQuiescing):
        fake.request_writers.enter()
    assert calls == ['reader-admission', 'manual-exports', 'automatic-picker', 'setup-pause',
                     'setup', 'updates', 'reading', 'capture', 'hito']


def test_explicit_capture_only_experiment_does_not_claim_writer_drain():
    from backend import api
    from backend.runtime_writers import RuntimeWriterGate
    calls = []
    old = api.Runtime.__new__(api.Runtime)
    old._handoff_lock, old._writer_handoff = asyncio.Lock(), False
    old.request_writers, old.standby = RuntimeWriterGate(), False
    async def stop_updates(): calls.append('updates')
    async def stop_capture(): calls.append('capture')
    old.stop_updates = stop_updates
    old.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True), stop=stop_capture,
        export_handoff=lambda active: CaptureHandoff(running=active, session_id='experiment'))
    state = asyncio.run(old.quiesce_capture_handoff())
    assert state.running and state.session_id == 'experiment'
    old.request_writers.enter(); old.request_writers.leave()
    assert calls == ['updates', 'capture'] and not old._writer_handoff


def test_legacy_activation_cannot_bypass_explicit_strict_handoff():
    from backend.api import Runtime
    async def run():
        old = Runtime.__new__(Runtime)
        old._handoff_lock, old._writer_handoff = asyncio.Lock(), True
        with pytest.raises(TimeoutError, match='explicit writers protocol'):
            await old.activate_handoff(CaptureHandoff(running=True))
        with pytest.raises(TimeoutError, match='explicit writers protocol'):
            await old.quiesce_capture_handoff()
    asyncio.run(run())


def test_pool_drain_waits_for_pending_work_and_cache_completion_callback():
    # A cancelled asyncio Future and an empty replacement queue both missed
    # callbacks writing dictionaries/audio in the retiring runtime.
    pool = ResumableExecutor(max_workers=1)
    entered, release, callback, finish = (threading.Event() for _ in range(4))
    writes = []
    def work():
        entered.set()
        assert release.wait(3)
    def completed(_):
        callback.set()
        assert finish.wait(3)
        writes.append('cache')
    first = pool.submit(work)
    first.add_done_callback(completed)
    second = pool.submit(lambda: writes.append('queued'))
    assert entered.wait(1)
    drain = threading.Thread(target=pool.drain)
    drain.start()
    try:
        with pytest.raises(RuntimeError):
            pool.submit(lambda: None)
        release.set()
        assert callback.wait(1)
        drain.join(.03)
        assert drain.is_alive() and writes == []
        finish.set()
        drain.join(2)
        assert not drain.is_alive() and writes == ['cache', 'queued']
        assert second.done()
        pool.resume()
        assert pool.submit(lambda: 'resumed').result(1) == 'resumed'
    finally:
        release.set(); finish.set()
        drain.join(3)
        pool.shutdown()


def test_request_barrier_counts_get_through_response_completion():
    async def run():
        gate = RequestBarrier()
        entered, release = asyncio.Event(), asyncio.Event()
        messages = []
        async def app(scope, receive, send):
            await send({'type': 'http.response.start', 'status': 200, 'headers': []})
            entered.set()
            await release.wait()  # A streaming response still owns its cache work.
            await send({'type': 'http.response.body', 'body': b'done'})
        async def send(message):
            messages.append(message)
        middleware = WriterBarrierMiddleware(app, lambda: gate)
        scope = {'type': 'http', 'path': '/api/lines/1/reading', 'method': 'GET'}
        first = asyncio.create_task(middleware(scope, None, send))
        await entered.wait()
        drain = asyncio.create_task(gate.pause())
        await asyncio.sleep(0)
        await middleware(scope, None, send)
        assert messages[-2]['status'] == 503 and not drain.done()
        release.set()
        await first; await drain
        gate.resume()
        assert gate.enter()
        gate.leave()
    asyncio.run(run())


def test_cancelled_handoff_waiter_does_not_release_actual_workers(tmp_path):
    capture, _, _, _ = fixture_service(tmp_path)
    retired = ResumableExecutor(max_workers=1)
    entered, release = threading.Event(), threading.Event()
    def old_scan():
        entered.set()
        assert release.wait(5)
    retired.submit(old_scan)
    assert entered.wait(1)
    capture._retired_executors.append(retired)
    async def run():
        waiter = asyncio.create_task(capture.stop())
        await asyncio.sleep(.03)
        waiter.cancel()
        with pytest.raises(asyncio.CancelledError):
            await waiter
        with pytest.raises(RuntimeError, match='previous scan'):
            capture.start()
        assert not capture._stop_task.done()
        release.set()
        await capture.stop()
        assert capture._retired_executors == []
    try:
        asyncio.run(run())
    finally:
        release.set()
        retired.shutdown(); capture._executor.shutdown()


def test_handoff_timeout_keeps_drain_alive_and_blocks_activation(monkeypatch):
    from backend import api
    from starlette.requests import Request
    from fastapi import HTTPException
    fake = object.__new__(api.Runtime)
    fake._request_stop = None
    fake._handoff_lock = asyncio.Lock()
    fake._sql_handoff = None
    fake.request_barrier = RequestBarrier()
    fake._quiesce_task = None
    fake._handoff_state = None
    fake.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True),
        export_handoff=lambda running: CaptureHandoff(running=running, session_id='same-session'))
    monkeypatch.setattr(api, 'runtime', fake, raising=False)
    monkeypatch.setattr(api, 'HANDOFF_TIMEOUT_SECONDS', .01)
    request = Request({'type': 'http', 'method': 'POST', 'path': '/api/runtime/quiesce',
                       'headers': [], 'server': ('127.0.0.1', 8766), 'scheme': 'http', 'query_string': b''})
    async def run():
        release = asyncio.Event()
        fake._drain_workers = release.wait
        with pytest.raises(HTTPException) as failure:
            await api.runtime_quiesce(request, 'update')
        assert failure.value.status_code == 503
        assert not fake._quiesce_task.done()
        with pytest.raises(RuntimeError, match='still stopping'):
            fake.activate_workers()
        release.set()
        monkeypatch.setattr(api, 'HANDOFF_TIMEOUT_SECONDS', 1)
        result = await api.runtime_quiesce(request, 'update')
        assert result['running'] and result['session_id'] == 'same-session'
    asyncio.run(run())


@pytest.mark.parametrize('writers', [False, True])
def test_public_timeout_retains_actual_outer_request_pause_and_does_not_resume_early(monkeypatch, writers):
    from backend import api
    from starlette.requests import Request
    from fastapi import HTTPException
    from backend.runtime_writers import RuntimeWriterGate, RuntimeWriterMiddleware
    current = api.Runtime.__new__(api.Runtime)
    current._request_stop = None
    current._handoff_lock = asyncio.Lock()
    current._quiesce_task = current._handoff_state = None
    current._sql_handoff = None
    current.request_barrier, current.request_writers = RequestBarrier(), RuntimeWriterGate()
    current.capture = SimpleNamespace(snapshot=lambda: SimpleNamespace(running=True),
        export_handoff=lambda running: CaptureHandoff(running=running, session_id='retained-stream'))
    monkeypatch.setattr(api, 'runtime', current, raising=False)
    monkeypatch.setattr(api, 'HANDOFF_TIMEOUT_SECONDS', .01)
    request = Request({'type':'http', 'method':'POST', 'path':'/api/runtime/quiesce', 'headers':[],
        'server':('127.0.0.1',8766), 'scheme':'http', 'query_string':b''})
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()
        producer_calls = []
        async def stream(scope, receive, send):
            entered.set()
            await release.wait()
        async def send(_message): pass
        async def receive(): return {'type':'http.request'}
        async def producers(*, timeout):
            # This adapter isolates the genuine outer request pause. SQL/real
            # producer cohorts are covered by the separate composition tests.
            assert current.request_barrier.paused and current.request_barrier._active == 0
            producer_calls.append(timeout)
            current.request_writers.stop_admission()
        current.quiesce_writers = producers
        middleware = WriterBarrierMiddleware(RuntimeWriterMiddleware(stream, lambda: current), lambda: current.request_barrier)
        streaming = asyncio.create_task(middleware({'type':'http','path':'/api/lines/1/reading'}, receive, send))
        await entered.wait()
        try:
            with pytest.raises(HTTPException) as refusal:
                await api.runtime_quiesce(request, 'update', writers=writers)
            assert refusal.value.status_code == 503
            owned = current._quiesce_task
            assert not owned.done() and current.request_barrier.paused and current.request_barrier._active == 1
            assert producer_calls == []
            for operation in (current.activate_workers, current.resume_writers, current.admit_requests):
                with pytest.raises(RuntimeError, match='still stopping'): operation()
            assert current._quiesce_task is owned and current.request_barrier.paused
        finally:
            release.set()
            await streaming
        await asyncio.wait_for(asyncio.shield(owned), 1)
        assert producer_calls == [threading.TIMEOUT_MAX]
        assert current.request_barrier.paused and not current.request_writers._accepting
        result = await api.runtime_quiesce(request, 'update', writers=writers)
        assert result['running'] and result['session_id'] == 'retained-stream'
        assert current._quiesce_task is owned and len(producer_calls) == 1
    asyncio.run(run())


def test_export_drain_stops_decoder_left_after_export_parent_exits(tmp_path):
    # Exercise the export manager's actual ownership, not merely the process
    # wrapper: otherwise a clean parent exit could skip descendant cleanup.
    import psutil
    from backend.mobile_export_controls import MobileExportManager
    marker = tmp_path / 'decoder.json'
    script = '''import subprocess, sys, json
from pathlib import Path
p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'],
    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
Path(sys.argv[1]).write_text(json.dumps({'pid': p.pid}))
print(json.dumps({'state': 'complete', 'progress': 100}), flush=True)
'''
    manager = MobileExportManager(tmp_path)
    manager._worker_args = lambda *_: [sys.executable, '-c', script, str(marker)]
    manager._thread = threading.Thread(target=manager._run, args=('zzz', False, tmp_path))
    manager._thread.start()
    manager._thread.join(15)
    manager.drain()
    assert not manager._thread.is_alive()
    assert manager.status()['state'] == 'complete'
    assert not psutil.pid_exists(json.loads(marker.read_text())['pid'])
