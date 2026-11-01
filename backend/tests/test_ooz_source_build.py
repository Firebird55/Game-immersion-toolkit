"""Authored build inventories exercise fixed source/output trust without downloads."""
import copy
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
import urllib.error
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('ooz_source_build', ROOT / 'scripts/build-ooz-runtime.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def receipt_for(pins, target, files):
    return {'schema': builder.SCHEMA, 'target': target, 'source': pins['source'],
            'emscripten_source': pins['emscripten_source'],
            'toolchain': {'version': pins['toolchain']['version'],
                          'release_revision': pins['toolchain']['release_revision'],
                          **pins['toolchain']['archives'][target]},
            'node': {'version': pins['node']['version'], 'sha256': pins['node']['executable_sha256'][target]},
            'sources': pins['sources'], 'arguments': pins['arguments'], 'files': files}


@pytest.fixture
def authored_build(tmp_path, monkeypatch):
    pins = copy.deepcopy(builder.read_policy())
    root = tmp_path / 'built'
    root.mkdir()
    output = b'// authored embedded WASM output\n'
    pins['output'].update(sha256=sha(output), bytes=len(output))
    contents = {pins['output']['path']: output}
    for key in ('source', 'emscripten_source'):
        data = ('authored complete preferred source ' + key).encode()
        pins[key]['sha256'] = sha(data)
        contents['sources/' + pins[key]['archive']] = data
    for index, notice in enumerate(pins['notices']):
        data = ('authored full license terms ' + str(index)).encode()
        notice['sha256'] = sha(data)
        contents[notice['path']] = data
    contents.update({name: builder.text_input(path) for name, path in builder.OWNED.items()})
    for name, data in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(builder, 'read_policy', lambda: pins)
    receipt = receipt_for(pins, 'windows-x64', builder.inventory(root))
    (root / 'ooz-build.json').write_text(json.dumps(receipt), encoding='utf-8')
    return root, pins, receipt


def test_exact_retained_source_notices_recipe_and_output_pass(authored_build):
    root, _, receipt = authored_build
    assert builder.verify_build(root) == receipt
    assert 'recipe/LICENSE' in receipt['files']


@pytest.mark.parametrize('name', ['build/ooz.js', 'sources/ooz-source.tar.gz',
                                  'notices/ooz-LICENSE', 'recipe/build-ooz-runtime.py',
                                  'recipe/ooz-build.json', 'recipe/LICENSE'])
def test_forged_self_consistent_receipt_cannot_change_fixed_inputs(authored_build, name):
    root, _, receipt = authored_build
    (root / name).write_bytes(b'changed input and forged receipt')
    receipt['files'] = builder.inventory(root)
    receipt['approved'] = True
    (root / 'ooz-build.json').write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='exact pins'):
        builder.verify_build(root)


@pytest.mark.parametrize('field', ['source', 'emscripten_source', 'toolchain', 'node', 'sources', 'arguments'])
def test_source_or_build_identity_cannot_be_claimed_by_receipt(authored_build, field):
    root, _, receipt = authored_build
    receipt[field] = {'unreviewed': True}
    (root / 'ooz-build.json').write_text(json.dumps(receipt), encoding='utf-8')
    with pytest.raises(ValueError, match='fixed source and toolchain'):
        builder.verify_build(root)


@pytest.mark.parametrize('kind', ['extra-file', 'empty-directory', 'missing-file', 'large-receipt', 'list-receipt'])
def test_closed_inventory_and_bounded_receipt(authored_build, kind):
    root, _, receipt = authored_build
    if kind == 'extra-file':
        (root / 'unexpected.dll').write_bytes(b'not a build input')
        receipt['files'] = builder.inventory(root)
        (root / 'ooz-build.json').write_text(json.dumps(receipt), encoding='utf-8')
    elif kind == 'empty-directory':
        (root / 'unexpected').mkdir()
    elif kind == 'missing-file':
        (root / 'recipe/LICENSE').unlink()
    elif kind == 'large-receipt':
        (root / 'ooz-build.json').write_bytes(b' ' * (2 * 1024 * 1024 + 1))
    else:
        (root / 'ooz-build.json').write_text('[]', encoding='utf-8')
    with pytest.raises(ValueError):
        builder.verify_build(root)


@pytest.mark.parametrize('name', ['../outside', '/absolute', 'a/../../outside', r'a\outside',
                                 'C:/outside', 'a//b', './a', 'a/./b'])
def test_archive_preflight_rejects_noncanonical_member_before_writing(tmp_path, name):
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as output:
        # ZipInfo's Windows constructor normalizes backslashes; set the stored
        # name afterwards to exercise an archive authored on another platform.
        member = zipfile.ZipInfo('placeholder')
        member.filename = name
        output.writestr(member, b'unsafe')
    destination = tmp_path / 'extracted'
    with pytest.raises(ValueError):
        builder.extract(archive, destination)
    assert not list(destination.iterdir())


def test_tar_link_cannot_escape_destination(tmp_path):
    archive = tmp_path / 'input.tar'
    with tarfile.open(archive, 'w') as output:
        member = tarfile.TarInfo('link')
        member.type = tarfile.SYMTYPE
        member.linkname = '../outside'
        output.addfile(member)
    with pytest.raises(tarfile.FilterError):
        builder.extract(archive, tmp_path / 'extracted')
    assert not (tmp_path / 'outside').exists()


def test_compiler_sources_allow_only_omitted_editor_metadata(tmp_path):
    root, archive = tmp_path / 'compiler', tmp_path / 'source.tar'
    names = {'src/runtime.js': b'authored runtime', 'system/lib/runtime.c': b'authored libc'}
    names.update({f'system/include/file{i}.h': str(i).encode() for i in range(100)})
    with tarfile.open(archive, 'w') as output:
        for name, data in {**names, 'system/.gitignore': b'build', 'system/.clang-tidy': b'rules'}.items():
            member = tarfile.TarInfo('source/' + name)
            member.size = len(data)
            output.addfile(member, io.BytesIO(data))
    for name, data in names.items():
        path = root / 'emscripten' / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    builder.verify_compiler_sources(root, archive, {'prefix': 'source/'})
    (root / 'emscripten/src/runtime.js').write_bytes(b'changed runtime')
    with pytest.raises(ValueError, match='differs'):
        builder.verify_compiler_sources(root, archive, {'prefix': 'source/'})
    (root / 'emscripten/src/runtime.js').unlink()
    with pytest.raises(FileNotFoundError):
        builder.verify_compiler_sources(root, archive, {'prefix': 'source/'})


def test_verified_cache_never_accepts_changed_bytes(tmp_path, monkeypatch):
    data = b'authored pinned compiler archive'
    pin = {'archive': 'compiler.zip', 'url': 'https://supplier.invalid/fixed.zip', 'sha256': sha(data)}
    path = tmp_path / pin['archive']
    path.write_bytes(data)
    monkeypatch.setattr(builder.urllib.request, 'urlopen', lambda *a, **kw: pytest.fail('No network for verified cache'))
    assert builder.acquire(pin, tmp_path) == path
    path.write_bytes(b'changed')
    with pytest.raises(ValueError, match='differs'):
        builder.acquire(pin, tmp_path)


def test_transient_download_retries_but_hash_failure_does_not(tmp_path, monkeypatch):
    data, calls = b'authored pinned archive', []
    pin = {'archive': 'compiler.zip', 'url': 'https://supplier.invalid/fixed.zip', 'sha256': sha(data)}
    def download(*args, **kwargs):
        calls.append(1)
        if len(calls) < 3:
            raise urllib.error.URLError('temporary connection failure')
        return io.BytesIO(data)
    monkeypatch.setattr(builder.urllib.request, 'urlopen', download)
    monkeypatch.setattr(builder.time, 'sleep', lambda _: None)
    assert builder.acquire(pin, tmp_path).read_bytes() == data
    assert len(calls) == 3
    assert not list(tmp_path.glob('*.partial-*'))
    (tmp_path / pin['archive']).unlink()
    calls.clear()
    def changed(*args, **kwargs):
        calls.append(1)
        return io.BytesIO(b'changed supplier content')
    monkeypatch.setattr(builder.urllib.request, 'urlopen', changed)
    with pytest.raises(ValueError, match='differs'):
        builder.acquire(pin, tmp_path)
    assert len(calls) == 1
    assert not list(tmp_path.iterdir())


def test_build_environment_drops_developer_configuration(monkeypatch, tmp_path):
    for name in ('HOME', 'EMCC_CFLAGS', 'CFLAGS', 'CXXFLAGS', 'NODE_OPTIONS', 'EMSDK', 'EM_CONFIG', 'PATH'):
        monkeypatch.setenv(name, 'injected-development-setting')
    config = tmp_path / 'owned-config'
    env = builder.build_environment(config)
    assert env['EM_CONFIG'] == str(config)
    assert env['PATH'] == ''
    assert env['SOURCE_DATE_EPOCH'] == '0'
    assert not {'HOME', 'EMCC_CFLAGS', 'CFLAGS', 'CXXFLAGS', 'NODE_OPTIONS', 'EMSDK'} & env.keys()


def test_build_rejects_overlapping_writable_roots_before_acquisition(tmp_path):
    with pytest.raises(ValueError, match='separate'):
        builder.build(tmp_path / 'work/output', tmp_path / 'work', tmp_path / 'cache', tmp_path / 'node')


def test_production_recipe_uses_relative_inputs_embedded_wasm_and_supported_targets():
    pins = builder.read_policy()
    assert set(pins['toolchain']['archives']) == {'windows-x64', 'linux-x64', 'macos-arm64', 'macos-x64'}
    assert set(pins['node']['executable_sha256']) == set(pins['toolchain']['archives'])
    assert all(not Path(name).is_absolute() and name.startswith('lib/') for name in pins['sources'])
    assert '-sSINGLE_FILE=1' in pins['arguments']
    assert '-sEXPORT_ES6=1' in pins['arguments']
    assert '-sEXPORTED_RUNTIME_METHODS=["HEAPU8"]' in pins['arguments']
    # Emscripten defaults to os.linesep; its documented compiler option makes
    # the same generated JS byte-identical on Windows, Linux and macOS.
    index = pins['arguments'].index('--output-eol')
    assert pins['arguments'][index + 1] == 'linux'
    assert pins['source']['revision'] in pins['source']['url']
    assert pins['emscripten_source']['revision'] in pins['emscripten_source']['url']
    assert all(pins['toolchain']['release_revision'] in p['url'] for p in pins['toolchain']['archives'].values())


def test_compiler_mismatch_reports_only_safe_identity_metadata(tmp_path):
    compiled = tmp_path / 'private-output.js'
    data = b'authored changed output containing private diagnostic text'
    compiled.write_bytes(data)
    with pytest.raises(ValueError, match='fixed decoder pin') as error:
        builder.verify_compiled_output(compiled, {'sha256': 'a' * 64, 'bytes': 1}, 'linux-x64')
    message = str(error.value)
    assert sha(data) in message and str(len(data)) in message and 'linux-x64' in message
    assert str(tmp_path) not in message
    assert data.decode() not in message
    builder.verify_compiled_output(compiled, {'sha256': sha(data), 'bytes': len(data)}, 'linux-x64')


def test_runtime_decoder_pin_matches_fixed_compiler_output():
    from backend.prebuilt_node_reader import ZZZ_DEPENDENCIES
    assert ZZZ_DEPENDENCIES['ooz/build/ooz.js'] == builder.read_policy()['output']['sha256']
