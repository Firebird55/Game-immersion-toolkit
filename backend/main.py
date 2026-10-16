from __future__ import annotations

import uvicorn
import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8766)
    parser.add_argument('--standby', action='store_true')
    args = parser.parse_args()
    if args.standby:
        os.environ['PROXY_TRANSCRIPT_STANDBY'] = '1'
    uvicorn.run(
        "backend.api:app",
        host="127.0.0.1",
        port=args.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
