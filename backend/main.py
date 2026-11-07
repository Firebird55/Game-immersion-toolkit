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


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int)
    parser.add_argument('--standby', action='store_true')
    parser.add_argument('--candidate-closed', action='store_true')
    parser.add_argument('--parent-control-stdin', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--shutdown-stdin', action='store_true', help=argparse.SUPPRESS)
    parser.add_argument('--preparation-probe', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.preparation_probe:
        if not args.shutdown_stdin or args.candidate_closed or args.parent_control_stdin:
            parser.error('The preparation probe requires exclusive owned shutdown input.')
        from .preparation_probe import run
        from .runtime_bundle import discover_layout
        return run(discover_layout(), start_stdin_shutdown)
    gate = None
    parent = None
    saved_stdout = None
    if args.parent_control_stdin:
        if (getattr(sys, 'frozen', False) or args.candidate_closed or not args.standby
                or not args.shutdown_stdin or args.port is None
                or (args.port != 0 and (not 1024 < args.port < 65536 or args.port in (3000, 8766)))):
            parser.error('Parent control requires source standby, shutdown input and an explicit private port.')
        from .runtime_writers import ParentControlBinding, RuntimeWriterGate
        # Retain actual wrappers as well as their binary endpoints: replacing
        # sys.stdout must not let its wrapper destructor close the control pipe.
        parent = ParentControlBinding.__new__(ParentControlBinding)
        ParentControlBinding.__init__(parent, sys.stdin.buffer, sys.stdout.buffer, stream_owners=(sys.stdin, sys.stdout))
        gate = RuntimeWriterGate(parent_control=parent)
        parent.bind_input()
        saved_stdout, sys.stdout = sys.stdout, sys.stderr
    if args.candidate_closed:
        _candidate_layout(args.port, args.standby)
        # Construct the exact closed gate before importing any API services.
        from .runtime_writers import RuntimeWriterGate
        gate = RuntimeWriterGate(closed_candidate=True)
    if args.standby:
        os.environ['PROXY_TRANSCRIPT_STANDBY'] = '1'
    try:
        target = 'backend.api:app'
        if parent is not None:
            from .api import parent_control_app
            target = parent_control_app(parent)
        elif gate is not None:
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
                if args.shutdown_stdin and parent is None:
                    loop = asyncio.get_running_loop()
                    start_stdin_shutdown(lambda: loop.call_soon_threadsafe(setattr, server, 'should_exit', True))
                serving = asyncio.create_task(server.serve(sockets=[listener]))
                try:
                    while not server.started and not serving.done():
                        await asyncio.sleep(.02)
                    if server.started:
                        if parent is None:
                            print(json.dumps({'ready': True, 'port': listener.getsockname()[1]}), flush=True)
                        else:
                            from .api import _parent_activate_idle
                            parent.start(listener.getsockname()[1],
                                lambda grant: _parent_activate_idle(parent, grant),
                                lambda: setattr(server, 'should_exit', True))
                    await serving
                finally:
                    if parent is not None:
                        await asyncio.to_thread(parent.finish_io, 1.0)
            asyncio.run(serve())
        finally:
            listener.close()
    finally:
        if saved_stdout is not None:
            sys.stdout = saved_stdout


if __name__ == "__main__":
    raise SystemExit(main())
