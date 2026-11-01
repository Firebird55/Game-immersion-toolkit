from __future__ import annotations

import uvicorn
import argparse
import os
import asyncio
import json
import socket
import sys
import threading


def _candidate_layout(port, standby):
    from .runtime_bundle import discover_layout, EXPERIMENT_CHILDREN, RuntimeBundleError, RuntimeLayout
    if (not getattr(sys, 'frozen', False) or sys.platform != 'win32' or not standby
            or type(port) is not int or not 1024 < port < 65536 or port in (3000, 8766)):
        raise RuntimeBundleError('Closed candidates require frozen experimental standby and an explicit private port.')
    layout = discover_layout()
    if (type(layout) is not RuntimeLayout or layout.mode != 'bundle' or layout.profile != 'runtime-experiment'
            or layout.children != EXPERIMENT_CHILDREN or layout.legacy_root is not None
            or layout.resource_root != layout.application_root / '_internal'
            or layout.executable != layout.application_root / 'GameImmersionToolkit.exe'):
        raise RuntimeBundleError('Closed candidates require the quarantined experimental main runtime image.')
    return layout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int)
    parser.add_argument('--standby', action='store_true')
    parser.add_argument('--candidate-closed', action='store_true')
    parser.add_argument('--shutdown-stdin', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    gate = None
    if args.candidate_closed:
        _candidate_layout(args.port, args.standby)
        # Construct the exact closed gate before importing any API services.
        from .runtime_writers import RuntimeWriterGate
        gate = RuntimeWriterGate(closed_candidate=True)
    if args.standby:
        os.environ['PROXY_TRANSCRIPT_STANDBY'] = '1'
    target = 'backend.api:app'
    if gate is not None:
        from .api import closed_candidate_app
        target = closed_candidate_app(gate)
    port = 8766 if args.port is None else args.port
    config = uvicorn.Config(
        target,
        host="127.0.0.1",
        port=port,
        log_level="info",
        reload=False,
        access_log=False,
    )
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if hasattr(socket, 'SO_EXCLUSIVEADDRUSE'):
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    try:
        listener.bind(('127.0.0.1', port))
        listener.listen(128)
        server = uvicorn.Server(config)
        async def serve():
            if args.shutdown_stdin:
                loop = asyncio.get_running_loop()
                def stop_on_input():
                    sys.stdin.readline()
                    loop.call_soon_threadsafe(setattr, server, 'should_exit', True)
                threading.Thread(target=stop_on_input, daemon=True).start()
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
    main()
