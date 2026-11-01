"""Build the real ZZZ scene reader into compiler-free immutable resources.

Only the build host executes the exact retained TypeScript compiler. All game
assets remain local runtime inputs and are never collected by this script.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'packaging/runtime-bundle'))
import zzz_inputs
from backend.game_tools import READER_REVISION, READER_SHA
from backend.node_tools import ARCHIVES, NODE_VERSION, host_platform
from backend.prebuilt_node_reader import ZZZ_PREFIX, ZZZ_SCHEMA, ZZZ_SCRIPTS, ZZZ_DEPENDENCIES, _no_links, _unique_json
from backend.runtime_bundle import relative_resource

RECIPE = 'packaging/zzz-reader/transpile.cjs'
TARGETS = ('win-x64', 'linux-x64', 'darwin-arm64')


def digest(data):
    return hashlib.sha256(data).hexdigest()


def encoded(value):
    return (json.dumps(value, indent=2) + '\n').encode()


def verified_node(executable: Path):
    executable = executable.absolute()
    _no_links(executable)
    runtime_path = executable.parent / 'runtime.json'
    _no_links(runtime_path)
    if runtime_path.stat().st_size > 16384:
        raise ValueError('Oversized build Node manifest')
    runtime = json.loads(runtime_path.read_text(encoding='utf-8'), object_pairs_hook=_unique_json)
    target = host_platform()
    expected = 'node.exe' if target.startswith('win-') else 'node'
    if (target not in ARCHIVES or runtime.get('schema') != 'toolkit-node-runtime-v1'
            or runtime.get('platform') != target or runtime.get('version') != NODE_VERSION
            or runtime.get('archive_sha256') != ARCHIVES[target][1]
            or executable.name != expected or runtime.get('executable') != expected
            or digest(executable.read_bytes()) != runtime.get('executable_sha256')):
        raise ValueError('The build requires the already collected pinned app-local Node runtime')
    return executable


def transpile(reader_bytes: bytes, compiler_path: Path, node_path: Path, work: Path) -> bytes:
    """Replay the owned recipe with explicitly verified inputs in fresh work."""
    import os
    work.mkdir(parents=True, exist_ok=False)
    source, compiled, recipe = work / 'reader.ts', work / 'reader.mjs', work / 'transpile.cjs'
    source.write_bytes(reader_bytes)
    recipe.write_bytes((ROOT / RECIPE).read_bytes())
    environment = {'PATH': '', **{name: value for name, value in os.environ.items()
                    if name.lower() in {'systemroot', 'windir', 'temp', 'tmp', 'tmpdir'}}}
    completed = subprocess.run([str(node_path), str(recipe), str(compiler_path), str(source), str(compiled)],
        cwd=work, env=environment, capture_output=True, timeout=120)
    if completed.returncode or not compiled.is_file():
        raise ValueError('Pinned reader transpilation failed')
    return compiled.read_bytes()


def build(output: Path, evidence_root: Path, target: str, node_executable: Path, ooz_build_root: Path,
          *, input_cache: Path | None = None):
    output, evidence_root = output.absolute(), evidence_root.absolute()
    if target not in TARGETS or output.exists() or evidence_root.exists():
        raise ValueError('Choose a supported platform and fresh output/evidence folders')
    for path in (output, evidence_root):
        _no_links(path)
    if output == evidence_root or output in evidence_root.parents or evidence_root in output.parents:
        raise ValueError('Resource output and build evidence must be separate folders')
    node = verified_node(node_executable)
    spec = importlib.util.spec_from_file_location('toolkit_ooz_builder', ROOT / 'scripts/build-ooz-runtime.py')
    ooz_builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(ooz_builder)
    ooz_receipt = ooz_builder.verify_build(ooz_build_root)
    decoder = (ooz_build_root / 'build/ooz.js').read_bytes()
    if digest(decoder) != ZZZ_DEPENDENCIES['ooz/build/ooz.js']:
        raise ValueError('Source-built decoder differs from the production runtime pin')
    pins = zzz_inputs.read_pins()
    if pins['upstream']['commit'] != READER_REVISION or pins['upstream']['sha256'] != READER_SHA:
        raise ValueError('Reader policy differs from runtime pin')
    evidence_root.mkdir(parents=True)
    archives = zzz_inputs.acquire_inputs(input_cache or evidence_root / 'inputs', pins)
    files = zzz_inputs.retained_members(pins, archives)
    files[ZZZ_PREFIX + 'dependencies/ooz/build/ooz.js'] = decoder
    for name in [*ooz_receipt['files'], 'ooz-build.json']:
        relative_resource(name)
        files[ZZZ_PREFIX + 'sources/ooz-build/' + name] = (ooz_build_root / name).read_bytes()
    compiler_pin = next(pin for pin in pins['archives'] if pin['name'] == 'typescript')
    compiler_members = zzz_inputs.archive_members(archives['typescript'], compiler_pin)
    compiler_root = evidence_root / 'compiler'
    compiler_root.mkdir()
    # Include the compiler's complete terms in build evidence, not runtime code.
    for item in compiler_pin['files']:
        name = item['member'].removeprefix('package/')
        relative_resource(name)
        destination = compiler_root / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(compiler_members[item['member']])
    if json.loads((compiler_root / 'package.json').read_bytes()).get('version') != '5.9.3':
        raise ValueError('Compiler identity differs')
    source = files[ZZZ_PREFIX + 'upstream/galgame-perform.ts']
    compiled = transpile(source, compiler_root / 'lib/typescript.js', node, evidence_root / 'transpile')
    recipe = (ROOT / RECIPE).read_bytes()
    files[ZZZ_PREFIX + 'upstream/galgame-perform.mjs'] = compiled
    files[ZZZ_PREFIX + 'sources/transpile.cjs'] = recipe
    files[ZZZ_PREFIX + 'TOOLKIT-LICENSE'] = (ROOT / 'LICENSE').read_bytes()
    files[ZZZ_PREFIX + 'inputs.json'] = encoded(pins)
    for name in ZZZ_SCRIPTS:
        files[ZZZ_PREFIX + 'scripts/' + name] = (ROOT / 'scripts' / name).read_bytes()
    recipe_record = {'schema': 'toolkit-zzz-build-recipe-v1', 'compiler': {'version': '5.9.3',
        'archive_sha256': compiler_pin['sha256'], 'url': compiler_pin['url']},
        'recipe_sha256': digest(recipe), 'input_sha256': digest(source),
        'output_sha256': digest(compiled), 'node_version': NODE_VERSION,
        'ooz_build_sha256': digest(files[ZZZ_PREFIX + 'sources/ooz-build/ooz-build.json']),
        'steps': ['Expose unpackMhyFile export', 'Transpile ES2022/ESNext',
                  'Replace two package imports with explicit app-local dependency paths']}
    files[ZZZ_PREFIX + 'BUILD-RECIPE.json'] = encoded(recipe_record)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=normal'], cwd=ROOT, text=True).strip())
    inventory = {name.removeprefix(ZZZ_PREFIX): {'bytes': len(data), 'sha256': digest(data)} for name, data in sorted(files.items())}
    identity = digest(json.dumps(inventory, sort_keys=True, separators=(',', ':')).encode())
    runtime = {'schema': ZZZ_SCHEMA, 'platform': target, 'source_commit': commit, 'source_dirty': dirty,
        'upstream_revision': READER_REVISION, 'upstream_sha256': READER_SHA,
        'ooz_build_sha256': recipe_record['ooz_build_sha256'],
        'inputs_sha256': digest(files[ZZZ_PREFIX + 'inputs.json']), 'build_id': identity, 'files': inventory}
    files[ZZZ_PREFIX + 'runtime.json'] = encoded(runtime)
    source_names = ['LICENSE', RECIPE, 'scripts/build-zzz-toolchain.py', zzz_inputs.POLICY,
                    'backend/prebuilt_node_reader.py', 'backend/game_tools.py',
                    'scripts/build-ooz-runtime.py', 'packaging/zzz-reader/ooz-build.json',
                    'packaging/runtime-bundle/zzz_inputs.py', *('scripts/' + name for name in ZZZ_SCRIPTS)]
    resource = {'schema': 'toolkit-native-resources-v1', 'platform': target, 'source_commit': commit,
        'source_dirty': dirty, 'source_inputs': {name: digest((ROOT / name).read_bytes()) for name in source_names},
        'components': {pin['name']: {key: pin[key] for key in ('url', 'sha256', 'revision', 'version', 'role') if key in pin}
                       for pin in pins['archives']},
        'rights_review': 'pending', 'native_acceptance': 'pending',
        'files': [{'path': name, 'bytes': len(data), 'sha256': digest(data)} for name, data in sorted(files.items())]}
    output.mkdir(parents=True)
    for name, data in files.items():
        relative_resource(name)
        if not name.startswith(ZZZ_PREFIX):
            raise ValueError('Unexpected resource namespace')
        destination = output / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data)
    (output / 'resource-manifest.json').write_bytes(encoded(resource))
    (evidence_root / 'BUILD-RECIPE.json').write_bytes(encoded(recipe_record))
    (evidence_root / 'resource-manifest.json').write_bytes(encoded(resource))
    return resource


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--evidence-root', type=Path, required=True)
    parser.add_argument('--platform', choices=TARGETS, required=True)
    parser.add_argument('--node-executable', type=Path, required=True)
    parser.add_argument('--ooz-build-root', type=Path, required=True)
    parser.add_argument('--input-cache', type=Path)
    args = parser.parse_args()
    result = build(args.output, args.evidence_root, args.platform, args.node_executable, args.ooz_build_root.absolute(), input_cache=args.input_cache)
    print(json.dumps({'platform': result['platform'], 'files': len(result['files']), 'native_acceptance': 'pending'}))
