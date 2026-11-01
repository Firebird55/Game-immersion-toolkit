"""Real Sans-I/O close frames with deterministic transport-callback ordering."""
import asyncio

import pytest
from uvicorn import Config
from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol
from uvicorn.server import ServerState
from websockets.exceptions import InvalidState
from websockets.frames import Close, Frame, Opcode
from websockets.protocol import CLOSED, CLOSING, OPEN
from websockets.server import ServerProtocol

from backend.gateway_websocket import GatewayWebSocketProtocol


async def app(scope, receive, send):
    raise AssertionError('This protocol fixture must not initialize an application')


class Transport:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, data):
        self.writes.append(data)

    def close(self):
        self.closed = True

    def is_closing(self):
        return self.closed


def established(protocol_type=GatewayWebSocketProtocol):
    state = ServerState()
    protocol = protocol_type(Config(app, log_config=None, ws=protocol_type), state, {})
    protocol.transport = Transport()
    # Start at the established state; all subsequent close transitions use
    # the actual wire parser and Uvicorn event handlers, not mocked flags.
    protocol.conn = ServerProtocol(state=OPEN)
    protocol.handshake_complete = True
    state.connections.add(protocol)
    return protocol, state


def peer_close(protocol):
    frame = Frame(Opcode.CLOSE, Close(1000, 'reader finished').serialize())
    protocol.data_received(frame.serialize(mask=True))


def test_pinned_upstream_reproduces_peer_close_shutdown_race():
    async def run():
        protocol, _ = established(WebSocketsSansIOProtocol)
        peer_close(protocol)
        assert protocol.conn.state is CLOSING and not protocol.close_sent
        with pytest.raises(InvalidState, match='connection is closing'):
            protocol.shutdown()
    asyncio.run(run())


@pytest.mark.parametrize('closing', ['peer', 'eof', 'application', 'server'])
def test_shutdown_drains_existing_close_without_second_frame(closing):
    async def run():
        protocol, state = established()
        if closing == 'peer':
            peer_close(protocol)
        elif closing == 'eof':
            protocol.conn.receive_eof()
            assert protocol.conn.state is CLOSED
        elif closing == 'application':
            await protocol.send({'type': 'websocket.close', 'code': 1000})
        else:
            protocol.shutdown()
            assert protocol.conn.close_sent.code == 1012
        assert protocol.conn.state in (CLOSING, CLOSED)
        written = list(protocol.transport.writes)
        protocol.ping_timer = asyncio.get_running_loop().call_later(60, lambda: None)
        protocol.pong_timer = asyncio.get_running_loop().call_later(60, lambda: None)
        if protocol.close_timer is None:
            protocol.close_timer = asyncio.get_running_loop().call_later(60, lambda: None)
        timers = [protocol.ping_timer, protocol.pong_timer, protocol.close_timer]
        protocol.shutdown()
        protocol.shutdown()
        assert protocol.transport.closed
        assert protocol.transport.writes == written
        assert all(timer.cancelled() for timer in timers)
        assert protocol.ping_timer is protocol.pong_timer is protocol.close_timer is None
        # Transport close must not pretend that connection_lost already ran.
        assert protocol in state.connections
        protocol.connection_lost(None)
        assert not state.connections and protocol.disconnected
        assert protocol.writable.is_set()
    asyncio.run(run())


def test_open_connection_keeps_service_restart_close_and_unknown_failures(monkeypatch):
    async def run():
        protocol, _ = established()
        protocol.shutdown()
        assert protocol.conn.close_sent.code == 1012
        assert protocol.queue.get_nowait() == {'type': 'websocket.disconnect', 'code': 1012}
        assert protocol.transport.closed and protocol.transport.writes

        other, _ = established()
        error = RuntimeError('Authored unrelated protocol failure')
        def fail(_code):
            raise error
        monkeypatch.setattr(other.conn, 'send_close', fail)
        with pytest.raises(RuntimeError) as caught:
            other.shutdown()
        assert caught.value is error
    asyncio.run(run())


def test_unaccepted_connection_retains_upstream_handshake_rejection():
    async def run():
        protocol, _ = established()
        protocol.conn = ServerProtocol()
        protocol.handshake_complete = False
        protocol.shutdown()
        assert protocol.transport.closed
        assert b'500 Internal Server Error' in b''.join(protocol.transport.writes)
    asyncio.run(run())
