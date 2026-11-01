"""Authored archive closures exercise review independently of upstream downloads."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviewer = load('zzz_input_reviewer', 'scripts/review-desktop-inputs.py')
adapter = load('zzz_review_adapter', 'packaging/runtime-bundle/zzz_review.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def closure(tmp_path, monkeypatch):
    from backend.prebuilt_node_reader import ZZZ_SCRIPTS
    archives, pins = {}, []

    def archive(name, role, files, notices=()):
        path = tmp_path / (name + '.tar.gz')
        with tarfile.open(path, 'w:gz') as output:
            for member, data in files.items():
                info = tarfile.TarInfo(member)
                info.size = len(data)
                output.addfile(info, io.BytesIO(data))
        pin = {'name': name, 'role': role, 'archive': path.name, 'sha256': sha(path.read_bytes()),
               'url': 'https://supplier.invalid/' + path.name}
        if role == 'source':
            pin['prefix'] = name + '/'
            pin['notices'] = [{'member': name + '/' + n, 'sha256': sha(files[name + '/' + n])} for n in notices]
        else:
            pin['files'] = [{'member': member, 'sha256': sha(data)} for member, data in files.items()]
        archives[name] = path
        pins.append(pin)
        return pin

    terms, source = b'Authored full permission and copyright terms', b'// authored preferred source'
    archive('reader-source', 'source', {'reader-source/LICENSE': terms, 'reader-source/galgame-perform.ts': source}, ('LICENSE',))
    ooz = {'package.json': b'{"version":"fixture"}', 'index.js': b'// authored module', 'LICENSE': terms}
    xxhash = {'package.json': b'{"version":"fixture"}', 'LICENSE.md': terms}
    archive('ooz-source', 'source', {'ooz-source/' + k: v for k, v in ooz.items()}, ('LICENSE',))
    archive('xxhash-source', 'source', {'xxhash-source/' + k: v for k, v in xxhash.items()}, ('LICENSE.md',))
    archive('ooz-wasm', 'runtime', {'package/' + k: v for k, v in (ooz | {'build/ooz.js': b'// authored WASM module'}).items()})
    archive('xxhash-wasm', 'runtime', {'package/' + k: v for k, v in (xxhash | {'esm/xxhash-wasm.js': b'// authored hash module'}).items()})
    compiler = archive('typescript', 'build-only', {'package/lib/typescript.js': b'// authored compiler'})
    compiler['version'] = '5.9.3'
    policy = {'schema': 'toolkit-zzz-inputs-v1', 'archives': pins, 'upstream': {
        'path': 'galgame-perform.ts', 'sha256': sha(source), 'license_path': 'LICENSE', 'license_sha256': sha(terms)}}
    source_root = tmp_path / 'source'
    names = (*adapter.OWNED, *('scripts/' + name for name in ZZZ_SCRIPTS))
    for name in names:
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(policy).encode() if name == adapter.zzz_inputs.POLICY else (ROOT / name).read_bytes())
    monkeypatch.setattr(adapter, 'ROOT', source_root)
    compiled = b'// authored transpiled output'
    monkeypatch.setattr(adapter, 'transpile', lambda *args: compiled)
    monkeypatch.setattr(adapter, 'inspect_ooz_build', lambda *args: set())
    monkeypatch.setattr(adapter, 'validate_runtime', lambda *args: None)
    files = adapter.zzz_inputs.retained_members(policy, archives)
    prefix = adapter.zzz_inputs.PREFIX
    files[prefix + 'upstream/galgame-perform.mjs'] = compiled
    files[prefix + 'sources/transpile.cjs'] = (source_root / adapter.RECIPE).read_bytes()
    files[prefix + 'TOOLKIT-LICENSE'] = (source_root / 'LICENSE').read_bytes()
    files[prefix + 'inputs.json'] = (json.dumps(policy, indent=2) + '\n').encode()
    files[prefix + 'runtime.json'] = b'{}'  # Runtime contract has its own focused tests.
    for name in ZZZ_SCRIPTS:
        files[prefix + 'scripts/' + name] = (source_root / 'scripts' / name).read_bytes()
    files[prefix + 'BUILD-RECIPE.json'] = json.dumps({'schema': 'toolkit-zzz-build-recipe-v1',
        'compiler': {'version': compiler['version'], 'url': compiler['url'], 'archive_sha256': compiler['sha256']},
        'node_version': '24.22.1',
        'recipe_sha256': sha(files[prefix + 'sources/transpile.cjs']), 'input_sha256': sha(source), 'output_sha256': sha(compiled)}).encode()
    root = tmp_path / 'runtime'
    inventory = []
    for name, data in files.items():
        path = root / '_internal' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        inventory.append({'path': '_internal/' + name, 'bytes': len(data), 'sha256': sha(data)})
    review = reviewer.Review(root, {'files': inventory}, 'windows-x64')
    review.native_archive_paths = {pin['sha256']: archives[pin['name']] for pin in pins}
    snapshot = SimpleNamespace(files={name: (source_root / name).read_bytes() for name in names})
    return review, snapshot


def test_exact_archive_and_authored_recipe_closure(closure):
    review, snapshot = closure
    adapter.inspect(review, snapshot, reviewer.source_matches)
    assert review.checks['native_inputs']['evidence'][-1]['zzz_transpilation'] == 'exact-byte-replay'
    assert review.checks['complete_notices']['evidence'][-1]['compiler_shipped'] is False


@pytest.mark.parametrize('change', ['notice', 'preferred_source', 'compiled_output', 'source_recipe', 'archive', 'record', 'extra_source'])
def test_rehashed_or_declared_evidence_cannot_replace_exact_inputs(closure, change):
    review, snapshot = closure
    if change == 'archive':
        review.native_archive_paths.clear()
    elif change == 'source_recipe':
        snapshot.files[adapter.RECIPE] = b'// arbitrary replacement'
    elif change == 'extra_source':
        name = adapter.PREFIX + 'sources/unreviewed-library.js'
        data = b'// an unreviewed addition, consistently inventoried'
        (review.root / name).write_bytes(data)
        review.inventory[name] = {'bytes': len(data), 'sha256': sha(data)}
    else:
        paths = {'notice': 'dependencies/ooz/LICENSE', 'preferred_source': 'upstream/galgame-perform.ts',
                 'compiled_output': 'upstream/galgame-perform.mjs', 'record': 'BUILD-RECIPE.json'}
        name = adapter.PREFIX + paths[change]
        data = b'{}' if change == 'record' else b'changed but consistently rehashed'
        (review.root / name).write_bytes(data)
        review.inventory[name].update(bytes=len(data), sha256=sha(data))
    with pytest.raises(ValueError):
        adapter.inspect(review, snapshot, reviewer.source_matches)
    assert review.checks['corresponding_sources']['blockers']
