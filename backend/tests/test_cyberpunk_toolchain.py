"""Supplier bytes, fixed operations and retained child ownership are independent gates."""
import hashlib
import io
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess
import urllib.error
import zipfile

import pytest

from backend import cyberpunk_toolchain as tools
from backend.preparation_errors import PreparationFailure


def runtime(tmp_path, monkeypatch, *, bundled=False):
    root = tmp_path / 'runtime'
    files = {'reader/WolvenKit.CLI.dll': hashlib.sha256(b'authored assembly').hexdigest(),
             'dotnet/dotnet.exe': hashlib.sha256(b'authored host').hexdigest()}
    for name, data in [('reader/WolvenKit.CLI.dll', b'authored assembly'), ('dotnet/dotnet.exe', b'authored host')]:
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    monkeypatch.setattr(tools, 'INVENTORY_SHA256', tools._identity(files))
    monkeypatch.setattr(tools, 'OWNED_FILES', {})
    monkeypatch.setattr(tools, 'host_platform', lambda: 'win-x64')
    value = {'schema': tools.SCHEMA, 'platform': tools.TARGET, 'version': tools.VERSION, 'runtime': tools.RUNTIME,
             'inventory_sha256': tools.INVENTORY_SHA256, 'files': files}
    (root / 'runtime.json').write_text(json.dumps(value))
    layout = SimpleNamespace(mode='bundle' if bundled else 'source', data_root=tmp_path / 'data',
        cache_root=tmp_path / 'cache', work_root=tmp_path / 'work', resource_root=tmp_path,
        resources={tools.PREFIX + name: digest for name, digest in files.items()})
    layout.resources[tools.PREFIX + 'runtime.json'] = tools._sha(root / 'runtime.json')
    layout.resource = lambda name: root / name.removeprefix(tools.PREFIX)
    return root, layout


@pytest.mark.parametrize('change', ['byte', 'extra-file', 'empty-directory', 'rewritten-manifest', 'duplicate-manifest-key'])
def test_source_inventory_rejects_cache_marker_replacement_and_added_loader_files(tmp_path, monkeypatch, change):
    root, _ = runtime(tmp_path, monkeypatch)
    assert tools._verify(root).executable == root / 'reader/WolvenKit.CLI.dll'
    if change == 'byte':
        (root / 'reader/WolvenKit.CLI.dll').write_bytes(b'changed assembly')
    elif change == 'extra-file':
        (root / 'reader/extra.dll').write_bytes(b'new dependency')
    elif change == 'empty-directory':
        (root / 'unlisted').mkdir()
    else:
        path = root / 'runtime.json'
        if change == 'duplicate-manifest-key':
            path.write_text(path.read_text().replace('"schema":', '"schema":"duplicate","schema":'))
        else:
            value = json.loads(path.read_text())
            (root / 'reader/WolvenKit.CLI.dll').write_bytes(b'changed assembly')
            value['files']['reader/WolvenKit.CLI.dll'] = tools._sha(root / 'reader/WolvenKit.CLI.dll')
            value['inventory_sha256'] = tools._identity(value['files'])
            path.write_text(json.dumps(value))
    with pytest.raises(ValueError):
        tools._verify(root)


def test_bundle_requires_same_closed_outer_inventory(tmp_path, monkeypatch):
    root, layout = runtime(tmp_path, monkeypatch, bundled=True)
    assert tools._verify(root, layout=layout)
    del layout.resources[tools.PREFIX + 'dotnet/dotnet.exe']
    with pytest.raises(ValueError, match='application inventory'):
        tools._verify(root, layout=layout)


def test_unavailable_platform_never_prepares_or_falls_back_to_path(tmp_path, monkeypatch):
    monkeypatch.setattr(tools, 'host_platform', lambda: 'darwin-arm64')
    monkeypatch.setattr(tools, 'acquire', lambda *_: pytest.fail('No unsupported executable acquisition'))
    with pytest.raises(PreparationFailure, match='Windows x64'):
        tools.ensure(tmp_path / 'tools', layout=SimpleNamespace(mode='source'))
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize('names', [['../outside'], ['/absolute'], ['C:/outside'], ['file', 'FILE'], ['reader\\evil'], ['file:stream']])
def test_archive_names_are_portable_and_cannot_escape_or_alias(tmp_path, names):
    archive = tmp_path / 'input.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        for name in names:
            member = zipfile.ZipInfo()
            member.filename = name  # Preserve hostile backslashes on Windows too.
            zipped.writestr(member, b'authored')
    with pytest.raises((ValueError, tools.RuntimeBundleError)):
        tools._extract(archive, tmp_path / 'out', 'reader/')
    assert not (tmp_path / 'outside').exists()


def test_zip_links_are_not_extracted(tmp_path):
    archive = tmp_path / 'link.zip'
    with zipfile.ZipFile(archive, 'w') as zipped:
        member = zipfile.ZipInfo('linked')
        member.external_attr = 0o120777 << 16
        zipped.writestr(member, 'elsewhere')
    with pytest.raises(ValueError):
        tools._extract(archive, tmp_path / 'out', 'reader/')


def test_partial_download_retries_and_bad_hash_never_publishes(tmp_path, monkeypatch):
    expected = b'authored supplier'
    supplier = {'url': 'https://example.invalid/supplier', 'sha256': hashlib.sha256(expected).hexdigest()}
    calls = []
    def download(*_, **__):
        calls.append(True)
        if len(calls) == 1:
            raise urllib.error.URLError('authored timeout')
        return io.BytesIO(expected)
    monkeypatch.setattr(tools.urllib.request, 'urlopen', download)
    monkeypatch.setattr(tools.time, 'sleep', lambda _: None)
    target = tools.acquire(tmp_path / 'verified', supplier)
    assert target.read_bytes() == expected and len(calls) == 2
    monkeypatch.setattr(tools.urllib.request, 'urlopen', lambda *_a, **_k: io.BytesIO(b'bad'))
    with pytest.raises(ValueError, match='checksum'):
        tools.acquire(tmp_path / 'bad', supplier)
    assert list(tmp_path.iterdir()) == [target]


def test_commands_pin_host_and_wrapper_and_strip_loader_variables(tmp_path, monkeypatch):
    root, layout = runtime(tmp_path, monkeypatch, bundled=True)
    source = tmp_path / 'game/input.archive'
    source.parent.mkdir()
    source.write_bytes(b'authored archive')
    output = layout.data_root / 'extracted'
    monkeypatch.setenv('DOTNET_STARTUP_HOOKS', 'untrusted.dll')
    monkeypatch.setenv('DOTNET_ADDITIONAL_DEPS', 'external.json')
    monkeypatch.setenv('CORECLR_PROFILER_PATH', 'external.dll')
    command, env = tools.CyberpunkToolchain(root).command(
        ['unbundle', source, '-o', output, '-r', '.*', '-v', 'quiet'], work=layout.work_root, layout=layout)
    assert command[:6] == [str(root / 'dotnet/dotnet.exe'), 'exec', '--fx-version', tools.RUNTIME, '--roll-forward', 'Disable']
    assert command[10] == str(root / 'reader/ToolkitCyberpunkReader.dll')
    assert env['PATH'] == '' and env['DOTNET_MULTILEVEL_LOOKUP'] == '0'
    assert not {'DOTNET_STARTUP_HOOKS', 'DOTNET_ADDITIONAL_DEPS', 'CORECLR_PROFILER_PATH'} & env.keys()
    for args in [['pack', str(output)], ['settings'], ['cr2w', '-d', str(output), '-v', 'quiet']]:
        with pytest.raises(ValueError, match='Unsupported'):
            tools.CyberpunkToolchain(root).command(args, work=layout.work_root, layout=layout)
    with pytest.raises(ValueError, match='private application'):
        tools.CyberpunkToolchain(root).command(['cr2w', '-s', str(source.parent), '-v', 'quiet'], work=layout.work_root, layout=layout)


def test_run_owns_child_until_cleanup_even_on_timeout(tmp_path, monkeypatch):
    root, layout = runtime(tmp_path, monkeypatch, bundled=True)
    monkeypatch.setattr(tools, 'discover_layout', lambda: layout)
    monkeypatch.setattr(tools, 'resolve', lambda **_: tools.CyberpunkToolchain(root))
    events = []
    class Child:
        def __init__(self, *args, **kwargs):
            assert args[0][10].endswith('ToolkitCyberpunkReader.dll')
            self.process = self
        def communicate(self, timeout):
            raise subprocess.TimeoutExpired('authored child', timeout)
        def stop(self):
            events.append('verified stopped')
        def close_streams(self):
            events.append('streams closed')
    monkeypatch.setattr(tools, 'OwnedProcess', Child)
    with pytest.raises(subprocess.TimeoutExpired):
        tools.run(tmp_path / 'legacy/WolvenKit.CLI.exe', '--help')
    assert events == ['verified stopped', 'streams closed']
    assert not list(layout.work_root.iterdir())


def test_owned_source_pin_and_boundary_are_stable():
    source = Path(__file__).resolve().parents[2] / 'scripts/game-readers/CyberpunkReader.cs'
    data = source.read_bytes().replace(b'\r\n', b'\n')
    assert hashlib.sha256(data).hexdigest() == tools.OWNED_FILES['sources/ToolkitCyberpunkReader.cs']
    assert b'.UseHost(' in data and b'NativeLibrary.SetDllImportResolver' in data
    assert b'GetProperty("UseOodle")!.SetValue(settings, false)' in data
    assert b'.Main(' not in data and b'Oodle.Load(' not in data
