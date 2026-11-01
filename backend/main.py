from __future__ import annotations

import uvicorn
import argparse
import os
import sys


def _candidate_layout(port, standby):
    from .runtime_bundle import discover_layout, EXPERIMENT_CHILDREN, RuntimeBundleError, RuntimeLayout
    if (not getattr(sys, 'frozen', False) or sys.platform != 'win32' or not standby
            or type(port) is not int or not 1024 < port < 65536 or port in (3000, 8766)):
        raise RuntimeBundleError('Closed candidates require frozen experimental standby and an explicit private port.')
    layout = discover_layout()
    if (type(layout) is not RuntimeLayout or layout.mode != 'bundle' or layout.profile != 'runtime-experiment'
            or layout.children != EXPERIMENT_CHILDREN or layout.legacy_root is not None
            or layout.resource_root != layout.application_root / '_internal'
            or layout.executable != layout.application_root / 'ProxyTranscriptRuntime.exe'):
        raise RuntimeBundleError('Closed candidates require the quarantined experimental main runtime image.')
    return layout


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int)
    parser.add_argument('--standby', action='store_true')
    parser.add_argument('--candidate-closed', action='store_true')
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
    uvicorn.run(
        target,
        host="127.0.0.1",
        port=8766 if args.port is None else args.port,
        log_level="info",
        reload=False,
    )


if __name__ == "__main__":
    main()
