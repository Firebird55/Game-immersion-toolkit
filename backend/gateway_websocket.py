"""Gateway-local shutdown repair for the pinned Uvicorn Sans-I/O protocol."""
from uvicorn.protocols.websockets.websockets_sansio_impl import WebSocketsSansIOProtocol
from websockets.protocol import CLOSED, CLOSING


class GatewayWebSocketProtocol(WebSocketsSansIOProtocol):
    def shutdown(self):
        # A peer Close is echoed by websockets before Uvicorn receives the
        # transport's connection_lost callback. Uvicorn 0.54.0 leaves its
        # separate close_sent flag unset on that path; shutdown would then
        # send another Close from CLOSING and abort the entire server drain.
        # Reconcile that flag with the actual protocol state, retaining the
        # upstream timer cleanup, transport close and connection bookkeeping.
        if self.conn.state in (CLOSING, CLOSED):
            self.close_sent = True
        super().shutdown()
