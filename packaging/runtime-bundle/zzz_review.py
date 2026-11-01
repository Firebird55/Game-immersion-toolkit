"""Independent exact ZZZ source, dependency and transpilation inspection."""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace

import zzz_inputs

ROOT = Path(__file__).resolve().parents[2]
PREFIX = '_internal/' + zzz_inputs.PREFIX
RECIPE = 'packaging/zzz-reader/transpile.cjs'
OWNED = ('scripts/build-zzz-toolchain.py', 'packaging/runtime-bundle/zzz_inputs.py',
         'packaging/runtime-bundle/zzz_review.py', zzz_inputs.POLICY, RECIPE,
         'backend/prebuilt_node_reader.py', 'backend/game_tools.py', 'backend/node_tools.py',
         'scripts/build-ooz-runtime.py', 'packaging/zzz-reader/ooz-build.json', 'LICENSE')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def transpile(source: bytes, compiler: bytes, recipe: bytes, node: str) -> bytes:
    """Replay only the pinned compiler and owned recipe, never game-reader code."""
    with tempfile.TemporaryDirectory(prefix='toolkit-zzz-review-') as directory:
        work = Path(directory)
        for name, data in (('reader.ts', source), ('typescript.cjs', compiler), ('transpile.cjs', recipe)):
            (work / name).write_bytes(data)
        environment = {key: value for key, value in os.environ.items()
                       if key.lower() in {'systemroot', 'windir', 'temp', 'tmp', 'tmpdir', 'path'}}
        result = subprocess.run([node, str(work / 'transpile.cjs'), str(work / 'typescript.cjs'),
            str(work / 'reader.ts'), str(work / 'reader.mjs')], cwd=work, env=environment,
            capture_output=True, timeout=120)
        if result.returncode or not (work / 'reader.mjs').is_file():
            raise ValueError('Exact ZZZ compiler replay failed.')
        return (work / 'reader.mjs').read_bytes()


def inspect(review, snapshot, source_matches, *, node='node'):
    if not any(name.startswith(PREFIX) for name in review.inventory):
        return
    try:
        inspect_selection(review, snapshot, source_matches, node=node)
    except (OSError, ValueError, KeyError, RuntimeError, subprocess.SubprocessError):
        for check in ('complete_notices', 'corresponding_sources'):
            review.block(check, 'zzz-review-incomplete', 'Exact ZZZ dependencies, full notices and preferred source could not be verified.')
        raise


def inspect_selection(review, snapshot, source_matches, *, node):
    from backend.prebuilt_node_reader import ZZZ_SCRIPTS
    from backend.node_tools import NODE_VERSION
    owned = (*OWNED, *('scripts/' + name for name in ZZZ_SCRIPTS))
    for name in owned:
        if name not in snapshot.files or not source_matches(snapshot.files[name], sha((ROOT / name).read_bytes()), name):
            raise ValueError('ZZZ inspection code differs from the candidate source: ' + name)
    pins = json.loads(snapshot.files[zzz_inputs.POLICY])
    if pins.get('schema') != 'toolkit-zzz-inputs-v1':
        raise ValueError('Unknown ZZZ input pin schema.')
    validate_runtime(review)

    def delivered(name, data):
        name = '_internal/' + name
        value = review.inventory.get(name, {})
        if value.get('link') or value.get('sha256') != sha(data) or value.get('bytes') != len(data):
            raise ValueError('ZZZ delivered resource differs: ' + name)
        if (review.root / name).read_bytes() != data:
            raise ValueError('ZZZ delivered bytes differ: ' + name)

    archives = {}
    for pin in pins['archives']:
        if pin['role'] == 'source':
            archives[pin['name']] = review.root / PREFIX / 'sources' / pin['archive']
        else:
            path = review.native_archive_paths.get(pin['sha256'])
            if path is None:
                raise ValueError('ZZZ review requires exact npm archive: ' + pin['name'])
            archives[pin['name']] = path
    expected = zzz_inputs.retained_members(pins, archives)
    rebuilt_name = zzz_inputs.PREFIX + 'dependencies/ooz/build/ooz.js'
    for name, data in expected.items():
        if name != rebuilt_name:
            delivered(name, data)
    for name in ZZZ_SCRIPTS:
        delivered(zzz_inputs.PREFIX + 'scripts/' + name, (ROOT / 'scripts' / name).read_bytes())
    delivered(zzz_inputs.PREFIX + 'TOOLKIT-LICENSE', (ROOT / 'LICENSE').read_bytes())
    delivered(zzz_inputs.PREFIX + 'sources/transpile.cjs', (ROOT / RECIPE).read_bytes())
    delivered(zzz_inputs.PREFIX + 'inputs.json', (json.dumps(pins, indent=2) + '\n').encode())

    compiler_pin = next(pin for pin in pins['archives'] if pin['name'] == 'typescript')
    compiler = zzz_inputs.archive_members(archives['typescript'], compiler_pin)['package/lib/typescript.js']
    source = expected[zzz_inputs.PREFIX + 'upstream/galgame-perform.ts']
    compiled = transpile(source, compiler, (ROOT / RECIPE).read_bytes(), node)
    delivered(zzz_inputs.PREFIX + 'upstream/galgame-perform.mjs', compiled)
    recipe = json.loads((review.root / PREFIX / 'BUILD-RECIPE.json').read_bytes())
    if (recipe.get('schema') != 'toolkit-zzz-build-recipe-v1'
            or recipe.get('compiler') != {key: compiler_pin[key] for key in ('version', 'url')} | {'archive_sha256': compiler_pin['sha256']}
            or recipe.get('node_version') != NODE_VERSION
            or recipe.get('recipe_sha256') != sha((ROOT / RECIPE).read_bytes())
            or recipe.get('input_sha256') != sha(source) or recipe.get('output_sha256') != sha(compiled)):
        raise ValueError('ZZZ build recipe differs from independently replayed inputs.')

    # A supplier-source snapshot does not prove the npm generated WASM. The
    # production collector supplies a separately verified source-build receipt.
    build_files = inspect_ooz_build(review, snapshot, source_matches)
    selected = {'_internal/' + name for name in expected} | set(build_files)
    selected.update(PREFIX + name for name in (
        'runtime.json', 'BUILD-RECIPE.json', 'inputs.json', 'TOOLKIT-LICENSE',
        'sources/transpile.cjs', 'upstream/galgame-perform.mjs',
        *('scripts/' + name for name in ZZZ_SCRIPTS)))
    if {name for name in review.inventory if name.startswith(PREFIX)} != selected:
        raise ValueError('ZZZ selection contains resources outside the exact inspected closure.')
    review.evidence('native_inputs', zzz_transpilation='exact-byte-replay', compiler_archive_sha256=compiler_pin['sha256'],
                    reader_output_sha256=sha(compiled), exact_dependency_members=len(expected))
    review.evidence('complete_notices', zzz_dependency_notices='exact-source-and-package-members', compiler_shipped=False)
    review.evidence('corresponding_sources', zzz_preferred_sources=[pin['sha256'] for pin in pins['archives'] if pin['role'] == 'source'],
                    basis='Exact retained preferred source and fixed compiler replay; WASM source-build evidence inspected separately.')


def validate_runtime(review):
    """Use the same closed resource contract as the installed reader, no spawn."""
    from backend.prebuilt_node_reader import production_zzz_reader
    resources = {name.removeprefix('_internal/'): entry['sha256'] for name, entry in review.inventory.items()
                 if name.startswith('_internal/') and not entry.get('link')}
    root = review.root / '_internal'
    layout = SimpleNamespace(mode='bundle', profile='runtime', resource_root=root,
        resources=resources, source_commit=review.receipt['source_commit'],
        work_root=review.root.parent / 'unused-review-work', resource=lambda name: root / name)
    production_zzz_reader(layout=layout)


def inspect_ooz_build(review, snapshot, source_matches):
    """Verify a known source build against independent source/output pins."""
    name = 'scripts/build-ooz-runtime.py'
    spec = importlib.util.spec_from_file_location('toolkit_ooz_review_builder', ROOT / name)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    build_root = review.root / PREFIX / 'sources/ooz-build'
    receipt = builder.verify_build(build_root)
    recipe = json.loads((review.root / PREFIX / 'BUILD-RECIPE.json').read_bytes())
    if recipe.get('ooz_build_sha256') != sha((build_root / 'ooz-build.json').read_bytes()):
        raise ValueError('ZZZ reader recipe does not bind the inspected source-build receipt.')
    compiled = receipt['files']['build/ooz.js']
    actual = review.inventory.get(PREFIX + 'dependencies/ooz/build/ooz.js', {})
    if actual.get('link') or any(actual.get(key) != compiled[key] for key in ('bytes', 'sha256')):
        raise ValueError('ZZZ selected WASM differs from its verified source build.')
    data = (review.root / PREFIX / 'dependencies/ooz/build/ooz.js').read_bytes()
    if sha(data) != compiled['sha256'] or len(data) != compiled['bytes']:
        raise ValueError('ZZZ selected WASM bytes differ from its verified source build.')
    review.evidence('native_inputs', zzz_decompressor='pinned-source-build', output_sha256=compiled['sha256'],
                    toolchain_version=receipt['toolchain']['version'], toolchain_archive_sha256=receipt['toolchain']['sha256'])
    review.evidence('corresponding_sources', zzz_decompressor_source=receipt['source']['sha256'],
                    emscripten_runtime_source=receipt['emscripten_source']['sha256'],
                    basis='Exact preferred source, full terms and build recipe retained; independently pinned generated output, not a claim to reproduce the undocumented npm build.')
    return {PREFIX + 'sources/ooz-build/' + name for name in (*receipt['files'], 'ooz-build.json')}
