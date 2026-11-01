"""Actual stdlib server bookkeeping with deterministic socket-reset injection."""
import asyncio
from asyncio.base_events import Server
from asyncio.proactor_events import _ProactorBasePipeTransport
import socket
import sys
from types import SimpleNamespace

import pytest

from backend.gateway_loop import GatewaySocketTransport, new_gateway_loop


def reset_error(code=10054):
    error = ConnectionResetError('Authored shutdown reset')
    error.winerror = code
    return error


class ResetSocket:
    def __init__(self, error=None):
        self.socket = socket.socket()
        self.error = error
        self.shutdown_calls = []
        self.close_calls = 0

    def fileno(self):
        return self.socket.fileno()

    def shutdown(self, how):
        self.shutdown_calls.append(how)
        if self.error:
            raise self.error

    def close(self):
        self.close_calls += 1
        self.socket.close()


def transport_state(loop, sock, *, protocol_error=None):
    server = Server(loop, [], None, None, 1, None)
    server._attach()
    server.close()
    calls = []

    def connection_lost(error):
        calls.append(error)
        if protocol_error:
            raise protocol_error

    state = SimpleNamespace(_called_connection_lost=False, _sock=sock, _server=server,
                            _protocol=SimpleNamespace(connection_lost=connection_lost))
    return state, server, calls


def test_stdlib_reset_retains_server_connection_but_gateway_releases_it():
    async def scenario():
        for callback, repaired in [(_ProactorBasePipeTransport._call_connection_lost, False),
                                   (GatewaySocketTransport._call_connection_lost, True)]:
            sock = ResetSocket(reset_error())
            state, server, calls = transport_state(asyncio.get_running_loop(), sock)
            waiting = asyncio.create_task(server.wait_closed())
            await asyncio.sleep(0)
            assert not waiting.done()
            try:
                if repaired:
                    callback(state, None)
                    await asyncio.wait_for(asyncio.shield(waiting), .5)
                    callback(state, None)  # A queued second callback cannot detach twice.
                    assert state._called_connection_lost and state._sock is None and state._server is None
                    assert sock.fileno() == -1 and sock.close_calls == 1 and server._active_count == 0
                else:
                    with pytest.raises(ConnectionResetError):
                        callback(state, None)
                    await asyncio.sleep(0)
                    assert not waiting.done() and server._active_count == 1
                    assert sock.fileno() != -1 and sock.close_calls == 0
                    assert not state._called_connection_lost
                assert calls == [None] and sock.shutdown_calls == [socket.SHUT_RDWR]
            finally:
                if not repaired:
                    sock.close()
                    server._detach()
                await waiting
    asyncio.run(scenario())


@pytest.mark.parametrize('shutdown_reset', [False, True])
def test_protocol_errors_propagate_after_actual_socket_release(shutdown_reset):
    async def scenario():
        error = reset_error()  # Even the same error code from the protocol is not suppressed.
        sock = ResetSocket(reset_error() if shutdown_reset else None)
        state, server, calls = transport_state(asyncio.get_running_loop(), sock, protocol_error=error)
        with pytest.raises(ConnectionResetError) as caught:
            GatewaySocketTransport._call_connection_lost(state, None)
        assert caught.value is error
        await asyncio.wait_for(server.wait_closed(), .5)
        assert calls == [None] and sock.close_calls == 1 and sock.fileno() == -1
    asyncio.run(scenario())


@pytest.mark.parametrize('error', [reset_error(10053), OSError('Unknown socket failure')], ids=['other-code', 'other-error'])
def test_unknown_shutdown_errors_are_not_suppressed(error):
    async def scenario():
        sock = ResetSocket(error)
        state, server, _calls = transport_state(asyncio.get_running_loop(), sock)
        try:
            with pytest.raises(OSError) as caught:
                GatewaySocketTransport._call_connection_lost(state, None)
            assert caught.value is error and not state._called_connection_lost
            assert server._active_count == 1
        finally:
            sock.close()
            server._detach()
            await server.wait_closed()
    asyncio.run(scenario())


def test_gateway_loop_uses_actual_owned_tcp_transports_without_changing_policy():
    policy = asyncio.get_event_loop_policy()
    observed = []

    class Protocol(asyncio.Protocol):
        def connection_made(self, transport):
            observed.append(transport)
            transport.close()

    async def scenario():
        loop = asyncio.get_running_loop()
        server = await loop.create_server(Protocol, '127.0.0.1', 0)
        try:
            reader, writer = await asyncio.open_connection('127.0.0.1', server.sockets[0].getsockname()[1])
            observed.append(writer.transport)
            assert await asyncio.wait_for(reader.read(), 1) == b''
            writer.close()
            await writer.wait_closed()
        finally:
            server.close()
            await asyncio.wait_for(server.wait_closed(), 1)

    asyncio.run(scenario(), loop_factory=new_gateway_loop)
    assert len(observed) == 2 and all(transport.is_closing() for transport in observed)
    assert all(isinstance(transport, GatewaySocketTransport) == (sys.platform == 'win32') for transport in observed)
    assert asyncio.get_event_loop_policy() is policy
