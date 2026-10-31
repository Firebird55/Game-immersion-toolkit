"""Promote an unchanged native payload using exact input and execution evidence.

The output is a new external receipt. No executable, manifest, frontend or other
payload byte is changed after testing. R19 plan completion is independent of a
platform's distributable installer acceptance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.runtime_payload import PackageError, TARGETS, digest, validate

INPUT_CHECKS = frozenset({'python_supplier', 'exact_wheels', 'native_inputs',
    'complete_notices', 'corresponding_sources', 'frontend_licenses'})
NATIVE_CHECKS = frozenset({'host_check', 'frontend_gateway', 'api_crash_recovery',
    'owned_shutdown', 'browser_open', 'status_window', 'tray_icon'})
REPORT_SCHEMAS = {'toolkit-desktop-native-probe-v1', 'toolkit-desktop-ui-probe-v1'}


def inventory_digest(receipt):
    value = {key: receipt[key] for key in ('files', 'directories')}
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def read_report(path):
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 8 * 1024 * 1024:
        raise PackageError('Acceptance evidence must be a bounded regular JSON file.')
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict):
        raise PackageError('Acceptance evidence must be an object.')
    return value


def identity(report, receipt, receipt_digest, target):
    expected = {key: receipt[key] for key in ('source_commit', 'build_id')}
    expected.update(target=target, runtime_receipt_sha256=receipt_digest)
    if any(report.get(key) != value for key, value in expected.items()):
        raise PackageError('Acceptance evidence belongs to different payload bytes or a different target.')


def accept(root, provenance, target, input_review, native_reports, output):
    receipt = read_report(provenance)
    validate(root, receipt, target, candidate=True)
    if receipt.get('profile') != 'runtime':
        raise PackageError('Build the runtime profile before testing; promotion never rewrites its manifest.')
    if output.exists() or output.absolute() == provenance.absolute():
        raise PackageError('Choose a new acceptance receipt; previous evidence is preserved.')
    if root.absolute() == output.absolute() or root.absolute() in output.absolute().parents:
        raise PackageError('Acceptance evidence must stay outside the immutable payload.')
    if receipt.get('directories') is None:
        raise PackageError('Acceptance requires the exact directory inventory.')
    receipt_sha = digest(provenance)
    review = read_report(input_review)
    identity(review, receipt, receipt_sha, target)
    if (review.get('schema') != 'toolkit-desktop-input-review-v1'
            or review.get('file_inventory_sha256') != inventory_digest(receipt)
            or review.get('approved') is not True
            or any(review.get('checks', {}).get(key) is not True for key in INPUT_CHECKS)):
        raise PackageError('Exact supplier, notices and corresponding-source review is incomplete.')
    # Capabilities are explicit product facts, including unavailable codecs or
    # capture backends. Missing packs are not invented as unvoiced recordings.
    capabilities = review.get('capabilities')
    if not isinstance(capabilities, dict) or not capabilities or any(
            not isinstance(name, str) or status not in {'available', 'unavailable', 'requires-installed-pack', 'host-permission'}
            for name, status in capabilities.items()):
        raise PackageError('Acceptance needs explicit native capability states.')
    observed = set()
    reports = []
    for path in native_reports:
        report = read_report(path)
        identity(report, receipt, receipt_sha, target)
        if (report.get('schema') not in REPORT_SCHEMAS or report.get('passed') is not True
                or report.get('execution') != 'actual-frozen-process' or not isinstance(report.get('checks'), dict)):
            raise PackageError('Native evidence must come from a successful actual frozen process probe.')
        checks = report['checks']
        if any(key in NATIVE_CHECKS and value is not True for key, value in checks.items()):
            raise PackageError('A required native check failed or was unavailable.')
        observed.update(key for key, value in checks.items() if value is True)
        reports.append({'schema': report['schema'], 'sha256': digest(path),
            'checks': {key: value for key, value in checks.items() if key in NATIVE_CHECKS}})
    if not NATIVE_CHECKS <= observed:
        raise PackageError('Native acceptance is missing checks: ' + ', '.join(sorted(NATIVE_CHECKS - observed)))
    accepted = {**receipt, 'release_eligible': True, 'redistribution_review': 'approved',
        'native_acceptance': 'approved', 'signing': 'unsigned', 'capabilities': capabilities,
        'release_acceptance': {'schema': 'toolkit-desktop-target-acceptance-v1', 'target': target,
            'constructed_receipt_sha256': receipt_sha, 'file_inventory_sha256': inventory_digest(receipt),
            'input_review_sha256': digest(input_review), 'native_reports': reports}}
    # An accepted target says nothing new about all-game R19 completion.
    accepted['r19_complete'] = receipt.get('r19_complete') is True
    validate(root, accepted, target)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('x', encoding='utf-8') as stream:
        stream.write(json.dumps(accepted, indent=2) + '\n')
    return accepted


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runtime-root', type=Path, required=True)
    parser.add_argument('--provenance', type=Path, required=True)
    parser.add_argument('--target', choices=sorted(TARGETS), required=True)
    parser.add_argument('--input-review', type=Path, required=True)
    parser.add_argument('--native-report', type=Path, action='append', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        result = accept(args.runtime_root, args.provenance, args.target, args.input_review, args.native_report, args.output)
    except (OSError, ValueError) as error:
        print('Desktop acceptance failed: ' + str(error), file=sys.stderr)
        return 2
    print(json.dumps({key: result[key] for key in ('build_id', 'release_eligible', 'r19_complete', 'signing')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
