"""Actual HTTP cancellation/epoch boundaries; no native capture or accounts.

Middleware-only and gate unit tests cannot observe an explicit asyncio worker
outliving its request. These cases exercise both actual handlers/ASGI dispatch
with owned SQLite/index data and Event-controlled provider doubles.
"""
import asyncio
from concurrent.futures import ThreadPoolExecutor
import json
import threading
from types import SimpleNamespace

import httpx
from PIL import Image
import pytest

from backend import accounts, api, capture as capture_module, lexirise
from backend.capture import CaptureService
from backend.runtime_writers import RuntimeWriterGate
from backend.storage import TranscriptStore
from backend.textmaps import TextMapIndex, TEXTMAP_URLS


TEXT = 'A synthetic spoken sentence.'
CHINESE = '一句合成台词。'
RETRY = 'Runtime handoff is stopping writers. Retry after activation or recovery.'
REGION = {'left': 0, 'top': 0, 'width': 1, 'height': 1, 'picture_area': 'window'}


@pytest.fixture
def owned(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        pytest.fail('Owned HTTP worker tests must not access native capture, accounts or network.')

    monkeypatch.setattr(api, 'Runtime', forbidden)
    monkeypatch.setattr(accounts.AccountStore, '_read', forbidden)
    monkeypatch.setattr(accounts.AccountStore, '_write', forbidden)
    monkeypatch.setattr(lexirise, '_protect', forbidden)
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', forbidden)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', forbidden)
    directory = tmp_path/'owned-textmaps'
    directory.mkdir()
    for name in TEXTMAP_URLS:
        content = {} if name.endswith('overwrite') else {
            'Dialog_Authored': TEXT if name.startswith('en') else CHINESE}
        (directory/(name+'.json')).write_text(json.dumps(content, ensure_ascii=False), encoding='utf-8')
    index = TextMapIndex(directory)
    index.load()
    gate = RuntimeWriterGate()
    state = SimpleNamespace(gate=gate, index=index, store=TranscriptStore(tmp_path/'owned-transcript.db'),
        published=[], match_calls=[], preview_calls=[], entries=[], leaves=[], threshold=82)
    enter, leave = gate.enter, gate.leave

    def observed_enter(*args):
        enter(*args)
        state.entries.append((threading.get_ident(), bool(args)))

    def observed_leave():
        state.leaves.append(threading.get_ident())
        leave()

    monkeypatch.setattr(gate, 'enter', observed_enter)
    monkeypatch.setattr(gate, 'leave', observed_leave)
    original_match = index.match_text

    def match(text, threshold):
        state.match_calls.append((text, threshold))
        return original_match(text, threshold)

    monkeypatch.setattr(index, 'match_text', match)

    class Background:
        def __init__(self):
            self.frames = self.closes = 0

        def frame(self, _window):
            self.frames += 1
            return Image.new('RGB', (100, 100))

        def close(self):
            self.closes += 1

    capture = object.__new__(CaptureService)
    capture.settings = SimpleNamespace(get=lambda: SimpleNamespace(fuzzy_threshold=state.threshold))
    capture.session_id = 'owned-before-match'
    capture._window_frame = threading.local()
    capture._preview_lock = threading.RLock()
    capture._preview = b'owned-cached-preview'
    capture._background_capture = state.background = Background()
    capture._capture = lambda _bounds: Image.new('RGB', (100, 100))
    original_preview = capture.preview_for_region

    def preview(region, picture_area):
        state.preview_calls.append((region, picture_area))
        return original_preview(region, picture_area)

    capture.preview_for_region = preview
    monkeypatch.setattr(capture_module, 'find_active_game_window', lambda _settings:
        (SimpleNamespace(id='zzz'), SimpleNamespace(bounds=(0, 0, 100, 100))))

    async def on_line(line):
        state.published.append(line)

    state.runtime = SimpleNamespace(request_writers=gate, textmaps=index, transcript=state.store,
        settings=capture.settings, capture=capture, on_line=on_line,
        accounts=SimpleNamespace(lock=threading.RLock(), status=forbidden, active_key=forbidden),
        lexirise=SimpleNamespace(_key=forbidden))
    state.forbidden = forbidden
    monkeypatch.setattr(api, 'runtime', state.runtime, raising=False)
    return state


async def _request(kind, *, text=TEXT, params=None):
    # ASGITransport does not run lifespan; api.Runtime is also forbidden above.
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=api.app),
        base_url='http://127.0.0.1:8766', headers={'Origin': 'http://127.0.0.1:3000'}) as client:
        if kind == 'preview':
            return await client.get('/api/capture/preview.jpg', params=REGION if params is None else params)
        return await client.post('/api/ingest', json={'text': text})


async def _direct(kind):
    if kind == 'preview':
        return await api.capture_preview(**REGION)
    return await api.manual_ingest(api.ManualIngest(text=TEXT))


async def _event(event):
    await asyncio.wait_for(event.wait(), 2)


async def _cancel(task):
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


def _calls(state, kind):
    return state.preview_calls if kind == 'preview' else state.match_calls


def _hold_operation(state, kind, monkeypatch, loop):
    entered, finished, release = asyncio.Event(), asyncio.Event(), threading.Event()
    target = state.runtime.capture if kind == 'preview' else state.index
    name = 'preview_for_region' if kind == 'preview' else 'match_text'
    original = getattr(target, name)

    def held(*args):
        loop.call_soon_threadsafe(entered.set)
        try:
            assert release.wait(5), 'Authored worker was not released.'
            return original(*args)
        finally:
            loop.call_soon_threadsafe(finished.set)

    monkeypatch.setattr(target, name, held)
    return entered, finished, release


@pytest.mark.parametrize('kind', ['preview', 'ingest'])
def test_cancelled_http_waiter_keeps_actual_worker_admitted_through_resource_work(owned, monkeypatch, kind):
    state, gate = owned, owned.gate

    async def run():
        entered, finished, release = _hold_operation(state, kind, monkeypatch, asyncio.get_running_loop())
        task = asyncio.create_task(_request(kind))
        try:
            await _event(entered)
            assert gate._active == 2  # ASGI request and the actual worker.
            await _cancel(task)
            gate.stop_admission()
            assert gate._active == 1 and not finished.is_set()
            with pytest.raises(TimeoutError):
                gate.wait_drained(0)
            assert _calls(state, kind) == [] and state.background.closes == 0
            release.set()
            await _event(finished)
            gate.wait_drained(1)
            assert gate._active == 0 and len(_calls(state, kind)) == 1
            assert len(state.entries) == len(state.leaves) == 2
            worker, = [thread for thread, ticketed in state.entries if ticketed]
            assert worker != threading.get_ident() and state.leaves.count(worker) == 1
            assert state.store.count() == 0 and state.published == []
            if kind == 'ingest':
                assert state.index._cache  # Real matcher completed; no post-cancel SQL continuation.
            else:
                assert state.background.frames == 1
                state.background.close()  # Test provider cleanup only, after actual drain.
                assert state.background.closes == 1
        finally:
            release.set()
            if not task.done():
                await _cancel(task)
            await _event(finished)
            gate.wait_drained(1)

    asyncio.run(run())


@pytest.mark.parametrize('kind', ['preview', 'ingest'])
@pytest.mark.parametrize('error_type', [RuntimeError, asyncio.CancelledError])
def test_worker_error_or_worker_cancellation_leaves_exactly_once_and_propagates(owned, monkeypatch, kind, error_type):
    state, gate = owned, owned.gate
    failure = error_type('Authored worker fault.')
    target = state.runtime.capture if kind == 'preview' else state.index
    name = 'preview_for_region' if kind == 'preview' else 'match_text'
    called = []

    def fail(*_args):
        called.append(threading.get_ident())
        raise failure

    monkeypatch.setattr(target, name, fail)

    async def run():
        with pytest.raises(error_type) as raised:
            await _direct(kind)
        assert raised.value is failure

    asyncio.run(run())
    assert len(called) == 1 and called[0] != threading.get_ident()
    assert gate._active == 0 and len(state.entries) == len(state.leaves) == 1
    assert state.entries == [(called[0], True)] and state.leaves == called
    assert state.store.count() == 0 and state.published == []


@pytest.mark.parametrize('kind', ['preview', 'ingest'])
def test_http_worker_failure_balances_both_request_and_actual_worker_scopes(owned, monkeypatch, kind):
    state = owned
    failure = RuntimeError('Authored HTTP worker failure.')
    target = state.runtime.capture if kind == 'preview' else state.index
    name = 'preview_for_region' if kind == 'preview' else 'match_text'

    def fail(*_args):
        assert state.gate._active == 2
        raise failure

    monkeypatch.setattr(target, name, fail)

    async def run():
        with pytest.raises(RuntimeError) as raised:
            await _request(kind)
        assert raised.value is failure

    asyncio.run(run())
    state.gate.wait_drained(0)
    assert len(state.entries) == len(state.leaves) == 2
    assert len([thread for thread, ticketed in state.entries if ticketed]) == 1
    assert state.store.count() == 0 and state.published == []


async def _queued(loop):
    started, queued, release = asyncio.Event(), asyncio.Event(), threading.Event()

    class ObservedExecutor(ThreadPoolExecutor):
        def __init__(self):
            super().__init__(max_workers=1)
            self.submissions = 0
            self.worker_future = None

        def submit(self, *args, **kwargs):
            future = super().submit(*args, **kwargs)
            self.submissions += 1
            if self.submissions == 2:
                self.worker_future = future
                queued.set()
            return future

    pool = ObservedExecutor()
    loop.set_default_executor(pool)

    def hold():
        loop.call_soon_threadsafe(started.set)
        assert release.wait(5), 'Authored executor blocker was not released.'

    blocker = loop.run_in_executor(None, hold)
    await _event(started)
    return SimpleNamespace(pool=pool, queued=queued, release=release, blocker=blocker)


@pytest.mark.parametrize('kind', ['preview', 'ingest'])
def test_queued_old_ticket_is_refused_after_stop_resume_and_fresh_request_succeeds(owned, kind):
    state, gate = owned, owned.gate

    async def run():
        queue = await _queued(asyncio.get_running_loop())
        task = asyncio.create_task(_request(kind))
        try:
            await _event(queue.queued)
            assert gate._active == 1 and _calls(state, kind) == []
            gate.stop_admission()
            with pytest.raises(TimeoutError):
                gate.wait_drained(0)  # Live queued HTTP waiter still counts.
            gate.resume()  # Authored recovery transition; not successful quiesce proof.
            queue.release.set()
            await queue.blocker
            refused = await asyncio.wait_for(task, 2)
            assert refused.status_code == 503 and refused.headers['retry-after'] == '1'
            assert refused.json() == {'detail': RETRY}
            assert _calls(state, kind) == [] and gate._active == 0
            assert len(state.entries) == len(state.leaves) == 1  # Refused worker never leaves.
            fresh = await _request(kind)
            assert fresh.status_code == 200 and len(_calls(state, kind)) == 1
            assert gate._active == 0 and len(state.entries) == len(state.leaves) == 3
            if kind == 'ingest':
                assert state.store.count() == len(state.published) == 1
                assert fresh.json()['chinese'] == CHINESE
            else:
                assert fresh.headers['content-type'] == 'image/jpeg' and state.background.frames == 1
        finally:
            queue.release.set()
            await queue.blocker
            if not task.done():
                await _cancel(task)
            queue.pool.shutdown(wait=True)

    asyncio.run(run())


@pytest.mark.parametrize('kind', ['preview', 'ingest'])
def test_cancel_before_queued_worker_start_does_not_enter_or_leave_worker_scope(owned, kind):
    state, gate = owned, owned.gate

    async def run():
        queue = await _queued(asyncio.get_running_loop())
        task = asyncio.create_task(_request(kind))
        try:
            await _event(queue.queued)
            await _cancel(task)
            await asyncio.sleep(0)  # Dispatch the concurrent-Future cancellation callback.
            assert queue.pool.worker_future.cancelled()
            gate.stop_admission()
            gate.wait_drained(0)
            gate.resume()
            queue.release.set()
            await queue.blocker
            queue.pool.shutdown(wait=True)
            assert _calls(state, kind) == [] and gate._active == 0
            assert len(state.entries) == len(state.leaves) == 1
            assert state.store.count() == 0 and state.published == []
        finally:
            queue.release.set()
            await queue.blocker
            if not task.done():
                await _cancel(task)
            queue.pool.shutdown(wait=True)

    asyncio.run(run())


@pytest.mark.parametrize('kind', ['preview', 'ingest'])
def test_queued_operation_retains_original_runtime_gate_and_bound_callable(owned, monkeypatch, kind):
    state, gate = owned, owned.gate

    async def run():
        queue = await _queued(asyncio.get_running_loop())
        task = asyncio.create_task(_request(kind))
        try:
            await _event(queue.queued)
            other_gate = RuntimeWriterGate()
            forbidden = state.forbidden
            replacement = SimpleNamespace(request_writers=other_gate,
                capture=SimpleNamespace(preview_for_region=forbidden, preview_bytes=forbidden,
                                        session_id='forbidden-replacement-session'),
                textmaps=SimpleNamespace(ready=True, match_text=forbidden),
                transcript=SimpleNamespace(add=forbidden), on_line=forbidden)
            # These authored reference changes are binding negatives, not an
            # assertion that production currently swaps Runtime mid-request.
            monkeypatch.setattr(api, 'runtime', replacement)
            state.runtime.request_writers = other_gate
            if kind == 'preview':
                monkeypatch.setattr(state.runtime.capture, 'preview_for_region', forbidden)
            else:
                monkeypatch.setattr(state.index, 'match_text', forbidden)
                state.threshold = 3
                state.runtime.capture.session_id = 'owned-after-match-wait'
            queue.release.set()
            await queue.blocker
            response = await asyncio.wait_for(task, 2)
            assert response.status_code == 200 and len(_calls(state, kind)) == 1
            assert gate._active == other_gate._active == 0
            assert len(state.entries) == len(state.leaves) == 2
            if kind == 'ingest':
                assert state.match_calls == [(TEXT, 82)]
                line, = state.store.list()
                assert line.session_id == 'owned-after-match-wait' and line.chinese == CHINESE
                assert [item.id for item in state.published] == [line.id]
                assert response.json()['session_id'] == 'owned-after-match-wait'
        finally:
            queue.release.set()
            await queue.blocker
            if not task.done():
                await _cancel(task)
            queue.pool.shutdown(wait=True)

    asyncio.run(run())


@pytest.mark.parametrize('kind', ['preview', 'ingest'])
def test_closed_or_wrong_gate_ticket_refuses_before_resource_access_without_worker_leave(owned, monkeypatch, kind):
    state, gate = owned, owned.gate

    async def run():
        gate.stop_admission()
        with pytest.raises(api.HTTPException) as closed:
            await _direct(kind)
        assert closed.value.status_code == 503 and closed.value.detail == RETRY
        assert closed.value.headers == {'Retry-After': '1'}
        gate.resume()
        other = RuntimeWriterGate()
        monkeypatch.setattr(gate, 'capture_ticket', other.capture_ticket)
        with pytest.raises(api.HTTPException) as wrong:
            await _direct(kind)
        assert wrong.value.status_code == 503 and wrong.value.detail == RETRY
        assert wrong.value.headers == {'Retry-After': '1'}
        assert gate._active == other._active == 0

    asyncio.run(run())
    assert _calls(state, kind) == [] and state.entries == state.leaves == []
    assert state.store.count() == 0 and state.published == []


def test_preview_without_region_keeps_cached_byte_behavior_without_a_worker_ticket(owned, monkeypatch):
    state = owned
    monkeypatch.setattr(state.gate, 'capture_ticket', state.forbidden)

    async def run():
        response = await _request('preview', params={})
        assert response.status_code == 200 and response.content == b'owned-cached-preview'
        assert response.headers['content-type'] == 'image/jpeg'
        assert response.headers['cache-control'] == 'no-store, max-age=0'
        state.runtime.capture._preview = b''
        missing = await _request('preview', params={})
        assert missing.status_code == 404

    asyncio.run(run())
    assert state.preview_calls == [] and state.background.frames == 0
    assert all(not ticketed for _thread, ticketed in state.entries)
    assert state.gate._active == 0 and len(state.entries) == len(state.leaves) == 2


def test_ingest_not_ready_and_no_match_keep_existing_errors_and_do_not_publish(owned):
    state = owned

    async def run():
        state.index.ready = False
        unready = await _request('ingest')
        assert unready.status_code == 409 and unready.json() == {'detail': 'TextMaps are not ready'}
        assert state.match_calls == []
        state.index.ready = True
        missing = await _request('ingest', text='Unrelated authored input without any match.')
        assert missing.status_code == 404 and missing.json() == {'detail': 'No bilingual TextMap match found'}

    asyncio.run(run())
    assert state.store.count() == 0 and state.published == [] and state.gate._active == 0
