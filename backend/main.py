from __future__ import annotations

import uvicorn
import argparse
import os
import asyncio
import json
import socket
import sys
import threading


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--standby', action='store_true')
    parser.add_argument('--shutdown-stdin', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
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
