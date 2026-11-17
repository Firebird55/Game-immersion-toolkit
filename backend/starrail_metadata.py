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
import struct
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
        _check(operation in {'metadata', 'disassemble', 'native-graph'} and len(paths) == (2 if operation == 'metadata' else 3)
               and all(Path(path).is_absolute() for path in paths))
        _run([*self.command, operation, *(str(path) for path in paths)], work)


def helper(directory, *, allow_build=True):
    """Resolve a compiler-free apphost, or build fixed software in source mode."""
    _check(type(allow_build) is bool)
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
    if not allow_build:
        raise ValueError('The Star Rail metadata helper is not prepared on this device.')
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

    def native_graph(self, entry_rva):
        """Follow original PE-owned direct branches, without metadata decoding.

        This operation also works while diagnosing a changed metadata codec;
        it requires only authenticated native input and the fixed reader.
        """
        _check(type(entry_rva) is int and 0 <= entry_rva < 1 << 32)
        source = self.inputs / CANONICAL['native']
        spec = self.receipt['identity']['files']['native']
        _check(source.stat().st_size == spec['bytes'] and _hash(source, 'md5') == spec['md5'])
        with tempfile.TemporaryDirectory(prefix='native-graph-', dir=self.directory) as temporary:
            work = Path(temporary); request = work / 'request.json'; output = work / 'result.json'
            request.write_text(json.dumps({'entry_rva': entry_rva}))
            self.helper.run('native-graph', source, request, output, work=work)
            _check(output.stat().st_size <= 8 * 1024**2)
            result = _native_graph(json.loads(output.read_text()), source, entry_rva)
            _check(source.stat().st_size == spec['bytes'] and _hash(source, 'md5') == spec['md5'])
            return result

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


def _native_graph(value, source, entry_rva):
    """Validate the helper's closed graph and recheck every original region."""
    _check(isinstance(value, dict) and set(value) == {
        'schema', 'image_base', 'entry_rva', 'regions', 'instructions', 'edges', 'calls', 'returns'}
        and value['schema'] == 'proxy-starrail-native-graph-v1'
        and type(value['entry_rva']) is int and value['entry_rva'] == entry_rva)
    base = value['image_base']
    _check(type(base) is int and 0 <= base <= (1 << 64) - (1 << 32))
    regions = value['regions']
    _check(isinstance(regions, list) and 0 < len(regions) <= 16)
    _check(any(isinstance(r, dict) and r.get('rva') == entry_rva for r in regions))
    total, previous = 0, -1
    with Path(source).open('rb') as stream:
        image_base, sections, table_offset, function_count = _graph_pe(stream)
        _check(base == image_base)
        for region in regions:
            _check(isinstance(region, dict) and set(region) == {'rva', 'bytes', 'offset', 'unwind_rva', 'sha256'})
            start, size, offset, unwind = (region[k] for k in ('rva', 'bytes', 'offset', 'unwind_rva'))
            _check(all(type(v) is int for v in (start, size, offset, unwind))
                   and previous <= start < start + size <= 1 << 32 and 0 < size <= 32768
                   and 0 <= offset <= Path(source).stat().st_size - size and 0 < unwind < 1 << 32
                   and isinstance(region['sha256'], str) and re.fullmatch('[0-9a-f]{64}', region['sha256']))
            previous = start + size; total += size
            _check(total <= 32768)
            mappings = [off + start - rva for rva, length, off, executable in sections
                        if executable and rva <= start < start + size <= rva + length]
            _check(mappings == [offset] and sum(rva <= unwind < rva + length
                for rva, length, _, _ in sections) == 1)
            lo, hi = 0, function_count
            while lo < hi:
                middle = (lo + hi) // 2
                stream.seek(table_offset + middle * 12); first = struct.unpack('<I', stream.read(4))[0]
                if first <= start:
                    lo = middle + 1
                else:
                    hi = middle
            _check(lo > 0)
            stream.seek(table_offset + (lo - 1) * 12)
            _check(struct.unpack('<III', stream.read(12)) == (start, start + size, unwind))
            stream.seek(offset); raw = stream.read(size)
            _check(len(raw) == size and hashlib.sha256(raw).hexdigest() == region['sha256'])
    rows = value['instructions']
    _check(isinstance(rows, list) and 0 < len(rows) <= 8192)
    instructions, occupied = {}, set()
    previous = -1
    for row in rows:
        _check(isinstance(row, list) and len(row) == 4)
        address, operation, operands, size = row
        _check(type(address) is int and previous < address < 1 << 64 and type(size) is int and 0 < size <= 15
               and isinstance(operation, str) and re.fullmatch(r'(?:(?:lock|rep|repe|repne|bnd) )?[a-z][a-z0-9]{0,23}', operation)
               and isinstance(operands, str) and len(operands) <= 512)
        rva = address - base
        _check(sum(r['rva'] <= rva < rva + size <= r['rva'] + r['bytes'] for r in regions) == 1)
        positions = set(range(address, address + size))
        _check(not occupied & positions)
        occupied.update(positions); instructions[address] = operation.split()[-1], operands, size
        previous = address
    _check(base + entry_rva in instructions)
    edges = value['edges']
    _check(isinstance(edges, list) and len(edges) == len(instructions))
    links = {}
    for row in edges:
        _check(isinstance(row, list) and len(row) == 2)
        address, targets = row
        _check(type(address) is int and address in instructions and address not in links
               and isinstance(targets, list) and len(targets) <= 2
               and all(type(t) is int and t in instructions for t in targets) and len(targets) == len(set(targets)))
        operation, operands, size = instructions[address]
        if operation == 'ret':
            expected = set()
        elif operation == 'jmp' or operation.startswith('j') or operation in {'loop', 'loope', 'loopne'}:
            _check(re.fullmatch('0x[0-9a-f]+', operands))
            expected = {int(operands, 16)} | ({address + size} if operation != 'jmp' else set())
        else:
            _check(operation not in {'ud2', 'int3', 'int', 'syscall', 'sysenter'})
            expected = {address + size}
        _check(set(targets) == expected)
        links[address] = targets
    calls = value['calls']
    _check(isinstance(calls, list) and len(calls) <= len(instructions))
    call_addresses = set()
    for row in calls:
        _check(isinstance(row, list) and len(row) == 3)
        address, kind, target = row
        _check(type(address) is int and address in instructions and address not in call_addresses
               and instructions[address][0] == 'call' and kind in {'direct', 'indirect'})
        if kind == 'direct':
            _check(type(target) is int and 0 <= target < 1 << 64
                   and re.fullmatch('0x[0-9a-f]+', instructions[address][1])
                   and int(instructions[address][1], 16) == target)
        else:
            _check(target is None and not re.fullmatch('0x[0-9a-f]+', instructions[address][1]))
        call_addresses.add(address)
    _check(call_addresses == {a for a, (op, _, _) in instructions.items() if op == 'call'})
    returns = value['returns']
    _check(isinstance(returns, list) and returns and all(type(a) is int for a in returns)
           and len(returns) == len(set(returns))
           and set(returns) == {a for a, (op, _, _) in instructions.items() if op == 'ret'})
    reached, pending = set(), [base + entry_rva]
    while pending:
        address = pending.pop()
        if address not in reached:
            reached.add(address); pending.extend(links[address])
    _check(reached == set(instructions) and all(any(
        region['rva'] <= a - base < region['rva'] + region['bytes'] for a in reached) for region in regions))
    return value


def _graph_pe(stream):
    """Read the original mapping needed to validate helper-owned PE regions."""
    size = stream.seek(0, 2); stream.seek(0); dos = stream.read(64)
    _check(64 <= size <= 1024**3 and len(dos) == 64 and dos[:2] == b'MZ')
    pe, = struct.unpack_from('<I', dos, 60)
    _check(pe <= 1024**2 and pe <= size - 24)
    stream.seek(pe); coff = stream.read(24)
    count, optional = struct.unpack_from('<H', coff, 6)[0], struct.unpack_from('<H', coff, 20)[0]
    _check(coff[:4] == b'PE\0\0' and struct.unpack_from('<H', coff, 4)[0] == 0x8664
           and 0 < count <= 96 and 240 <= optional <= 4096 and pe + 24 + optional + count * 40 <= size)
    headers = stream.read(optional + count * 40)
    _check(struct.unpack_from('<H', headers)[0] == 0x20b and struct.unpack_from('<I', headers, 108)[0] >= 4)
    base, = struct.unpack_from('<Q', headers, 24)
    sections = []
    for i in range(count):
        at = optional + i * 40
        rva, length, offset = struct.unpack_from('<III', headers, at + 12)
        _check(rva + length <= 1 << 32 and offset + length <= size)
        sections.append((rva, length, offset, bool(struct.unpack_from('<I', headers, at + 36)[0] & 0x20000000)))
    directory, length = struct.unpack_from('<II', headers, 136)
    _check(directory > 0 and 0 < length <= 64 * 1024**2 and length % 12 == 0)
    mappings = [off + directory - rva for rva, span, off, _ in sections
                if rva <= directory < directory + length <= rva + span]
    _check(len(mappings) == 1)
    return base, sections, mappings[0], length // 12


def _input(cache, asset, *, fetch=None):
    """Whole-file acceptance is independent from authenticated chunk reuse."""
    target = cache / 'native-files' / asset.digest; _no_links(target)
    target.parent.mkdir(exist_ok=True)
    if target.is_file() and target.stat().st_size == asset.size and _hash(target, 'md5') == asset.digest:
        return target
    with tempfile.TemporaryDirectory(prefix='original-input-', dir=target.parent) as temporary:
        staged = Path(temporary) / 'data'; md5 = hashlib.md5()
        with staged.open('xb') as stream:
            for at in range(0, asset.size, 16 * 1024**2):
                options = {'fetch': fetch} if fetch is not None else {}
                data = asset.read(cache / 'sophon', at, min(16 * 1024**2, asset.size - at), **options)
                md5.update(data); stream.write(data)
        _check(staged.stat().st_size == asset.size and md5.hexdigest() == asset.digest)
        staged.replace(target)
    return target


def prepare(directory, build, *, reader=None, fetch=None):
    """Authenticate complete original inputs, regenerate metadata atomically."""
    directory = Path(directory).absolute(); _no_links(directory); directory.mkdir(parents=True, exist_ok=True)
    _check(build['channel'] in {'starrail-global', 'starrail-cn'})
    spec = build['manifests']['game']
    options = {'fetch': fetch} if fetch is not None else {}
    assets = sophon.manifest(directory / 'sophon', build['channel'], tuple(spec), tuple(NAMES.values()), **options)
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
            verified = _input(directory, asset, **options)
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
