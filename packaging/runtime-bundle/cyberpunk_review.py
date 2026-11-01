"""Inspect the selected Cyberpunk reader without downloading or executing it."""
from __future__ import annotations

import hashlib
import json
from pathlib import PurePosixPath, Path
import tempfile
import zipfile

from backend import cyberpunk_toolchain as toolchain
from backend import cyberpunk_build as builder
from backend.runtime_bundle import relative_resource
from backend.runtime_payload import digest

PREFIX = '_internal/'
COMPONENTS = 'notices/cyberpunk/components.json'
POLICY = 'packaging/cyberpunk/redistribution.json'
RECIPES = ('backend/cyberpunk_toolchain.py', 'backend/cyberpunk_build.py',
    'scripts/build-cyberpunk-toolchain.py', 'scripts/cyberpunk_redistribution.py',
    POLICY, 'packaging/codecs/audio-runtime.json', 'LICENSE')


def inspect(review, snapshot, source_matches):
    try:
        return inspect_selection(review, snapshot, source_matches)
    except (OSError, ValueError, KeyError, RuntimeError, zipfile.BadZipFile):
        for check in ('complete_notices', 'corresponding_sources'):
            review.block(check, 'cyberpunk-review-incomplete',
                'Cyberpunk supplier, notice and corresponding-source evidence could not be completely verified.')
        raise


def inspect_selection(review, snapshot, source_matches):
    """Require actual supplier members, retained terms, and known source recipes.

    Compiled owned outputs have separately pinned identities. This inspects the
    inputs for the recorded source build; it does not claim to rebuild them.
    """
    if not any(name.startswith(PREFIX + toolchain.PREFIX) for name in review.inventory):
        return
    if review.target != 'windows-x64':
        raise ValueError('The inspected Cyberpunk dependency selection is Windows x64 only.')
    for name, module in (('backend/cyberpunk_toolchain.py', toolchain), ('backend/cyberpunk_build.py', builder)):
        if name not in snapshot.files or not source_matches(snapshot.files[name], digest(Path(module.__file__)), name):
            raise ValueError('Cyberpunk review adapter differs from the candidate source: ' + name)
    pins = json.loads(snapshot.files[POLICY])
    if pins.get('schema') != 'toolkit-cyberpunk-redistribution-pins-v1':
        raise ValueError('Unknown Cyberpunk dependency pin schema.')
    evidence_path = review.root / PREFIX / COMPONENTS
    if evidence_path.stat().st_size > 8 * 1024**2:
        raise ValueError('Cyberpunk component evidence exceeds its size limit.')
    evidence = json.loads(evidence_path.read_text(encoding='utf-8'))
    if evidence.get('schema') != 'toolkit-cyberpunk-components-v1' or evidence.get('platform') != 'win-x64':
        raise ValueError('Unknown Cyberpunk component evidence schema or target.')
    components = evidence.get('components', [])
    by_name = {item['name']: item for item in components}
    expected_names = {p['name'] + '/' + p['version'] for p in pins['packages']} | {
        'WolvenKit/' + toolchain.VERSION, '.NET/' + toolchain.RUNTIME + '/win-x64',
        'Kraken/' + builder.KRAKEN_REVISION, 'ToolkitCyberpunkReader'}
    if len(by_name) != len(components) or set(by_name) != expected_names:
        raise ValueError('Cyberpunk component inventory differs from the selected source policy.')
    covered = set()

    def delivered(name, expected):
        name = PREFIX + relative_resource(name)
        entry = review.inventory.get(name, {})
        if not isinstance(expected, str) or len(expected) != 64 or entry.get('link') or entry.get('sha256') != expected:
            raise ValueError('Cyberpunk retained evidence differs: ' + name)
        return name

    def reference(item):
        return delivered(item['path'], item['sha256'])

    def archive_member(archive_sha, member, expected):
        member = relative_resource(member)
        if not isinstance(expected, str) or len(expected) != 64 or review.archive_members.get(archive_sha, {}).get(member) != expected:
            raise ValueError('Cyberpunk supplier archive/member is absent or differs: ' + member)

    def binaries(component, expected):
        actual = {item['path']: item for item in component['binaries']}
        if len(actual) != len(component['binaries']) or set(actual) != set(expected):
            raise ValueError('Cyberpunk component binary selection differs: ' + component['name'])
        for name, identity in expected.items():
            item = actual[name]
            if name in covered or item['sha256'] != identity['sha256'] or item['origin'] != identity['origin']:
                raise ValueError('Cyberpunk component binary identity differs: ' + name)
            reference(item)
            origin = identity['origin']
            if origin['kind'] == 'archive-member':
                archive_member(origin['archive_sha256'], origin['member'], item['sha256'])
            covered.add(name)
            review.origin(item['sha256'], 'Inspected Cyberpunk component ' + component['name'])

    def required_notices(component, expected):
        actual = {item['path']: item['sha256'] for item in component['notices']}
        if len(actual) != len(component['notices']) or actual != expected:
            raise ValueError('Cyberpunk full notice selection differs: ' + component['name'])
        for name, value in expected.items():
            delivered(name, value)

    for package in pins['packages']:
        component = by_name[package['name'] + '/' + package['version']]
        prefix = 'notices/cyberpunk/nuget/' + component['name'] + '/'
        spec = package['nuspec']
        archive_member(package['sha256'], spec['member'], spec['sha256'])
        if component['metadata'] != {'path': prefix + spec['member'], 'sha256': spec['sha256']} or component['supplier_declarations'] != package['metadata']:
            raise ValueError('Cyberpunk supplier declaration differs from its pinned package.')
        reference(component['metadata'])
        expected = {}
        for member in package['members']:
            expected[member['path']] = {'sha256': member['sha256'], 'origin': {
                'kind': 'archive-member', 'url': package['url'], 'archive_sha256': package['sha256'], 'member': member['member']}}
        binaries(component, expected)
        notices = {}
        for notice in package['notices']:
            archive_member(package['sha256'], notice['member'], notice['sha256'])
            notices[prefix + notice['member']] = notice['sha256']
        terms = ([package['full_terms']] if package.get('full_terms') else []) + package.get('extra_terms', [])
        for index, term in enumerate(terms, 1):
            notices[prefix + f'UPSTREAM-TERMS-{index}.txt'] = term['sha256']
        if not notices:
            raise ValueError('Cyberpunk supplier lacks full retained terms: ' + component['name'])
        required_notices(component, notices)

    recipe_refs = {}
    for name in RECIPES:
        retained = 'sources/cyberpunk/' + name
        item = review.inventory.get(PREFIX + retained, {})
        if name not in snapshot.files or not source_matches(snapshot.files[name], item.get('sha256'), name):
            raise ValueError('Cyberpunk rebuild recipe differs from the candidate source: ' + name)
        recipe_refs[name] = {'path': retained, 'sha256': item['sha256']}
    if evidence['pins'] != recipe_refs[POLICY]:
        raise ValueError('Cyberpunk evidence refers to different dependency policy.')
    for name in ('WolvenKit/' + toolchain.VERSION, 'Kraken/' + builder.KRAKEN_REVISION, 'ToolkitCyberpunkReader'):
        recipes = by_name[name]['build_recipes']
        if len(recipes) != len(recipe_refs) or {r['path']: r['sha256'] for r in recipes} != {r['path']: r['sha256'] for r in recipe_refs.values()}:
            raise ValueError('Cyberpunk source build omits its exact rebuild recipes.')

    source_pin = toolchain.SUPPLIERS['source']
    archive = review.native_archive_paths.get(source_pin['sha256'])
    if archive is None:
        raise ValueError('Cyberpunk corresponding-source review needs the pinned upstream source archive.')
    source_name = toolchain.PREFIX + 'sources/wolvenkit-source.zip'
    selected_source = review.root / PREFIX / source_name
    # Only the known, source-bound selector runs. No source archive code or
    # supplier executable is imported or invoked by this review.
    with tempfile.TemporaryDirectory(prefix='toolkit-source-review-') as temporary:
        selected = Path(temporary) / 'selected.zip'
        builder.corresponding_source(archive, selected)
        if digest(selected) != digest(selected_source):
            raise ValueError('Cyberpunk selected corresponding source differs from the exact upstream selection.')
    wkit = by_name['WolvenKit/' + toolchain.VERSION]
    if wkit['sources'] != [{'path': source_name, 'sha256': digest(selected_source), 'kind': 'selected-upstream-source',
            'origin': source_pin, 'selection_recipe': recipe_refs['backend/cyberpunk_build.py']}]:
        raise ValueError('Cyberpunk source selection identity differs.')
    with zipfile.ZipFile(selected_source) as source:
        license_hash = hashlib.sha256(source.read('LICENSE')).hexdigest()
        declarations = {item['path']: item['sha256'] for item in wkit['project_declarations']}
        expected_declarations = {'notices/cyberpunk/projects/' + name: hashlib.sha256(source.read(name)).hexdigest()
                                 for name in source.namelist() if name.endswith('.csproj')}
        if declarations != expected_declarations:
            raise ValueError('Cyberpunk upstream project declarations differ.')
        for name, value in declarations.items():
            delivered(name, value)
    required_notices(wkit, {'notices/cyberpunk/WolvenKit-COPYING': license_hash})
    wkit_pin = toolchain.SUPPLIERS['wolvenkit']
    expected = {}
    for name in ('WolvenKit.CLI.dll', 'WolvenKit.Common.dll', 'WolvenKit.Core.dll', 'WolvenKit.Modkit.dll', 'WolvenKit.RED4.dll'):
        value = review.archive_members.get(wkit_pin['sha256'], {}).get(name)
        expected[toolchain.PREFIX + 'reader/' + name] = {'sha256': value, 'origin': {
            'kind': 'archive-member', 'url': wkit_pin['url'], 'archive_sha256': wkit_pin['sha256'], 'member': name}}
    binaries(wkit, expected)

    dotnet_pin = toolchain.SUPPLIERS['dotnet']
    dotnet = by_name['.NET/' + toolchain.RUNTIME + '/win-x64']
    dotnet_members = review.archive_members.get(dotnet_pin['sha256'], {})
    expected = {toolchain.PREFIX + 'dotnet/' + name: {'sha256': value, 'origin': {
        'kind': 'archive-member', 'url': dotnet_pin['url'], 'archive_sha256': dotnet_pin['sha256'], 'member': name}}
        for name, value in dotnet_members.items() if PurePosixPath(name).suffix.lower() in {'.dll', '.exe'}}
    if not expected:
        raise ValueError('Cyberpunk .NET supplier archive is absent.')
    binaries(dotnet, expected)
    required_notices(dotnet, {toolchain.PREFIX + 'dotnet/' + name: dotnet_members[name]
                             for name in ('LICENSE.txt', 'ThirdPartyNotices.txt')})

    for name, value in toolchain.OWNED_FILES.items():
        delivered(toolchain.PREFIX + name, value)
    copying = toolchain.PREFIX + 'sources/COPYING'
    for component_name, binary_name, recipe in (
            ('Kraken/' + builder.KRAKEN_REVISION, 'reader/kraken.dll', 'backend/cyberpunk_build.py'),
            ('ToolkitCyberpunkReader', 'reader/ToolkitCyberpunkReader.dll', 'backend/cyberpunk_toolchain.py')):
        expected_hash = toolchain.OWNED_FILES[binary_name]
        binaries(by_name[component_name], {toolchain.PREFIX + binary_name: {'sha256': expected_hash, 'origin': {
            'kind': 'reproducible-source-build', 'recipe': recipe_refs[recipe], 'expected_sha256': expected_hash}}})
    kraken = by_name['Kraken/' + builder.KRAKEN_REVISION]
    source_name = toolchain.PREFIX + 'sources/kraken-source.tar.gz'
    if kraken['sources'] != [{'path': source_name, 'sha256': builder.KRAKEN_SOURCE['sha256'],
            'origin': builder.KRAKEN_SOURCE, 'kind': 'complete-upstream-source', 'patch_recipe': recipe_refs['backend/cyberpunk_build.py']}]:
        raise ValueError('Cyberpunk Kraken source/patch identity differs.')
    notices = {copying: toolchain.OWNED_FILES['sources/COPYING']}
    for index, term in enumerate(pins['compiler_runtime_terms'], 1):
        notices[f'notices/cyberpunk/compiler-runtime/GCC-TERMS-{index}.txt'] = term['sha256']
    for name, value in pins['compiler_runtime_files'].items():
        notices['notices/cyberpunk/compiler-runtime/' + name] = value
    required_notices(kraken, notices)
    wrapper = by_name['ToolkitCyberpunkReader']
    if wrapper['sources'] != [{'path': toolchain.PREFIX + 'sources/ToolkitCyberpunkReader.cs',
                              'sha256': toolchain.OWNED_FILES['sources/ToolkitCyberpunkReader.cs']}]:
        raise ValueError('Cyberpunk owned wrapper source differs.')
    required_notices(wrapper, {copying: toolchain.OWNED_FILES['sources/COPYING']})
    actual = {name.removeprefix(PREFIX) for name in review.inventory
        if name.startswith(PREFIX + toolchain.PREFIX) and PurePosixPath(name).suffix.lower() in {'.dll', '.exe', '.so', '.dylib'}}
    if actual != covered or evidence.get('binary_count') != len(covered):
        raise ValueError('Cyberpunk executable inventory has missing or unreviewed components.')
    review.evidence('native_inputs', cyberpunk_components=len(components), exact_binary_origins=len(covered))
    review.evidence('complete_notices', cyberpunk_components_with_full_terms=len(components))
    review.evidence('corresponding_sources', cyberpunk_source_archive_sha256=source_pin['sha256'],
        selected_source_sha256=digest(selected_source), kraken_source_sha256=builder.KRAKEN_SOURCE['sha256'],
        basis='Exact supplier members and retained source selections/patch recipes; owned compiled hashes are pinned, not independently rebuilt by this review.')
