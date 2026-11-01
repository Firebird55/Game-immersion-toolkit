"""Gateway-local IOCP cleanup for reset TCP connections on Windows.

CPython 3.12's Proactor socket cleanup can leave Server.wait_closed() pending
when shutdown(SHUT_RDWR) raises WSAECONNRESET before close/_detach. Keep IOCP
and repair that operation only; other application loops and their policies
remain unchanged.
"""
from __future__ import annotations

import asyncio
from asyncio.proactor_events import _ProactorSocketTransport
import socket
import sys


class GatewaySocketTransport(_ProactorSocketTransport):
    def _call_connection_lost(self, exc):
        # Adapted from CPython 3.12 Lib/asyncio/proactor_events.py (PSF-2.0).
        # Full terms: packaging/runtime-bundle/python-notices/LICENSE.cpython.txt.
        # Handle only a reset from shutdown, not protocol.connection_lost errors.
        if self._called_connection_lost:
            return
        try:
            self._protocol.connection_lost(exc)
        finally:
            if self._sock.fileno() != -1:
                try:
                    self._sock.shutdown(socket.SHUT_RDWR)
                except ConnectionResetError as error:
                    if getattr(error, 'winerror', None) != 10054:
                        raise
            self._sock.close()
            self._sock = None
            if self._server is not None:
                self._server._detach()
                self._server = None
            self._called_connection_lost = True


def new_gateway_loop():
    """Select the gateway transport without installing a process-wide policy."""
    if sys.platform != 'win32':
        return asyncio.new_event_loop()

    class GatewayProactorEventLoop(asyncio.ProactorEventLoop):
        def _make_socket_transport(self, sock, protocol, waiter=None, extra=None, server=None):
            return GatewaySocketTransport(self, sock, protocol, waiter, extra, server)

    return GatewayProactorEventLoop()
