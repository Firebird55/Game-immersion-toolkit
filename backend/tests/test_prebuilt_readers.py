"""Synthetic manifest/dispatch tests; Windows runs the actual .NET apphost.

Existing SDK/source-reader fixtures cannot detect a frozen reader falling back
to a compiler, missing adjacent runtime files or promoting probe-only evidence.
"""
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import struct

import pytest

from backend import prebuilt_readers as readers
from backend.preparation_errors import PreparationFailure
from backend.runtime_bundle import RuntimeLayout


def digest(data):
    return hashlib.sha256(data).hexdigest()


def x64_image():
    data = bytearray(128)
    data[:2] = b'MZ'
    struct.pack_into('<I', data, 60, 64)
    data[64:68] = b'PE\0\0'
    struct.pack_into('<H', data, 68, 0x8664)
    struct.pack_into('<H', data, 88, 0x20b)
    return bytes(data)



@pytest.fixture(autouse=True)
def windows_helper_host(monkeypatch):
    # Historical receipt mutation fixtures deliberately describe Windows.
    monkeypatch.setattr(readers, 'host_platform', lambda: 'win-x64')


def native_image(platform):
    if platform == 'win-x64':
        return x64_image()
    data = bytearray(128)
    if platform == 'linux-x64':
        data[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<H', data, 18, 62)
    else:
        data[:4] = b'\xcf\xfa\xed\xfe'
        struct.pack_into('<I', data, 4, 0x100000c)
    return bytes(data)


def helper_fixture(tmp_path, kind='probe', platform='win-x64'):
    temporary = tmp_path.resolve()
    app, private = temporary / 'Application 中文', temporary / 'private'
    resource = app / '_internal'
    home = resource / 'helpers' / kind
    home.mkdir(parents=True)
    stem = 'ToolkitReaderProbe' if kind == 'probe' else 'NteReader'
    sources = {name: 'c' * 64 for name in readers._source_names(kind)}
    target = readers.TARGETS[platform]
    native_files = target['native_files']
    executable = stem + target['extension']
    content = {executable: native_image(platform), stem + '.dll': b'authored IL fixture',
        stem + '.runtimeconfig.json': json.dumps({'runtimeOptions': {'includedFrameworks': [{'name': 'Microsoft.NETCore.App', 'version': readers.RUNTIME}]}}).encode(),
        stem + '.deps.json': json.dumps({'runtimeTarget': {'name': '.NETCoreApp,Version=v10.0/' + target['rid']}}).encode(),
        **{name: native_image(platform) for name in native_files},
        'System.Private.CoreLib.dll': b'authored runtime fixture', 'probe-resource.txt': b'authored probe fixture',
        'notices/PROJECT-LICENSE.txt': b'Authored fixture notice', 'notices/sdk-LICENSE.txt': b'Authored SDK fixture notice',
        'notices/sdk-ThirdPartyNotices.txt': b'Authored complete third-party fixture notice'}
    if kind != 'probe':
        del content['probe-resource.txt']
    content['restore-lock.json'] = b'{"version":1,"dependencies":{"net10.0":{}}}'
    for name in target['packages']:
        content['notices/' + name + '/LICENSE.TXT'] = b'Authored pinned package fixture notice'
    receipt = {'schema': 'proxy-dotnet-helper-build-receipt-v1', 'source_commit': 'a' * 40,
        'source_dirty': False,
        'source_inputs': sources, 'sdk_version': readers.SDK, 'runtime_version': readers.RUNTIME,
        'sdk': {'sha512': target['sdk_sha512']}, 'sdk_installed_files': {'dotnet' + target['extension']: 'd' * 64},
        'dotnet_executable_sha256': 'd' * 64, 'restore_lock_sha256': digest(content['restore-lock.json']),
        'runtime_packages': [{'name': name, 'version': readers.RUNTIME, 'sha512_base64': value} for name, value in target['packages'].items()],
        'runtime_package_files': {'runtime/' + name: digest(content[name]) for name in (*native_files, 'System.Private.CoreLib.dll')}}
    content['build-receipt.json'] = json.dumps(receipt).encode()
    files = {}
    for name, data in content.items():
        path = home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        if name == executable:
            path.chmod(0o755)
        files[name] = {'bytes': len(data), 'sha256': digest(data)}
    manifest = {'schema': readers.SCHEMA, 'kind': kind, 'entry': executable, 'platform': platform,
        'sdk_version': readers.SDK, 'runtime_version': readers.RUNTIME, 'source_commit': 'a' * 40, 'source_dirty': False,
        'source_inputs': sources, 'purpose': 'authored-probe-only' if kind == 'probe' else 'owned-bridge-only',
        'files': files, 'build_id': readers._identity(files), 'sdk_archive': receipt['sdk'],
        'runtime_packages': receipt['runtime_packages'], 'restore_lock_sha256': receipt['restore_lock_sha256'],
        'dotnet_executable_sha256': receipt['dotnet_executable_sha256']}
    (home / 'helper-manifest.json').write_text(json.dumps(manifest))
    resources = {'helpers/' + kind + '/' + path.relative_to(home).as_posix(): digest(path.read_bytes()) for path in home.rglob('*') if path.is_file()}
    layout = RuntimeLayout(mode='bundle', application_root=app, resource_root=resource, executable=app / 'Runtime.exe',
        data_root=private / 'data', settings_root=private, cache_root=private / 'cache', tool_root=private / 'tools',
        work_root=private / 'work', state_root=private / 'state', default_export_root=private / 'exports',
        source_commit='a' * 40, resources=resources)
    return layout, home, manifest


def save(layout, home, manifest):
    manifest['build_id'] = readers._identity(manifest['files'])
    (home / 'helper-manifest.json').write_text(json.dumps(manifest))
    prefix = 'helpers/' + manifest['kind'] + '/'
    resources = {name: digest((layout.resource_root / name).read_bytes()) for name in layout.resources}
    resources[prefix + 'helper-manifest.json'] = digest((home / 'helper-manifest.json').read_bytes())
    return replace(layout, resources=resources)


def test_probe_uses_only_outer_verified_app_local_executable_and_fixed_arguments(tmp_path):
    layout, home, _ = helper_fixture(tmp_path)
    helper = readers.prebuilt_reader('probe', layout=layout)
    assert helper.command(['--probe']) == [str(home / 'ToolkitReaderProbe.exe'), '--probe']
    for arguments in ([], ['--probe', 'unrequested'], ['-m', 'arbitrary'], '--probe'):
        with pytest.raises(PreparationFailure):
            helper.command(arguments)


def test_owned_nte_identity_does_not_authorize_game_commands_or_external_libraries(tmp_path):
    layout, home, manifest = helper_fixture(tmp_path, 'nte')
    helper = readers.prebuilt_reader('nte', layout=layout)
    assert helper.runtime_identity_command() == [str(home / 'NteReader.exe'), '--runtime-identity']
    with pytest.raises(PreparationFailure):
        helper.command(['inventory'])
    # Rehashing a receipt cannot turn a blocked dependency into an owned file.
    data = b'authored unreviewed dependency fixture'
    (home / 'UEExtractor.dll').write_bytes(data)
    manifest['files']['UEExtractor.dll'] = {'bytes': len(data), 'sha256': digest(data)}
    layout = save(layout, home, manifest)
    with pytest.raises(PreparationFailure):
        readers.prebuilt_reader('nte', layout=layout)


def test_apphost_environment_omits_sdk_loader_and_account_state():
    result = readers.reader_environment({'SystemRoot': r'C:\Windows', 'WINDIR': r'C:\Windows',
        'TEMP': r'C:\Owned temp', 'PATH': r'C:\SDK;C:\Node', 'DOTNET_ROOT': r'C:\Other runtime',
        'DOTNET_STARTUP_HOOKS': 'untrusted.dll', 'CORECLR_PROFILER': 'untrusted',
        'NODE_OPTIONS': '--require=untrusted', 'LEXIRISE_API_KEY': 'owned-fake-test-value'})
    assert set(result) == {'SYSTEMROOT', 'WINDIR', 'TEMP', 'PATH', 'DOTNET_MULTILEVEL_LOOKUP'}
    assert result['PATH'] == r'C:\Windows\System32;C:\Windows'
    assert result['DOTNET_MULTILEVEL_LOOKUP'] == '0'


@pytest.mark.parametrize('change', ['missing-outer-file', 'changed-file', 'extra-file', 'empty-directory', 'wrong-machine',
    'missing-runtime', 'missing-notice', 'machine-framework', 'wrong-receipt', 'private-source-path', 'wrong-purpose'])
def test_incomplete_or_changed_native_closure_never_falls_back_to_machine_sdk(tmp_path, change):
    layout, home, manifest = helper_fixture(tmp_path)
    if change == 'missing-outer-file':
        resources = dict(layout.resources); del resources['helpers/probe/coreclr.dll']; layout = replace(layout, resources=resources)
    elif change == 'changed-file':
        (home / 'coreclr.dll').write_bytes(b'altered')
    elif change == 'extra-file':
        (home / 'unknown.dll').write_bytes(b'undeclared')
    elif change == 'empty-directory':
        (home / 'unlisted').mkdir()
    else:
        if change in {'missing-runtime', 'missing-notice'}:
            name = 'coreclr.dll' if change == 'missing-runtime' else 'notices/sdk-LICENSE.txt'
            (home / name).unlink(); del manifest['files'][name]
            resources = dict(layout.resources); del resources['helpers/probe/' + name]; layout = replace(layout, resources=resources)
        elif change == 'wrong-machine':
            data = bytearray(x64_image()); struct.pack_into('<H', data, 68, 0x14c)
            (home / 'ToolkitReaderProbe.exe').write_bytes(data)
            manifest['files']['ToolkitReaderProbe.exe'] = {'bytes': len(data), 'sha256': digest(data)}
        elif change in {'machine-framework', 'wrong-receipt'}:
            name = 'ToolkitReaderProbe.runtimeconfig.json' if change == 'machine-framework' else 'build-receipt.json'
            data = json.loads((home / name).read_text())
            if change == 'machine-framework': data['runtimeOptions']['framework'] = {'name': 'Microsoft.NETCore.App', 'version': readers.RUNTIME}
            else: data['sdk_version'] = '10.0.100'
            raw = json.dumps(data).encode(); (home / name).write_bytes(raw)
            manifest['files'][name] = {'bytes': len(raw), 'sha256': digest(raw)}
        elif change == 'private-source-path':
            manifest['source_inputs'] = {'C:/private/Keys.cs': 'f' * 64}
        elif change == 'wrong-purpose':
            manifest['purpose'] = 'approved-game-reader'
        layout = save(layout, home, manifest)
    with pytest.raises(PreparationFailure, match='missing|incompatible|resources'):
        readers.prebuilt_reader('probe', layout=layout)


def test_probe_and_owned_bridge_receipts_cannot_authorize_game_chains(tmp_path, monkeypatch):
    layout, home, manifest = helper_fixture(tmp_path, kind='nte')
    manifest['rights'] = 'approved'
    layout = save(layout, home, manifest)
    helper = readers.prebuilt_reader('nte', layout=layout)
    assert readers.SHA.fullmatch(helper.source_identity)
    with pytest.raises(PreparationFailure, match='external'):
        helper.command(['inventory'])
    monkeypatch.setattr(readers, 'discover_layout', lambda: layout)
    for kind in ('nte', 'endfield'):
        with pytest.raises(PreparationFailure):
            readers.require_game_reader(kind)
    with pytest.raises(PreparationFailure, match='compiled helper kind'):
        readers.prebuilt_reader('endfield', layout=layout)


def test_frozen_external_nte_adapter_fails_before_sdk_download_or_source_compilation(tmp_path, monkeypatch):
    from backend import nte_assets, nte_toolchain, runtime_bundle
    layout, _, _ = helper_fixture(tmp_path)
    monkeypatch.setattr(readers, 'discover_layout', lambda: layout)
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    monkeypatch.setattr(nte_toolchain, 'discover_layout', lambda: layout)
    monkeypatch.setattr(nte_assets, 'dotnet_sdk', lambda: pytest.fail('Frozen NTE cannot inspect a system SDK'))
    for operation in (lambda: nte_assets.ensure_extractor(tmp_path / 'nte'),
                      lambda: nte_assets.run_reader(tmp_path / 'game', tmp_path / 'tool', tmp_path / 'out', 'index')):
        with pytest.raises(PreparationFailure):
            operation()
    assert not (tmp_path / 'nte').exists()


def test_frozen_nte_fingerprint_uses_verified_helper_identity_not_cs_source(tmp_path, monkeypatch):
    from backend import nte_assets, runtime_bundle
    layout, _, _ = helper_fixture(tmp_path, kind='nte')
    monkeypatch.setattr(runtime_bundle, 'discover_layout', lambda: layout)
    original = Path.read_bytes
    def guarded(path):
        if path.suffix in {'.cs', '.csproj'}:
            pytest.fail('Frozen fingerprint must not read a developer source file')
        return original(path)
    monkeypatch.setattr(Path, 'read_bytes', guarded)
    assert readers.SHA.fullmatch(nte_assets.fingerprint(tmp_path / 'absent synthetic game'))


def test_helper_root_link_is_rejected_before_resource_canonicalization(tmp_path):
    layout, home, _ = helper_fixture(tmp_path)
    target = home.with_name('same-owned-bytes')
    home.rename(target)
    try:
        home.symlink_to(target, target_is_directory=True)
    except OSError:
        pytest.skip('Creating a synthetic directory link requires Windows link privileges')
    with pytest.raises(PreparationFailure, match='incompatible') as failure:
        readers.prebuilt_reader('probe', layout=layout)
    assert 'links or reparse' in str(failure.value.__cause__)


@pytest.mark.parametrize('change', ['duplicate-package', 'extra-wrong-version', 'sdk-executable', 'manifest-receipt'])
def test_receipt_identity_is_exact_and_bound_to_manifest(tmp_path, change):
    layout, home, manifest = helper_fixture(tmp_path)
    receipt = json.loads((home / 'build-receipt.json').read_text())
    if change == 'duplicate-package':
        receipt['runtime_packages'].append(receipt['runtime_packages'][0])
    elif change == 'extra-wrong-version':
        receipt['runtime_packages'].append({'name': 'unreviewed', 'version': '9.0.0', 'sha512_base64': 'ignored'})
    elif change == 'sdk-executable':
        receipt['sdk_installed_files']['dotnet.exe'] = 'f' * 64
    else:
        manifest['restore_lock_sha256'] = 'f' * 64
    raw = json.dumps(receipt).encode()
    (home / 'build-receipt.json').write_bytes(raw)
    manifest['files']['build-receipt.json'] = {'bytes': len(raw), 'sha256': digest(raw)}
    layout = save(layout, home, manifest)
    with pytest.raises(PreparationFailure, match='incompatible'):
        readers.prebuilt_reader('probe', layout=layout)


@pytest.mark.parametrize('platform', readers.TARGETS)
def test_each_native_platform_requires_its_own_complete_runtime(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(readers, 'host_platform', lambda: platform)
    layout, home, manifest = helper_fixture(tmp_path, 'nte', platform)
    helper = readers.prebuilt_reader('nte', layout=layout)
    assert helper.runtime_identity_command() == [str(home / manifest['entry']), '--runtime-identity']
    # The same managed contract cannot make a foreign apphost executable here.
    monkeypatch.setattr(readers, 'host_platform', lambda: next(p for p in readers.TARGETS if p != platform))
    with pytest.raises(PreparationFailure):
        readers.prebuilt_reader('nte', layout=layout)


@pytest.mark.parametrize('platform', ['linux-x64', 'darwin-arm64'])
def test_unix_apphost_machine_is_checked_after_outer_inventory_verification(tmp_path, monkeypatch, platform):
    monkeypatch.setattr(readers, 'host_platform', lambda: platform)
    layout, home, manifest = helper_fixture(tmp_path, 'nte', platform)
    raw = native_image('darwin-arm64' if platform == 'linux-x64' else 'linux-x64')
    (home / manifest['entry']).write_bytes(raw)
    manifest['files'][manifest['entry']] = {'bytes': len(raw), 'sha256': digest(raw)}
    layout = save(layout, home, manifest)
    with pytest.raises(PreparationFailure):
        readers.prebuilt_reader('nte', layout=layout)


def test_helper_target_pins_match_exact_build_inputs():
    pins = json.loads(Path('packaging/game-readers/inputs.json').read_text())
    for target in readers.TARGETS.values():
        specification = pins['targets'][target['rid']]
        assert target['sdk_sha512'] == specification['sdk']['sha512']
        assert target['packages'] == {p['name']: p['sha512_base64'] for p in specification['packages']}
        assert all(p['version'] == readers.RUNTIME for p in specification['packages'])


@pytest.mark.parametrize('platform', ['linux-x64', 'darwin-arm64'])
def test_unix_helper_environment_excludes_system_runtime_and_loader_injection(platform):
    result = readers.reader_environment({'HOME': '/synthetic/user', 'TMPDIR': '/synthetic/tmp',
        'PATH': '/developer/sdk', 'DOTNET_ROOT': '/developer/runtime', 'DOTNET_STARTUP_HOOKS': 'injected',
        'LD_PRELOAD': 'injected.so', 'DYLD_LIBRARY_PATH': '/injected', 'ACCOUNT_TOKEN': 'secret'}, platform=platform)
    assert result == {'HOME': '/synthetic/user', 'TMPDIR': '/synthetic/tmp',
                      'PATH': '/usr/bin:/bin', 'DOTNET_MULTILEVEL_LOOKUP': '0'}
