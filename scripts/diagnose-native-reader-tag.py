"""Isolated diagnostic for the original failed Windows v0.23.0 checkout.

This never grants release acceptance: the probe reporter is deliberately newer
than the immutable source whose helper and dependencies are being diagnosed.
Explicit metadata repair restores only the four observed files in this temporary
CI checkout, then runs the corrected external preparer without changing the tag.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TAG = 'v0.23.0'
SOURCE = 'eb27e74e084dde6f4b2dab0a7b486838a8bcb781'
METADATA = ('VERSION', 'package-lock.json', 'package.json', 'release-version.json')


def check_backend_origins(source):
    """Every backend import must come from the tagged checkout, not this reporter."""
    expected = source.resolve(strict=True) / 'backend'
    for name, module in tuple(sys.modules.items()):
        if name != 'backend' and not name.startswith('backend.'):
            continue
        path = getattr(module, '__file__', None)
        if not path or not Path(path).resolve(strict=True).is_relative_to(expected):
            raise ValueError('backend-origin-mismatch')
        for location in getattr(module, '__path__', ()):
            if not Path(location).resolve(strict=True).is_relative_to(expected):
                raise ValueError('backend-origin-mismatch')


def load_reporter(source, reporter):
    source = source.resolve(strict=True)
    reporter = reporter.resolve(strict=True)
    if reporter.is_relative_to(source):
        raise ValueError('reporter-must-be-external')
    # Import the package first so all relative backend imports retain its tagged
    # __path__, even though the newer probe inserts its own repository on sys.path.
    check_backend_origins(source)
    sys.path.insert(0, str(source))
    importlib.import_module('backend')
    check_backend_origins(source)
    specification = importlib.util.spec_from_file_location('external_native_reader_reporter', reporter)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    check_backend_origins(source)
    module.ROOT = source
    # Prevent later unrelated imports from selecting the reporter checkout.
    sys.path[:] = [value for value in sys.path if Path(value or '.').resolve() != reporter.parents[1]]
    return module


def diagnose(source, helper_root, resources, *, reporter=None):
    reporter = reporter or ROOT / 'scripts/probe-native-unreal.py'
    source = source.resolve(strict=True)
    result = {'schema': 'toolkit-unreal-tag-diagnostic-v1', 'diagnostic_only': True,
              'release_eligible': False, 'native_acceptance': 'not-established',
              'tag': TAG, 'source_commit': SOURCE, 'passed': False}
    try:
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        if commit != SOURCE:
            result['error'] = 'tag-source-mismatch'
            return result
        result['reporter_sha256'] = hashlib.sha256(reporter.read_bytes()).hexdigest()
        probe = load_reporter(source, reporter)
        observation = {'phase': 'initializing'}
        try:
            report = probe.probe(helper_root.resolve(), resources.resolve(), observation)
        except Exception as error:
            report = probe.failure_report(error, observation)
        check_backend_origins(source)
        result['probe'] = report
        result['passed'] = report.get('passed') is True
    except Exception:
        # Never print raw loader/subprocess exceptions containing filesystem paths.
        result['error'] = 'diagnostic-loader-failed'
    return result


def repair_metadata(source, original_report, *, prepare_script=None):
    """Reproduce the narrow correction only in the isolated diagnostic checkout.

    The original observed failure and the live Git status must both identify
    exactly the four unstaged version files before any restoration is allowed.
    This is never used by a release build or by the normal native probe.
    """
    result = {'schema': 'toolkit-unreal-tag-metadata-repair-v1', 'diagnostic_only': True,
              'release_eligible': False, 'native_acceptance': 'not-established',
              'tag': TAG, 'source_commit': SOURCE, 'passed': False}
    stage = 'validate-original-failure'
    try:
        source = source.resolve(strict=True)
        original = json.loads(original_report.read_text(encoding='utf-8'))
        probe = original.get('probe', {})
        if not (original.get('schema') == 'toolkit-unreal-tag-diagnostic-v1'
                and original.get('source_commit') == SOURCE and original.get('tag') == TAG
                and original.get('diagnostic_only') is True and original.get('passed') is False
                and probe.get('phase') == 'checkout-cleanliness'
                and probe.get('reason') == 'source-checkout-dirty'
                and probe.get('changed_release_metadata') == list(METADATA)
                and probe.get('other_changed') is False):
            raise ValueError('unexpected-original-failure')
        stage = 'validate-current-checkout'
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=source, text=True).strip()
        if commit != SOURCE:
            raise ValueError('unexpected-original-source')
        status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'],
                                         cwd=source, text=True)
        if sorted(status.splitlines()) != [' M ' + name for name in METADATA]:
            raise ValueError('unexpected-current-changes')
        prepare_script = (prepare_script or ROOT / 'scripts/prepare-release-version.mjs').resolve(strict=True)
        if prepare_script.is_relative_to(source):
            raise ValueError('preparer-must-be-external')
        result['preparer_sha256'] = hashlib.sha256(prepare_script.read_bytes()).hexdigest()
        stage = 'restore-only-release-metadata'
        subprocess.run(['git', 'restore', '--source=HEAD', '--worktree', '--', *METADATA],
                       cwd=source, capture_output=True, check=True)
        stage = 'run-corrected-metadata-preparation'
        environment = dict(os.environ, GITHUB_REF='refs/tags/' + TAG)
        subprocess.run(['node', str(prepare_script)], cwd=source, env=environment,
                       capture_output=True, timeout=30, check=True)
        stage = 'verify-clean-checkout'
        if subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'],
                                   cwd=source, text=True).strip():
            raise ValueError('source-remains-dirty')
        result.update(passed=True, changed_release_metadata=list(METADATA), checkout_clean=True)
    except Exception:
        # No arbitrary changed paths, subprocess text or exception messages leave CI.
        result.update(error='metadata-correction-failed', phase=stage)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--helper-root', type=Path)
    parser.add_argument('--resources', type=Path)
    parser.add_argument('--repair-metadata-from-original', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    options = parser.parse_args()
    if options.repair_metadata_from_original:
        result = repair_metadata(options.source_root, options.repair_metadata_from_original)
    else:
        if not options.helper_root or not options.resources:
            parser.error('--helper-root and --resources are required for the native probe')
        result = diagnose(options.source_root, options.helper_root, options.resources)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
