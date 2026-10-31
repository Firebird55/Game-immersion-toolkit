"""Collect exact supplier WolvenKit/.NET bytes for an immutable desktop bundle.

This constructs a candidate resource closure. Native acceptance and complete
redistribution review of supplier native dependencies remain separate gates.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.cyberpunk_toolchain import (PREFIX, SUPPLIERS, TARGET, INVENTORY_SHA256,
    VERSION, RUNTIME, SDK, OWNED_FILES, acquire, materialize, _sha)
from backend.prebuilt_readers import _no_links


def build(output: Path, target: str, cache: Path, *, sdk_root: Path | None = None):
    if target != TARGET:
        raise ValueError('WolvenKit 9.0.1 supplies a Windows x64 dependency closure; no verified POSIX package is available')
    output = output.absolute()
    _no_links(output)
    _no_links(cache)
    if output.exists():
        raise ValueError('Choose a fresh resource output folder')
    archives = {name: acquire(cache / (name + '.archive'), supplier) for name, supplier in SUPPLIERS.items()}
    stage = output.with_name('.cyberpunk-' + uuid.uuid4().hex)
    inputs = ['backend/cyberpunk_toolchain.py', 'scripts/build-cyberpunk-toolchain.py', 'scripts/game-readers/CyberpunkReader.cs']
    try:
        materialize(stage / PREFIX, archives, sdk_root=sdk_root)
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip())
        result = {'schema': 'toolkit-native-resources-v1', 'platform': target,
            'source_commit': commit, 'source_dirty': dirty,
            'source_inputs': {name: _sha(ROOT / name) for name in inputs},
            'components': {'wolvenkit': {'version': VERSION, **SUPPLIERS['wolvenkit'],
                'source': SUPPLIERS['source'], 'license': 'GPL-3.0 and supplier dependency notices'},
                'dotnet': {'version': RUNTIME, **SUPPLIERS['dotnet'], 'license': 'MIT and included THIRD-PARTY-NOTICES.TXT'},
                'owned_entry': {'build_sdk': SDK, 'license': 'Firebird55 Attribution License 1.0; supplier-linkage review pending',
                    'source_sha256': OWNED_FILES['sources/ToolkitCyberpunkReader.cs'],
                    'sha256': OWNED_FILES['reader/ToolkitCyberpunkReader.dll'],
                    'build': 'deterministic compiler with fixed runtime/supplier references, no restore'}},
            'inventory_sha256': INVENTORY_SHA256,
            'rights_review': 'pending', 'native_acceptance': 'pending',
            'files': [{'path': path.relative_to(stage).as_posix(), 'bytes': path.stat().st_size, 'sha256': _sha(path)}
                      for path in sorted(stage.rglob('*')) if path.is_file()]}
        (stage / 'resource-manifest.json').write_text(json.dumps(result, sort_keys=True, indent=2) + '\n', encoding='utf-8')
        os.rename(stage, output)
        return result
    finally:
        if stage.exists():
            shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--platform', required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--sdk-root', type=Path, help='Build-host .NET SDK 10.0.403 directory; not a runtime prerequisite')
    options = parser.parse_args()
    result = build(options.output, options.platform, options.cache, sdk_root=options.sdk_root)
    print(json.dumps({'platform': result['platform'], 'files': len(result['files']),
                      'rights_review': result['rights_review'], 'native_acceptance': result['native_acceptance']}))
