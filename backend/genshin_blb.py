"""Frozen BLB software with private data parameters and bounded decompression.

Community source supplies numeric helper data only. Its code is never compiled
or executed. Official whole-package authentication and generation acceptance
belong to the publisher adapter before any resulting text is activated.
"""
from dataclasses import dataclass
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile

from .game_tools import _atomic_file
from .prebuilt_readers import GENSHIN_SOFTWARE, _no_links, prebuilt_reader, reader_environment
from .runtime_bundle import discover_layout
from .genshin_blb_body import unpack as _unpack_body


ROOT = Path(__file__).resolve().parents[1]
PARAMETERS = {'GF256Exp': 256, 'GF256Log': 256, 'Blb3AESSBox': 256, 'Blb3AESShift': 16,
              'Blb3RC4Key': 256, 'Blb3SBox': 1024, 'Blb3ShiftRow': 48, 'Blb3Key': 8, 'Blb3Mul': 8}
MAX_PACKAGE = 160 * 1024**2
MAX_BODY = 512 * 1024**2


def check(value):
    if not value:
        raise ValueError('Unsupported or incomplete original Genshin container preparation.')


def parameter_data(source):
    """Parse only fixed numeric array declarations; never import helper code."""
    check(isinstance(source, bytes) and 0 < len(source) <= 1024 * 1024)
    source = source.decode('utf-8-sig')
    values = {}
    for name, length in PARAMETERS.items():
        matches = list(re.finditer(r'\b' + name + r'\s*=\s*new\s+byte\s*\[(\d*)\]\s*\{([^}]+)\}', source))
        check(len(matches) == 1)
        declared, body = matches[0].groups()
        check(not declared or int(declared) == length)
        tokens = body.strip().rstrip(',').split(',')
        check(len(tokens) == length and all(re.fullmatch(r'\s*(?:0[xX][0-9a-fA-F]{1,2}|[0-9]{1,3})\s*', token) for token in tokens))
        numbers = [int(token.strip(), 16 if token.strip().lower().startswith('0x') else 10) for token in tokens]
        check(all(0 <= number <= 255 for number in numbers))
        values[name] = base64.b64encode(bytes(numbers)).decode('ascii')
    return json.dumps(values, sort_keys=True, separators=(',', ':')).encode()


def _digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(8 * 1024**2):
            result.update(block)
    return result.hexdigest()


def _run(command, directory, *, build=False):
    env = reader_environment()
    if build:
        for name in ('DOTNET_CLI_HOME', 'NUGET_PACKAGES', 'NUGET_HTTP_CACHE_PATH', 'NUGET_PLUGINS_CACHE_PATH',
                     'NUGET_SCRATCH', 'TEMP', 'TMP', 'TMPDIR', 'APPDATA', 'LOCALAPPDATA', 'USERPROFILE', 'PROGRAMDATA'):
            folder = directory / name.lower(); folder.mkdir(exist_ok=True)
            env[name] = str(folder)
        for name in ('ProgramFiles', 'ProgramFiles(x86)', 'ProgramW6432'):
            if os.environ.get(name):
                env[name] = os.environ[name]
        env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_SKIP_FIRST_TIME_EXPERIENCE='1',
                   DOTNET_CLI_WORKLOAD_UPDATE_NOTIFY_DISABLE='1', DOTNET_GENERATE_ASPNET_CERTIFICATE='false')
    result = subprocess.run(command, cwd=directory, env=env, capture_output=True, timeout=240,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    if result.returncode:
        if build:
            _atomic_file(directory.parent / 'blb-helper-build.log', result.stdout + result.stderr)
        raise ValueError('The frozen original Genshin container software could not complete this operation.')


@dataclass(frozen=True)
class Helper:
    command: tuple[str, ...]
    identity: str

    def decode(self, source, parameters, destination, *, work):
        paths = [Path(path).absolute() for path in (source, parameters, destination)]
        check(len(set(paths)) == 3 and not paths[2].exists())
        _run([*self.command, 'decode', *(str(path) for path in paths)], work)


def helper(directory):
    """Installed bundles use their closed apphost; only source mode compiles."""
    layout = discover_layout()
    if layout.mode == 'bundle':
        reader = prebuilt_reader('genshin', layout=layout)
        return Helper((str(reader.executable),), hashlib.sha256((reader.source_identity + reader.manifest['build_id']).encode()).hexdigest())
    directory = Path(directory).absolute(); _no_links(directory); directory.mkdir(parents=True, exist_ok=True)
    names = ('scripts/game-readers/GenshinBlb.cs', 'scripts/game-readers/GenshinBlb.csproj',
             'packaging/genshin-reader/upstream/BlbUtils.cs', 'packaging/genshin-reader/inputs.json',
             'packaging/genshin-reader/AnimeStudio-LICENSE.txt')
    sources = {name: _digest(ROOT / name) for name in names}
    check(sources[names[2]] == GENSHIN_SOFTWARE['software_sha256'] and sources[names[4]] == GENSHIN_SOFTWARE['license_sha256'])
    identity = hashlib.sha256(json.dumps(sources, sort_keys=True).encode()).hexdigest()
    from .nte_assets import dotnet_sdk
    sdk = dotnet_sdk()
    if not sdk:
        raise ValueError('This source checkout requires the .NET 10 SDK; installed bundles include the original-container helper.')
    try:
        receipt = json.loads((directory / 'helper.json').read_bytes())
        check(receipt['source_identity'] == identity and re.fullmatch(r'helper-[a-zA-Z0-9_-]+', receipt['generation']))
        generation = directory / receipt['generation']; _no_links(generation)
        check(set(receipt['files']) == {'GenshinBlb.dll', 'GenshinBlb.deps.json', 'GenshinBlb.runtimeconfig.json'})
        check(all(_digest(generation / name) == digest for name, digest in receipt['files'].items()))
        closure = hashlib.sha256(json.dumps({'source': identity, 'files': receipt['files']}, sort_keys=True).encode()).hexdigest()
        return Helper((str(sdk), str(generation / 'GenshinBlb.dll')), closure)
    except (OSError, ValueError, KeyError, TypeError):
        pass
    with tempfile.TemporaryDirectory(prefix='blb-build-', dir=directory) as value:
        stage = Path(value)
        config = stage / 'NuGet.Config'
        config.write_text('<configuration><packageSources><clear/></packageSources></configuration>')
        command = [str(sdk), 'build', str(ROOT / names[1]), '-c', 'Release', '--nologo',
                   '-p:RestoreConfigFile=' + str(config), '-p:UseAppHost=false', '-p:UseSharedCompilation=false',
                   '-p:NuGetAudit=false', '-p:DisableTransitiveFrameworkReferenceDownloads=true',
                   '-p:BaseIntermediateOutputPath=' + str(stage / 'obj') + '/', '-o', str(stage / 'out')]
        _run(command, stage, build=True)
        generation = directory / ('helper-' + identity[:24]); generation.mkdir(exist_ok=True)
        files = {}
        for name in ('GenshinBlb.dll', 'GenshinBlb.deps.json', 'GenshinBlb.runtimeconfig.json'):
            raw = (stage / 'out' / name).read_bytes()
            _atomic_file(generation / name, raw); files[name] = hashlib.sha256(raw).hexdigest()
        _atomic_file(generation / 'AnimeStudio-LICENSE.txt', (ROOT / names[4]).read_bytes())
        _atomic_file(directory / 'helper.json', json.dumps({'source_identity': identity, 'generation': generation.name, 'files': files}).encode())
    closure = hashlib.sha256(json.dumps({'source': identity, 'files': files}, sort_keys=True).encode()).hexdigest()
    return Helper((str(sdk), str(generation / 'GenshinBlb.dll')), closure)


def unpack(decoded, destination):
    """Decompress a legacy desktop client's complete original BLB body."""
    return _unpack_body(decoded, destination, max_package=MAX_PACKAGE, max_body=MAX_BODY)
