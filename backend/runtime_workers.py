"""Exclude new work and join actual workers before a runtime gives up its data."""
from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
import threading

from starlette.responses import JSONResponse


class ResumableExecutor:
    """A pool that can be drained for handoff, then reopened on rollback.

    Cancelling an asyncio waiter does not stop its worker. Joining the pool also
    waits for future completion callbacks, which may commit cached results.
    """
    def __init__(self, max_workers=None, thread_name_prefix='', **kwargs):
        self._options = dict(max_workers=max_workers, thread_name_prefix=thread_name_prefix, **kwargs)
        self._lock = threading.RLock()
        self._pool = ThreadPoolExecutor(**self._options)
        self._draining = False
        self._closed = False

    def submit(self, function, /, *args, **kwargs):
        with self._lock:
            if self._closed or self._draining or self._pool is None:
                raise RuntimeError('Runtime workers are paused for handoff.')
            return self._pool.submit(function, *args, **kwargs)

    def drain(self):
        with self._lock:
            if self._draining:
                raise RuntimeError('Runtime workers are already draining.')
            if self._pool is None:
                return
            self._draining = True
            pool = self._pool
        try:
            pool.shutdown(wait=True, cancel_futures=False)
        except BaseException:
            # A failed join is not evidence that writes stopped. Leave this
            # executor blocked; the owner must terminate it before replacing it.
            raise
        else:
            with self._lock:
                self._pool = None
                self._draining = False

    def resume(self):
        with self._lock:
            if self._closed or self._draining:
                raise RuntimeError('Runtime workers have not finished stopping.')
            if self._pool is None:
                self._pool = ThreadPoolExecutor(**self._options)

    def shutdown(self, wait=True, *, cancel_futures=False):
        with self._lock:
            self._closed = True
            pool = self._pool
        if pool is not None:
            pool.shutdown(wait=wait, cancel_futures=cancel_futures)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.shutdown()


class RequestBarrier:
    def __init__(self, *, paused=False):
        self.paused = paused
        self._active = 0
        self._idle = asyncio.Event()
        self._idle.set()

    def enter(self):
        # These operations run on the ASGI loop without an intervening await.
        if self.paused:
            return False
        self._active += 1
        self._idle.clear()
        return True

    def leave(self):
        self._active -= 1
        if self._active == 0:
            self._idle.set()

    async def pause(self):
        self.paused = True
        await self._idle.wait()

    def resume(self):
        if self._active:
            raise RuntimeError('Requests have not finished draining.')
        self.paused = False


class WriterBarrierMiddleware:
    def __init__(self, app, barrier):
        self.app, self.barrier = app, barrier

    async def __call__(self, scope, receive, send):
        gate = self.barrier()
        path = scope.get('path', '')
        # GET dictionary/audio requests can write caches too. Count the entire
        # ASGI request, including streaming response and background completion.
        # Sockets only broadcast existing rows; fixed status/control paths do
        # not launch writers and must remain available during a handoff.
        bypass = (scope['type'] != 'http' or path in {
            '/api/health', '/api/status', '/api/runtime/ready',
            '/api/runtime/quiesce', '/api/runtime/activate'})
        if gate is None or bypass:
            return await self.app(scope, receive, send)
        if not gate.enter():
            return await JSONResponse(
                {'detail': 'Toolkit is finishing an update. Reconnecting shortly.'},
                status_code=503, headers={'Retry-After': '1'})(scope, receive, send)
        try:
            await self.app(scope, receive, send)
        finally:
            gate.leave()
