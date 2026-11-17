"""Original metadata acquisition and frozen-software lifecycle for Star Rail.

Client libraries are authenticated files only. Source checkouts may compile the
fixed software; bundled installations exclusively use the verified apphost.
Failed generations never replace a previously complete metadata preparation.
"""
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from . import sophon_assets as sophon
from .game_tools import _atomic_file
from .prebuilt_readers import reader_environment, prebuilt_reader, _no_links
from .runtime_bundle import discover_layout

ROOT = Path(__file__).resolve().parents[1]
NAMES = {'native': 'GameAssembly.dll', 'metadata': 'global-metadata.dat', 'startup': 'startup-metadata.dat'}
CANONICAL = {'native': 'GameAssembly.dll', 'metadata': 'StarRail_Data/il2cpp_data/Metadata/global-metadata.dat',
             'startup': 'StarRail_Data/il2cpp_data/Metadata/startup-metadata.dat'}
OUTPUTS = {'dump.cs': 512 * 1024**2, 'stringliterals.json': 64 * 1024**2}


def _check(value):
    if not value:
        raise ValueError('Invalid original Star Rail metadata preparation.')


def _hash(path, name='sha256'):
    result = hashlib.new(name)
    with path.open('rb') as stream:
        while block := stream.read(8 * 1024**2):
            result.update(block)
    return result.hexdigest()


def _identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def _run(command, directory, *, build=False, timeout=240):
    env = reader_environment()
    if build:
        for name, folder in [('DOTNET_CLI_HOME', 'cli-home'), ('NUGET_PACKAGES', 'nuget-cache'),
                             ('NUGET_HTTP_CACHE_PATH', 'nuget-http'), ('NUGET_PLUGINS_CACHE_PATH', 'nuget-plugins'),
                             ('NUGET_SCRATCH', 'nuget-scratch'), ('TEMP', 'temporary'), ('TMP', 'temporary'),
                             ('TMPDIR', 'temporary'),
                             ('APPDATA', 'app-data'), ('LOCALAPPDATA', 'local-data'),
                             ('USERPROFILE', 'profile'), ('PROGRAMDATA', 'program-data')]:
            path = directory / folder; path.mkdir(exist_ok=True)
            env[name] = str(path)
        # NuGet's installed machine configuration uses these OS program roots.
        # Source builds read the existing SDK there; all writable user roots and
        # the explicit closed feed/config remain private preparation directories.
        for name in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
            if os.environ.get(name):
                env[name] = os.environ[name]
        env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
                   DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='1', DOTNET_GENERATE_ASPNET_CERTIFICATE='false',
                   DOTNET_NOLOGO='1')
    result = subprocess.run(command, cwd=directory, env=env, capture_output=True, timeout=timeout,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        if build:
            # Developer-only diagnostics remain in the private tool cache.
            _atomic_file(directory.parent / 'metadata-helper-build.log', result.stdout + result.stderr)
        raise ValueError('The frozen Star Rail metadata software could not read these original inputs.')


@dataclass(frozen=True)
class Helper:
    command: tuple[str, ...]
    identity: str

    def run(self, operation, *paths, work):
        _check(operation in {'metadata', 'disassemble'} and len(paths) == (2 if operation == 'metadata' else 3)
               and all(Path(path).is_absolute() for path in paths))
        _run([*self.command, operation, *(str(path) for path in paths)], work)


def helper(directory):
    """Resolve a compiler-free apphost, or build fixed software in source mode."""
    layout = discover_layout()
    if layout.mode == 'bundle':
        reader = prebuilt_reader('starrail', layout=layout)
        return Helper((str(reader.executable),), _identity({'source': reader.source_identity, 'build': reader.manifest['build_id']}))
    directory = Path(directory).absolute(); _no_links(directory); directory.mkdir(parents=True, exist_ok=True)
    source_names = ('scripts/game-readers/StarRailMetadata.cs', 'scripts/game-readers/StarRailMetadata.csproj',
                    'scripts/prepare-starrail-reader.py', 'packaging/starrail-reader/inputs.json')
    identity = _identity({name: _hash(ROOT / name) for name in source_names})
    receipt_path = directory / 'helper.json'
    try:
        receipt = json.loads(receipt_path.read_text())
        _check(receipt['source_identity'] == identity and re.fullmatch(r'helper-[a-zA-Z0-9_-]+', receipt['generation']))
        generation = directory / receipt['generation']; _no_links(generation)
        files = receipt['files']
        _check(set(files) == {'StarRailMetadata.dll', 'StarRailMetadata.deps.json', 'StarRailMetadata.runtimeconfig.json', 'Iced.dll'})
        for name, digest in files.items():
            _no_links(generation / name)
            _check(_hash(generation / name) == digest)
        from .nte_assets import dotnet_sdk
        sdk = dotnet_sdk()
        if sdk:
            return Helper((str(sdk), str(generation / 'StarRailMetadata.dll')), _identity({'source': identity, 'files': files}))
    except (OSError, ValueError, KeyError, TypeError):
        pass
    from .nte_assets import dotnet_sdk
    sdk = dotnet_sdk()
    if not sdk:
        raise ValueError('The source checkout needs the .NET 10 SDK for original Star Rail metadata; installed bundles use their included helper.')
    # Import only the owned build-host preparer. Downloaded files are selected
    # compiler inputs, never imported Python or loaded client libraries.
    spec = importlib.util.spec_from_file_location('starrail_software_preparation', ROOT / source_names[2])
    preparation = importlib.util.module_from_spec(spec); spec.loader.exec_module(preparation)
    cache = directory / 'software'; cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='helper-build-', dir=directory) as temporary:
        stage = Path(temporary)
        preparation.prepare(cache, stage / 'prepared', download=True)
        config = stage / 'NuGet.Config'; config.write_text('<configuration><packageSources><clear/></packageSources></configuration>')
        command = [str(sdk), 'build', str(ROOT / source_names[1]), '--configuration', 'Release',
                   '-p:RestoreConfigFile=' + str(config), '--nologo', '-p:UseAppHost=false', '-p:UseSharedCompilation=false',
                   '-p:NuGetAudit=false', '-p:DisableTransitiveFrameworkReferenceDownloads=true',
                   '-p:DebugType=None', '-p:DebugSymbols=false', '-p:StarRailSource=' + str(stage / 'prepared'),
                   '-p:BaseIntermediateOutputPath=' + str(stage / 'obj') + '/',
                   '--output', str(stage / 'compiled')]
        _run(command, stage, build=True)
        files = {name: _hash(stage / 'compiled' / name) for name in (
            'StarRailMetadata.dll', 'StarRailMetadata.deps.json', 'StarRailMetadata.runtimeconfig.json', 'Iced.dll')}
        _check(files['Iced.dll'] == json.loads(preparation.PINS.read_text())['decoder']['package']['dll_sha256'])
        target = directory / ('helper-' + stage.name.removeprefix('helper-build-'))
        (stage / 'compiled').rename(target)
        _atomic_file(receipt_path, json.dumps({'source_identity': identity, 'generation': target.name, 'files': files}).encode())
    return Helper((str(sdk), str(target / 'StarRailMetadata.dll')), _identity({'source': identity, 'files': files}))


@dataclass(frozen=True)
class Prepared:
    directory: Path
    inputs: Path
    outputs: Path
    receipt: dict
    helper: Helper

    def disassemble(self, ranges):
        """Read bounded authenticated native bytes through the managed decoder."""
        _check(isinstance(ranges, list) and 0 < len(ranges) <= 4096)
        with tempfile.TemporaryDirectory(prefix='native-ranges-', dir=self.directory) as temporary:
            work = Path(temporary); request = work / 'request.json'; output = work / 'result.json'
            request.write_text(json.dumps({'ranges': ranges}))
            self.helper.run('disassemble', self.inputs / 'GameAssembly.dll', request, output, work=work)
            _check(output.stat().st_size <= 128 * 1024**2)
            result = json.loads(output.read_text())
            _check(isinstance(result, list) and len(result) == len(ranges))
            return result


def _input(cache, asset):
    """Whole-file acceptance is independent from authenticated chunk reuse."""
    target = cache / 'native-files' / asset.digest; _no_links(target)
    target.parent.mkdir(exist_ok=True)
    if target.is_file() and target.stat().st_size == asset.size and _hash(target, 'md5') == asset.digest:
        return target
    with tempfile.TemporaryDirectory(prefix='original-input-', dir=target.parent) as temporary:
        staged = Path(temporary) / 'data'; md5 = hashlib.md5()
        with staged.open('xb') as stream:
            for at in range(0, asset.size, 16 * 1024**2):
                data = asset.read(cache / 'sophon', at, min(16 * 1024**2, asset.size - at))
                md5.update(data); stream.write(data)
        _check(staged.stat().st_size == asset.size and md5.hexdigest() == asset.digest)
        staged.replace(target)
    return target


def prepare(directory, build, *, reader=None):
    """Authenticate complete original inputs, regenerate metadata atomically."""
    directory = Path(directory).absolute(); _no_links(directory); directory.mkdir(parents=True, exist_ok=True)
    _check(build['channel'] in {'starrail-global', 'starrail-cn'})
    spec = build['manifests']['game']
    assets = sophon.manifest(directory / 'sophon', build['channel'], tuple(spec), tuple(NAMES.values()))
    chosen = {}
    for role, basename in NAMES.items():
        matches = [asset for asset in assets.values() if asset.name.rsplit('/', 1)[-1] == basename]
        maximum = {'native': 1024 * 1024**2, 'metadata': 512 * 1024**2, 'startup': 64 * 1024**2}[role]
        _check(len(matches) == 1 and 0 < matches[0].size <= maximum)
        chosen[role] = matches[0]
    reader = reader or helper(directory / 'tools')
    identity = {'manifest': list(spec), 'channel': build['channel'], 'helper': reader.identity,
                'files': {role: {'name': asset.name, 'bytes': asset.size, 'md5': asset.digest} for role, asset in chosen.items()}}
    key = _identity(identity); generations = directory / 'generations'; generations.mkdir(exist_ok=True)
    current = directory / 'current.json'
    try:
        previous = json.loads(current.read_text())
        _check(previous['identity'] == identity and re.fullmatch(r'generation-[a-zA-Z0-9_-]+', previous['generation']))
        generation = generations / previous['generation']; _no_links(generation)
        for role, asset in chosen.items():
            path = generation / 'inputs' / CANONICAL[role]; _no_links(path)
            _check(path.stat().st_size == asset.size and _hash(path, 'md5') == asset.digest)
        _check(set(previous['outputs']) == set(OUTPUTS))
        for name, digest in previous['outputs'].items():
            path = generation / 'outputs' / name; _no_links(path)
            _check(0 < path.stat().st_size <= OUTPUTS[name] and _hash(path) == digest)
        return Prepared(directory, generation / 'inputs', generation / 'outputs', previous, reader)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    # Sophon chunks are immutable and independently authenticated, so interrupted
    # attempts reuse complete chunks. Only full MD5 acceptance publishes inputs.
    with tempfile.TemporaryDirectory(prefix='generation-', dir=generations) as temporary:
        stage = Path(temporary); inputs = stage / 'inputs'; inputs.mkdir()
        for role, asset in chosen.items():
            target = inputs / CANONICAL[role]; target.parent.mkdir(parents=True, exist_ok=True)
            verified = _input(directory, asset)
            try:
                os.link(verified, target)
            except OSError:
                shutil.copyfile(verified, target)
        reader.run('metadata', inputs, stage / 'outputs', work=stage)
        output_hashes = {}
        for name, maximum in OUTPUTS.items():
            path = stage / 'outputs' / name; _no_links(path)
            _check(0 < path.stat().st_size <= maximum)
            output_hashes[name] = _hash(path)
        generation = generations / (stage.name + '-' + key[:12])
        stage.rename(generation)
        receipt = {'identity': identity, 'generation': generation.name, 'outputs': output_hashes}
        _atomic_file(current, json.dumps(receipt, sort_keys=True).encode())
    return Prepared(directory, generation / 'inputs', generation / 'outputs', receipt, reader)
