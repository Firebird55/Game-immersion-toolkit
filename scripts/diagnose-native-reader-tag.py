"""Read-only reporter for the original failed Windows v0.23.0 checkout.

This never grants release acceptance: the probe reporter is deliberately newer
than the immutable source whose helper and dependencies are being diagnosed.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
TAG = 'v0.23.0'
SOURCE = 'eb27e74e084dde6f4b2dab0a7b486838a8bcb781'


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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', required=True, type=Path)
    parser.add_argument('--helper-root', required=True, type=Path)
    parser.add_argument('--resources', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    options = parser.parse_args()
    result = diagnose(options.source_root, options.helper_root, options.resources)
    options.output.parent.mkdir(parents=True, exist_ok=True)
    options.output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(result))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
