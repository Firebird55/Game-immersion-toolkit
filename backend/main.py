from __future__ import annotations

import uvicorn
import argparse
import os
import asyncio
import json
import socket
import sys
import threading


def start_stdin_shutdown(callback, *, ready=None):
    """Keep the API control reader identical in service and native probes."""
    def stop_on_input():
        if ready is not None:
            ready.set()
        sys.stdin.readline()
        callback()
    reader = threading.Thread(target=stop_on_input, daemon=True)
    reader.start()
    return reader


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--standby', action='store_true')
    parser.add_argument('--shutdown-stdin', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--preparation-probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.preparation_probe:
        if not args.shutdown_stdin:
            parser.error('The preparation probe requires its owned control input.')
        from .preparation_probe import run
        from .runtime_bundle import discover_layout
        return run(discover_layout(), start_stdin_shutdown)
    if args.standby:
        os.environ['PROXY_TRANSCRIPT_STANDBY'] = '1'
    config = uvicorn.Config(
        "backend.api:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        reload=False,
        access_log=False,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        listener.bind(('127.0.0.1', args.port))
        listener.listen(128)
        server = uvicorn.Server(config)
        async def serve():
            if args.shutdown_stdin:
                loop = asyncio.get_running_loop()
                start_stdin_shutdown(lambda: loop.call_soon_threadsafe(setattr, server, 'should_exit', True))
            serving = asyncio.create_task(server.serve(sockets=[listener]))
            while not server.started and not serving.done():
                await asyncio.sleep(.02)
            if server.started:
                print(json.dumps({'ready': True, 'port': listener.getsockname()[1]}), flush=True)
            await serving
        asyncio.run(serve())
    finally:
        listener.close()


if __name__ == "__main__":
    raise SystemExit(main())
