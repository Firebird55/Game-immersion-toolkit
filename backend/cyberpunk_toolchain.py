"""Closed WolvenKit/.NET runtime, shared by source preparation and frozen apps.

The supplier currently publishes a win-x64 dependency closure. Resolving it never
uses an SDK, global .NET, executable PATH lookup or a mutable verification marker.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import http.client
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import zipfile

from .node_tools import host_platform
from .owned_process import OwnedProcess
from .prebuilt_readers import _identity, _no_links, _unique_json
from .preparation_errors import PreparationFailure
from .runtime_bundle import discover_layout, relative_resource, RuntimeBundleError

VERSION = '9.0.1'
RUNTIME = '10.0.14'
SDK = '10.0.403'
TARGET = 'win-x64'
PREFIX = 'toolchains/cyberpunk/'
SCHEMA = 'toolkit-cyberpunk-runtime-v1'
SLOT = f'wolvenkit-{VERSION}-net{RUNTIME}-{TARGET}'
SUPPLIERS = {
    'wolvenkit': {'url': f'https://github.com/WolvenKit/WolvenKit/releases/download/{VERSION}/WolvenKit.Console-{VERSION}.zip',
        'sha256': '364427384c0f4ebb6b157fa9abd01595258af1b7993c7b3a7edd2920f2016e92', 'prefix': 'reader/'},
    'dotnet': {'url': f'https://builds.dotnet.microsoft.com/dotnet/Runtime/{RUNTIME}/dotnet-runtime-{RUNTIME}-win-x64.zip',
        'sha256': 'd861ab80f232adf3bdce83293bc1fa92868400330c477bf854d8558eb91c7ca6',
        'sha512': 'a176095f1db69b42c81acc60940744078d6bf2d2ac643e418342aa9c81889f4bd13e42f4621b131f9e77e4bc781ad46e375956219df9a4f979031d2a5a8d93cd', 'prefix': 'dotnet/'},
    'source': {'url': f'https://codeload.github.com/WolvenKit/WolvenKit/tar.gz/refs/tags/{VERSION}',
        'sha256': 'c1cd3d8bf7355a1c9e8332c029aaafc3bb7eb3753eac16555fb17ecc7e904db2'},
}
# Canonical complete file inventory derived from the pinned supplier archives.
# A rewritten local manifest cannot authorize substituted executable bytes.
INVENTORY_SHA256 = '22a1beb26fe81894e88b8cb9b12d0b0c2328aabd541f4733991af00cde4ed5b4'
OWNED_FILES = {
    'reader/ToolkitCyberpunkReader.dll': 'fc1b0907e03d43da23d867a17aa2e1108a387d26618079ca35eb4ff1a5d7632a',
    'sources/ToolkitCyberpunkReader.cs': '002a19e8c1e36a630fb4e6d11283d43532ebc96338f59bc8457d69966d2a8e8a',
    'sources/TOOLKIT-LICENSE': '1d2f36f13b16b401e4bbf81e955ea185d50c6b5de281d89915e240138b7bb396',
}


def failure():
    return PreparationFailure('bundle_toolchain_unavailable',
        'The Cyberpunk archive reader or its bundled .NET runtime is missing or incompatible. '
        'Repair the application or prepare game tools again. This reader currently requires Windows x64; '
        'no system .NET, SDK or executable fallback was started.')


def _sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def verify_archive(path: Path, supplier: dict):
    _no_links(path)
    if path.stat().st_size > 160 * 1024 * 1024 or _sha(path) != supplier['sha256']:
        raise ValueError('Cyberpunk supplier archive checksum differs')
    if 'sha512' in supplier:
        with path.open('rb') as stream:
            if hashlib.file_digest(stream, 'sha512').hexdigest() != supplier['sha512']:
                raise ValueError('Official .NET archive checksum differs')


def acquire(path: Path, supplier: dict):
    """Bounded verified download; partial bytes never become a cache entry."""
    _no_links(path)
    if path.exists():
        verify_archive(path, supplier)
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(3):
        partial = path.with_name(path.name + '.partial-' + uuid.uuid4().hex)
        try:
            with urllib.request.urlopen(supplier['url'], timeout=90) as response, partial.open('xb') as out:
                size = 0
                while chunk := response.read(1024 * 1024):
                    size += len(chunk)
                    if size > 160 * 1024 * 1024:
                        raise ValueError('Cyberpunk supplier archive exceeded its size limit')
                    out.write(chunk)
            verify_archive(partial, supplier)
            os.replace(partial, path)
            return path
        except (urllib.error.URLError, TimeoutError, ConnectionError, http.client.IncompleteRead) as error:
            if (isinstance(error, urllib.error.HTTPError) and error.code not in {408, 429, 500, 502, 503, 504}) or attempt == 2:
                raise
            time.sleep(attempt + 1)
        finally:
            partial.unlink(missing_ok=True)


def _extract(archive: Path, destination: Path, prefix: str):
    names, total = set(), 0
    with zipfile.ZipFile(archive) as bundle:
        if len(bundle.infolist()) > 2048:
            raise ValueError('Too many supplier archive members')
        for member in bundle.infolist():
            if member.orig_filename != member.filename:
                raise ValueError('Supplier archive member was normalized by the ZIP reader')
            name = member.filename.rstrip('/') if member.is_dir() else member.filename
            relative_resource(name)
            key = name.casefold()
            kind = stat.S_IFMT(member.external_attr >> 16)
            if key in names or kind not in {0, stat.S_IFDIR, stat.S_IFREG} or member.flag_bits & 1:
                raise ValueError('Unsafe or duplicate supplier archive member')
            names.add(key)
            total += member.file_size
            if total > 300 * 1024 * 1024 or member.file_size > 80 * 1024 * 1024:
                raise ValueError('Expanded supplier archive is too large')
            output = destination / prefix / name
            if member.is_dir():
                output.mkdir(parents=True, exist_ok=True)
            else:
                output.parent.mkdir(parents=True, exist_ok=True)
                with bundle.open(member) as incoming, output.open('xb') as target:
                    shutil.copyfileobj(incoming, target, 1024 * 1024)


def compile_entry(destination: Path, *, sdk_root: Path | None = None):
    """Development/build hosts only. Installed apps never execute a compiler.

    Output must reproduce the checked-in hash, independently of any developer
    SDK selection. Compiler inputs are fixed; no NuGet restore or project hooks.
    """
    sdk_root = sdk_root or (Path(os.environ['PROXY_TRANSCRIPT_DOTNET_SDK']) if os.environ.get('PROXY_TRANSCRIPT_DOTNET_SDK') else None)
    if sdk_root is None:
        dotnet = shutil.which('dotnet')
        sdk_root = Path(dotnet).parent if dotnet else None
    if sdk_root is None:
        raise PreparationFailure('source_sdk_missing', f'Source development needs .NET SDK {SDK} to prepare its owned archive reader. The desktop installer includes the complete runtime.')
    sdk_root = sdk_root.resolve()
    compiler = sdk_root / f'sdk/{SDK}/Roslyn/bincore/csc.dll'
    refs = sorted((sdk_root / f'packs/Microsoft.NETCore.App.Ref/{RUNTIME}/ref/net10.0').glob('*.dll'))
    if not compiler.is_file() or not refs:
        raise PreparationFailure('source_sdk_missing', f'Source development needs .NET SDK {SDK}. Use the desktop installer for a prepared runtime.')
    project = Path(__file__).resolve().parents[1]
    source = (project / 'scripts/game-readers/CyberpunkReader.cs').read_bytes().replace(b'\r\n', b'\n')
    license_data = (project / 'LICENSE').read_bytes().replace(b'\r\n', b'\n')
    for name, data in [('sources/ToolkitCyberpunkReader.cs', source), ('sources/TOOLKIT-LICENSE', license_data)]:
        if hashlib.sha256(data).hexdigest() != OWNED_FILES[name]:
            raise ValueError('Owned archive reader input differs from its pin')
        (destination / name).write_bytes(data)
    refs += [destination / 'reader' / name for name in ('System.CommandLine.dll', 'System.CommandLine.Hosting.dll', 'Microsoft.Extensions.Hosting.Abstractions.dll')]
    with tempfile.TemporaryDirectory(prefix='cyberpunk-build-', dir=destination.parent) as temporary:
        work = Path(temporary).resolve()
        src = work / 'CyberpunkReader.cs'
        src.write_bytes(source)
        output = work / 'ToolkitCyberpunkReader.dll'
        args = ['-nologo', '-target:exe', '-deterministic', '-optimize+', '-debug-', '-nullable:enable',
                '-pathmap:' + str(work) + '=/_src', '-out:' + str(output),
                *('-r:' + str(path.resolve()) for path in refs), str(src)]
        response = work / 'compile.rsp'
        response.write_text('\n'.join('"' + value + '"' for value in args), encoding='utf-8')
        env = {'PATH': '', **{key: value for key, value in os.environ.items() if key.lower() in {'systemroot', 'windir', 'temp', 'tmp'}}}
        env.update(DOTNET_ROOT=str(sdk_root), DOTNET_MULTILEVEL_LOOKUP='0', DOTNET_CLI_TELEMETRY_OPTOUT='1')
        child = OwnedProcess([str(sdk_root / 'dotnet.exe'), 'exec', str(compiler), '@' + str(response)], cwd=work, env=env)
        try:
            stdout, stderr = child.process.communicate(timeout=120)
            if child.process.returncode or not output.is_file():
                raise RuntimeError('The pinned development compiler could not build the owned archive reader')
            if _sha(output) != OWNED_FILES['reader/ToolkitCyberpunkReader.dll']:
                raise ValueError('Owned archive reader build did not reproduce its pinned executable hash')
            shutil.copyfile(output, destination / 'reader/ToolkitCyberpunkReader.dll')
        finally:
            child.stop()
            child.close_streams()


def materialize(destination: Path, archives: dict[str, Path], *, sdk_root: Path | None = None):
    """Build an unpublished directory from verified bytes, then seal its inventory."""
    if destination.exists():
        raise ValueError('A fresh runtime destination is required')
    _no_links(destination)
    for name, supplier in SUPPLIERS.items():
        verify_archive(archives[name], supplier)
    destination.mkdir(parents=True)
    for name in ('wolvenkit', 'dotnet'):
        _extract(archives[name], destination, SUPPLIERS[name]['prefix'])
    sources = destination / 'sources'
    sources.mkdir()
    shutil.copyfile(archives['source'], sources / 'wolvenkit-source.tar.gz')
    files = {p.relative_to(destination).as_posix(): _sha(p) for p in destination.rglob('*') if p.is_file()}
    if _identity(files) != INVENTORY_SHA256:
        raise ValueError('Supplier runtime inventory differs from the reviewed pinned closure')
    compile_entry(destination, sdk_root=sdk_root)
    files.update(OWNED_FILES)
    manifest = {'schema': SCHEMA, 'platform': TARGET, 'version': VERSION, 'runtime': RUNTIME,
                'files': files, 'inventory_sha256': INVENTORY_SHA256}
    (destination / 'runtime.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n', encoding='utf-8')
    return manifest


@dataclass(frozen=True)
class CyberpunkToolchain:
    root: Path

    @property
    def executable(self):
        return self.root / 'reader/WolvenKit.CLI.dll'

    def command(self, arguments, *, work: Path, layout):
        arguments = tuple(map(str, arguments))
        if arguments in {('--help',), ('--version',)}:
            pass
        elif len(arguments) == 8 and arguments[0] == 'unbundle' and arguments[2] == '-o' and arguments[4] == '-r' and arguments[6:] == ('-v', 'quiet'):
            source, output = Path(arguments[1]).resolve(), Path(arguments[3]).resolve()
            if not source.is_file() or source.suffix.lower() != '.archive' or not arguments[5] or len(arguments[5]) > 4096:
                raise ValueError('Invalid archive reader input')
            _no_links(source)
            self._output(output, layout)
            if output == source.parent or source.is_relative_to(output) or output.is_relative_to(source.parent):
                raise ValueError('Archive output must stay separate from the game archive directory')
            arguments = ('unbundle', str(source), '-o', str(output), '-r', arguments[5], '-v', 'quiet')
        elif len(arguments) == 5 and arguments[:2] == ('cr2w', '-s') and arguments[3:] == ('-v', 'quiet'):
            output = Path(arguments[2]).resolve()
            self._output(output, layout)
            if not output.is_dir():
                raise ValueError('Extracted resource directory is unavailable')
            arguments = ('cr2w', '-s', str(output), '-v', 'quiet')
        else:
            raise ValueError('Unsupported archive reader operation')
        runtime = self.root / 'dotnet'
        env = {'PATH': '', **{key: value for key, value in os.environ.items()
            if key.lower() in {'systemroot', 'windir', 'temp', 'tmp', 'lang', 'lc_all'}}}
        env.update(DOTNET_ROOT=str(runtime), DOTNET_ROOT_X64=str(runtime), DOTNET_MULTILEVEL_LOOKUP='0',
            DOTNET_ROLL_FORWARD='Disable', DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
            DOTNET_CLI_HOME=str(work), USERPROFILE=str(work), APPDATA=str(work), LOCALAPPDATA=str(work))
        return [str(runtime / 'dotnet.exe'), 'exec', '--fx-version', RUNTIME, '--roll-forward', 'Disable',
                '--depsfile', str(self.root / 'reader/WolvenKit.CLI.deps.json'),
                '--runtimeconfig', str(self.root / 'reader/WolvenKit.CLI.runtimeconfig.json'),
                str(self.root / 'reader/ToolkitCyberpunkReader.dll'), *arguments], env

    def _output(self, output, layout):
        _no_links(output)
        if output == self.root or output.is_relative_to(self.root) or self.root.is_relative_to(output):
            raise ValueError('Reader outputs cannot overlap the runtime')
        if layout.mode == 'bundle' and not any(output != root and output.is_relative_to(root)
                for root in (layout.data_root, layout.work_root, layout.cache_root)):
            raise ValueError('Reader outputs must stay in private application storage')


def _verify(root: Path, *, layout=None):
    _no_links(root)
    manifest = root / 'runtime.json'
    _no_links(manifest)
    if layout:
        manifest = layout.resource(PREFIX + 'runtime.json')
    if manifest.stat().st_size > 128 * 1024:
        raise ValueError('Reader manifest is too large')
    value = json.loads(manifest.read_text(encoding='utf-8'), object_pairs_hook=_unique_json)
    files = value.get('files')
    if (value.get('schema') != SCHEMA or value.get('platform') != TARGET or host_platform() != TARGET
            or value.get('version') != VERSION or value.get('runtime') != RUNTIME
            or not isinstance(files, dict)
            or any(files.get(name) != digest for name, digest in OWNED_FILES.items())
            or _identity({name: digest for name, digest in files.items() if name not in OWNED_FILES}) != INVENTORY_SHA256
            or value.get('inventory_sha256') != INVENTORY_SHA256):
        raise ValueError('Reader runtime identity differs')
    expected = {*files, 'runtime.json'}
    if layout and {name.removeprefix(PREFIX) for name in layout.resources if name.startswith(PREFIX)} != expected:
        raise ValueError('Reader resources are not closed by the application inventory')
    directories = {parent.as_posix() for name in expected for parent in Path(name).parents if parent != Path('.')}
    actual = set()
    for path in root.rglob('*'):
        _no_links(path)
        name = path.relative_to(root).as_posix()
        if path.is_file():
            actual.add(name)
        elif not path.is_dir() or name not in directories:
            raise ValueError('Uninventoried reader runtime directory')
    if actual != expected:
        raise ValueError('Reader runtime contains missing or extra files')
    for name, digest in files.items():
        relative_resource(name)
        path = layout.resource(PREFIX + name) if layout else root / name
        if _sha(path) != digest:
            raise ValueError('Reader runtime bytes differ')
    return CyberpunkToolchain(root)


def resolve(directory: Path | None = None, *, layout=None):
    layout = layout or discover_layout()
    try:
        if host_platform() != TARGET:
            raise ValueError('No verified supplier closure for this platform')
        root = layout.resource_root / PREFIX if layout.mode == 'bundle' else Path(directory) / SLOT
        return _verify(root, layout=layout if layout.mode == 'bundle' else None)
    except (OSError, ValueError, TypeError, KeyError, RuntimeBundleError) as error:
        raise failure() from error


def ensure(directory: Path, *, layout=None):
    layout = layout or discover_layout()
    if layout.mode == 'bundle':
        return resolve(layout=layout)
    if host_platform() != TARGET:
        raise failure()
    directory = Path(directory).absolute()
    _no_links(directory)
    directory = directory.resolve()
    slot = directory / SLOT
    if slot.exists():
        return resolve(directory, layout=layout)
    directory.mkdir(parents=True, exist_ok=True)
    archives = {name: acquire(directory / 'archives' / (name + '.archive'), supplier)
                for name, supplier in SUPPLIERS.items()}
    stage = directory / ('.runtime-' + uuid.uuid4().hex)
    try:
        materialize(stage, archives)
        _verify(stage)
        try:
            os.rename(stage, slot)
        except FileExistsError:
            pass  # Another preparer won; independently verify its complete slot.
        return resolve(directory, layout=layout)
    finally:
        if stage.exists():
            shutil.rmtree(stage)


def run(executable: Path, *arguments):
    layout = discover_layout()
    if layout.mode == 'bundle':
        chain = resolve(layout=layout)
    else:
        executable = Path(executable).absolute()
        _no_links(executable)
        executable = executable.resolve()
        # Playback still supplies its legacy cache placeholder. It is never run.
        directory = executable.parent.parent.parent if executable.name == 'WolvenKit.CLI.dll' else executable.parent
        chain = resolve(directory, layout=layout)
        if executable.name not in {'WolvenKit.CLI.dll', 'WolvenKit.CLI.exe'}:
            raise failure()
    layout.work_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cyberpunk-', dir=layout.work_root) as work:
        command, env = chain.command(arguments, work=Path(work), layout=layout)
        child = OwnedProcess(command, cwd=work, env=env)
        try:
            stdout, _stderr = child.process.communicate(timeout=600)
            if child.process.returncode or b'[ 0: Error' in stdout:
                raise RuntimeError('Cyberpunk extraction failed; check the selected game archives and repair the reader runtime.')
            return stdout
        finally:
            child.stop()
            child.close_streams()
