"""A complete authored resource closure exercises independent acceptance review."""
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import tarfile
from types import SimpleNamespace
import zipfile

import pytest

ROOT = Path(__file__).resolve().parents[2]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


reviewer = load('cyberpunk_input_reviewer', 'scripts/review-desktop-inputs.py')
adapter = load('cyberpunk_adapter', 'packaging/runtime-bundle/cyberpunk_review.py')
collector = load('cyberpunk_collector', 'scripts/cyberpunk_redistribution.py')


def sha(data):
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def closure(tmp_path, monkeypatch):
    archives, pinned = {}, {}

    def archive(name, files, tar=False):
        path = tmp_path / (name + ('.tar.gz' if tar else '.zip'))
        if tar:
            with tarfile.open(path, 'w:gz') as output:
                for member, data in files.items():
                    entry = tarfile.TarInfo(member)
                    entry.size = len(data)
                    output.addfile(entry, io.BytesIO(data))
        else:
            with zipfile.ZipFile(path, 'w') as output:
                for member, data in files.items():
                    output.writestr(member, data)
        pin = {'url': 'https://supplier.invalid/' + name, 'sha256': sha(path.read_bytes())}
        archives[name] = path
        pinned[pin['sha256']] = path
        return pin

    source_files = {'WolvenKit-9.0.1/LICENSE': b'Authored full supplier GPL terms',
                    'WolvenKit-9.0.1/WolvenKit.Core/Core.csproj': b'<Project />',
                    'WolvenKit-9.0.1/WolvenKit.Core/Core.cs': b'// authored source',
                    'WolvenKit-9.0.1/WolvenKit.Tests/game-sample.bin': b'excluded sample'}
    wkit_files = {name: b'MZ authored ' + name.encode() for name in (
        'WolvenKit.CLI.dll', 'WolvenKit.Common.dll', 'WolvenKit.Core.dll', 'WolvenKit.Modkit.dll', 'WolvenKit.RED4.dll')}
    net_files = {'dotnet.exe': b'MZ authored dotnet', 'runtime.dll': b'MZ authored runtime',
                 'LICENSE.txt': b'Authored full runtime terms', 'ThirdPartyNotices.txt': b'Authored full third-party terms'}
    suppliers = {'source': archive('source', source_files, tar=True),
        'wolvenkit': archive('wolvenkit', wkit_files), 'dotnet': archive('dotnet', net_files)}
    kraken = archive('kraken', {'kraken-fixture/decoder.cpp': b'// authored decoder'}, tar=True)
    package_files = {'lib/fixture.dll': b'MZ authored package', 'fixture.nuspec': b'<package />', 'LICENSE': b'Authored full package terms'}
    package = {**archive('fixture', package_files), 'archive': 'fixture.zip', 'name': 'fixture', 'version': '1',
        'members': [{'path': 'toolchains/cyberpunk/reader/fixture.dll', 'member': 'lib/fixture.dll', 'sha256': sha(package_files['lib/fixture.dll'])}],
        'notices': [{'member': 'LICENSE', 'sha256': sha(package_files['LICENSE'])}],
        'nuspec': {'member': 'fixture.nuspec', 'sha256': sha(package_files['fixture.nuspec'])},
        'metadata': {'license': {'text': 'MIT', 'attributes': {'type': 'expression'}}}}
    terms = b'Authored full compiler exception'
    term_path = tmp_path / 'terms.txt'
    term_path.write_bytes(terms)
    pinned[sha(terms)] = term_path
    pins = {'schema': 'toolkit-cyberpunk-redistribution-pins-v1', 'packages': [package],
        'compiler_runtime_files': {'runtime.c': sha(b'// authored compiler runtime')},
        'compiler_runtime_terms': [{'url': 'https://supplier.invalid/terms', 'sha256': sha(terms), 'archive': 'terms.txt'}]}
    root = tmp_path / 'runtime'
    internal = root / '_internal'
    prefix = internal / 'toolchains/cyberpunk'

    def write(name, data):
        path = prefix / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    for name, data in wkit_files.items():
        write('reader/' + name, data)
    for name, data in net_files.items():
        write('dotnet/' + name, data)
    write('reader/fixture.dll', package_files['lib/fixture.dll'])
    owned = {'reader/kraken.dll': b'MZ authored compiled decoder', 'reader/ToolkitCyberpunkReader.dll': b'MZ authored compiled wrapper',
        'sources/ToolkitCyberpunkReader.cs': b'// authored wrapper', 'sources/COPYING': b'Authored full GPL terms',
        'sources/kraken-source.tar.gz': archives['kraken'].read_bytes()}
    for name, data in owned.items():
        write(name, data)
    adapter.builder.corresponding_source(archives['source'], prefix / 'sources/wolvenkit-source.zip')
    source_root = tmp_path / 'source'
    for name in adapter.RECIPES:
        path = source_root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(json.dumps(pins).encode() if name == adapter.POLICY else (ROOT / name).read_bytes())
    native = tmp_path / 'compiler'
    native.mkdir()
    (native / 'runtime.c').write_bytes(b'// authored compiler runtime')
    for module in (adapter.toolchain, collector):
        monkeypatch.setattr(module, 'SUPPLIERS', suppliers)
        monkeypatch.setattr(module, 'OWNED_FILES', {name: sha(data) for name, data in owned.items()})
    monkeypatch.setattr(adapter.builder, 'KRAKEN_SOURCE', kraken)
    monkeypatch.setattr(collector, 'KRAKEN_SOURCE', kraken)
    monkeypatch.setattr(collector, 'PINS', source_root / adapter.POLICY)
    monkeypatch.setattr(collector, 'ROOT', source_root)
    monkeypatch.setattr(collector, 'acquire', lambda path, pin: pinned[pin['sha256']])
    collector.collect(internal, tmp_path / 'cache', archives, native_toolchain=native)
    files = [{'path': p.relative_to(root).as_posix(), 'sha256': sha(p.read_bytes()), 'bytes': p.stat().st_size}
             for p in root.rglob('*') if p.is_file()]
    review = reviewer.Review(root, {'files': files}, 'windows-x64')
    review.native_archives(list(archives.values()), set(pinned))
    snapshot = SimpleNamespace(files={name: (source_root / name).read_bytes().replace(b'\r\n', b'\n') for name in adapter.RECIPES})
    return review, snapshot


def test_authored_closed_resources_have_independent_origins_not_self_approval(closure):
    review, snapshot = closure
    adapter.inspect(review, snapshot, reviewer.source_matches)
    assert review.checks['native_inputs']['evidence'][-1]['exact_binary_origins'] == 10
    assert review.checks['complete_notices']['evidence'][-1]['cyberpunk_components_with_full_terms'] == 5
    assert 'not independently rebuilt' in review.checks['corresponding_sources']['evidence'][-1]['basis']


@pytest.mark.parametrize('change', ['notice', 'archive_member', 'source_selection', 'owned_binary', 'extra_binary', 'recipe'])
def test_changed_evidence_cannot_inherit_supplier_acceptance(closure, change):
    review, snapshot = closure
    if change == 'notice':
        review.inventory['_internal/notices/cyberpunk/nuget/fixture/1/LICENSE']['sha256'] = sha(b'changed')
    elif change == 'archive_member':
        review.archive_members.clear()
    elif change == 'source_selection':
        path = review.root / '_internal/toolchains/cyberpunk/sources/wolvenkit-source.zip'
        with zipfile.ZipFile(path, 'a') as output:
            output.writestr('extra.cs', '// substituted source')
    elif change == 'owned_binary':
        review.inventory['_internal/toolchains/cyberpunk/reader/kraken.dll']['sha256'] = sha(b'changed')
    elif change == 'extra_binary':
        review.inventory['_internal/toolchains/cyberpunk/reader/unreviewed.dll'] = {'sha256': sha(b'MZ unreviewed')}
    else:
        review.inventory['_internal/sources/cyberpunk/backend/cyberpunk_build.py']['sha256'] = sha(b'changed')
    with pytest.raises(ValueError):
        adapter.inspect(review, snapshot, reviewer.source_matches)
