"""Retain exact Cyberpunk component notices and independently inspectable origins.

Package declarations and supplied terms are evidence, not an approval flag.
The release input reviewer checks these against the committed pins and archives.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.cyberpunk_toolchain import PREFIX, SUPPLIERS, OWNED_FILES, acquire, _sha
from backend.cyberpunk_build import KRAKEN_SOURCE, KRAKEN_REVISION
from backend.runtime_bundle import relative_resource

PINS = ROOT / 'packaging/cyberpunk/redistribution.json'
BINARY_SUFFIXES = frozenset({'.dll', '.exe', '.so', '.dylib'})
RECIPES = ('backend/cyberpunk_toolchain.py', 'backend/cyberpunk_build.py',
           'scripts/build-cyberpunk-toolchain.py', 'scripts/cyberpunk_redistribution.py',
           'packaging/cyberpunk/redistribution.json', 'packaging/codecs/audio-runtime.json')


def checked_member(archive: zipfile.ZipFile, name: str, expected: str):
    relative_resource(name)
    found = [item for item in archive.infolist() if item.filename == name]
    if len(found) != 1 or found[0].is_dir() or found[0].file_size > 80 * 1024 * 1024:
        raise ValueError('Missing, duplicate or oversized supplier evidence member')
    data = archive.read(found[0])
    if hashlib.sha256(data).hexdigest() != expected:
        raise ValueError('Supplier component member differs from the committed pin')
    return data


def retain(root: Path, name: str, data: bytes):
    name = relative_resource(name)
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_bytes() != data:
        raise ValueError('Conflicting retained component evidence')
    path.write_bytes(data)
    return {'path': name, 'sha256': hashlib.sha256(data).hexdigest()}


def reference(root: Path, name: str):
    name = relative_resource(name)
    return {'path': name, 'sha256': _sha(root / name)}


def collect(root: Path, cache: Path, archives: dict[str, Path], *, native_toolchain: Path):
    pins = json.loads(PINS.read_text(encoding='utf-8'))
    if pins['schema'] != 'toolkit-cyberpunk-redistribution-pins-v1':
        raise ValueError('Unknown Cyberpunk component pin schema')
    packages = pins['packages']
    # This is build-time acquisition only; delivered applications have all bytes.
    with ThreadPoolExecutor(max_workers=5) as pool:
        acquired = list(pool.map(lambda p: acquire(cache / 'nuget' / p['archive'], p), packages))
    components, covered = [], set()
    for package, package_path in zip(packages, acquired, strict=True):
        identity = package['name'] + '/' + package['version']
        prefix = 'notices/cyberpunk/nuget/' + identity + '/'
        notices, binaries = [], []
        with zipfile.ZipFile(package_path) as archive:
            spec = package['nuspec']
            metadata = retain(root, prefix + spec['member'], checked_member(archive, spec['member'], spec['sha256']))
            for member in package['members']:
                name = relative_resource(member['path'])
                actual = root / name
                data = checked_member(archive, member['member'], member['sha256'])
                if not actual.is_file() or actual.read_bytes() != data or name in covered:
                    raise ValueError('Selected runtime component differs or has ambiguous ownership')
                covered.add(name)
                binaries.append({'path': name, 'sha256': member['sha256'],
                    'origin': {'kind': 'archive-member', 'url': package['url'],
                               'archive_sha256': package['sha256'], 'member': member['member']}})
            for notice in package['notices']:
                item = retain(root, prefix + notice['member'], checked_member(archive, notice['member'], notice['sha256']))
                item['origin'] = {'archive_sha256': package['sha256'], 'member': notice['member']}
                notices.append(item)
        terms = [*package.get('extra_terms', [])]
        if package.get('full_terms'):
            terms.insert(0, package['full_terms'])
        for index, term in enumerate(terms):
            downloaded = acquire(cache / 'terms' / term['archive'], term)
            item = retain(root, prefix + f'UPSTREAM-TERMS-{index + 1}.txt', downloaded.read_bytes())
            item['origin'] = {'url': term['url'], 'sha256': term['sha256']}
            notices.append(item)
        if not notices:
            raise ValueError('Selected component has no retained full license terms')
        components.append({'name': identity, 'binaries': binaries, 'notices': notices,
            'metadata': metadata, 'supplier_declarations': package['metadata'], 'sources': []})

    source_zip = PREFIX + 'sources/wolvenkit-source.zip'
    with zipfile.ZipFile(root / source_zip) as source:
        wkit_license = retain(root, 'notices/cyberpunk/WolvenKit-COPYING', source.read('LICENSE'))
        project_declarations = []
        for name in source.namelist():
            if name.endswith('.csproj'):
                project_declarations.append(retain(root, 'notices/cyberpunk/projects/' + name, source.read(name)))
    wkit_binaries = []
    with zipfile.ZipFile(archives['wolvenkit']) as supplier:
        for name in ('WolvenKit.CLI.dll', 'WolvenKit.Common.dll', 'WolvenKit.Core.dll',
                     'WolvenKit.Modkit.dll', 'WolvenKit.RED4.dll'):
            path = PREFIX + 'reader/' + name
            data = checked_member(supplier, name, _sha(root / path))
            covered.add(path)
            wkit_binaries.append({'path': path, 'sha256': hashlib.sha256(data).hexdigest(),
                'origin': {'kind': 'archive-member', 'url': SUPPLIERS['wolvenkit']['url'],
                    'archive_sha256': SUPPLIERS['wolvenkit']['sha256'], 'member': name}})

    recipes = [retain(root, 'sources/cyberpunk/' + name, (ROOT / name).read_bytes().replace(b'\r\n', b'\n')) for name in RECIPES]
    recipe_by_name = {item['path'].removeprefix('sources/cyberpunk/'): item for item in recipes}
    components.append({'name': 'WolvenKit/9.0.1', 'binaries': wkit_binaries,
        'notices': [wkit_license], 'project_declarations': project_declarations,
        'supplier_declarations': {'top_level_license': 'GPL-3.0',
            'project_license': 'See retained upstream project files; declarations are preserved without rewriting them.'},
        'sources': [{**reference(root, source_zip), 'kind': 'selected-upstream-source',
            'origin': SUPPLIERS['source'], 'selection_recipe': recipe_by_name['backend/cyberpunk_build.py']}],
        'build_recipes': recipes})

    dotnet_notices = [reference(root, PREFIX + 'dotnet/' + name) for name in ('LICENSE.txt', 'ThirdPartyNotices.txt')]
    dotnet_binaries = []
    with zipfile.ZipFile(archives['dotnet']) as supplier:
        for path in sorted((root / PREFIX / 'dotnet').rglob('*')):
            if path.is_file() and path.suffix.lower() in BINARY_SUFFIXES:
                name = path.relative_to(root / PREFIX / 'dotnet').as_posix()
                digest = _sha(path)
                checked_member(supplier, name, digest)
                relative = path.relative_to(root).as_posix()
                covered.add(relative)
                dotnet_binaries.append({'path': relative, 'sha256': digest,
                    'origin': {'kind': 'archive-member', 'url': SUPPLIERS['dotnet']['url'],
                        'archive_sha256': SUPPLIERS['dotnet']['sha256'], 'member': name}})
    components.append({'name': '.NET/10.0.14/win-x64', 'binaries': dotnet_binaries,
                       'notices': dotnet_notices, 'sources': []})

    runtime_notices = [reference(root, PREFIX + 'sources/COPYING')]
    for index, term in enumerate(pins['compiler_runtime_terms']):
        downloaded = acquire(cache / 'terms' / term['archive'], term)
        item = retain(root, f'notices/cyberpunk/compiler-runtime/GCC-TERMS-{index + 1}.txt', downloaded.read_bytes())
        item['origin'] = {'url': term['url'], 'sha256': term['sha256']}
        runtime_notices.append(item)
    for name, expected in pins['compiler_runtime_files'].items():
        path = native_toolchain / relative_resource(name)
        if _sha(path) != expected:
            raise ValueError('Compiler runtime source/notice differs from pinned w64devkit')
        runtime_notices.append(retain(root, 'notices/cyberpunk/compiler-runtime/' + name, path.read_bytes()))
    native_path = PREFIX + 'reader/kraken.dll'
    covered.add(native_path)
    components.append({'name': 'Kraken/' + KRAKEN_REVISION,
        'binaries': [{**reference(root, native_path), 'origin': {'kind': 'reproducible-source-build',
            'recipe': recipe_by_name['backend/cyberpunk_build.py'], 'expected_sha256': OWNED_FILES['reader/kraken.dll']}}],
        'notices': runtime_notices, 'sources': [{**reference(root, PREFIX + 'sources/kraken-source.tar.gz'),
            'origin': KRAKEN_SOURCE, 'kind': 'complete-upstream-source',
            'patch_recipe': recipe_by_name['backend/cyberpunk_build.py']}],
        'build_recipes': recipes, 'platform_dependencies': ['KERNEL32.dll', 'msvcrt.dll']})
    owned_path = PREFIX + 'reader/ToolkitCyberpunkReader.dll'
    covered.add(owned_path)
    components.append({'name': 'ToolkitCyberpunkReader', 'binaries': [{**reference(root, owned_path),
        'origin': {'kind': 'reproducible-source-build', 'recipe': recipe_by_name['backend/cyberpunk_toolchain.py'],
            'expected_sha256': OWNED_FILES['reader/ToolkitCyberpunkReader.dll']}}],
        'notices': [reference(root, PREFIX + 'sources/COPYING')],
        'license': 'GPL-3.0-or-later', 'sources': [reference(root, PREFIX + 'sources/ToolkitCyberpunkReader.cs')],
        'build_recipes': recipes})
    actual = {path.relative_to(root).as_posix() for path in (root / PREFIX).rglob('*')
              if path.is_file() and path.suffix.lower() in BINARY_SUFFIXES}
    if actual != covered:
        raise ValueError('Cyberpunk executable closure contains unmapped or absent components')
    result = {'schema': 'toolkit-cyberpunk-components-v1', 'platform': 'win-x64',
        'pins': reference(root, 'sources/cyberpunk/packaging/cyberpunk/redistribution.json'),
        'components': components, 'binary_count': len(covered),
        'review_scope': 'exact selected bytes, retained supplier terms and source/build correspondence; approval is separate'}
    retain(root, 'notices/cyberpunk/components.json', (json.dumps(result, sort_keys=True, indent=2) + '\n').encode('utf-8'))
    return result
