"""Quarantined FFmpeg/Opus build experiment, never runtime supplier authority.

Original project orchestration stays under LICENSE. The additional grant for
three Xiph FLAC kit inputs does not apply here. Original dependency recipes and
notices are retained separately, without a source-delivery approval claim.
"""
import argparse
import hashlib
import importlib.util
import itertools
import json
import os
from pathlib import Path, PurePosixPath
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PIN = ROOT / 'packaging/codecs/ffmpeg-opus-replay.json'
PROJECT_INPUTS = ('packaging/codecs/ffmpeg-opus-replay.json',
    'scripts/replay-game-codec.py', 'scripts/build-game-codec-replay.ps1',
    'scripts/fixtures/game-codec-replay.c', 'backend/codec_fixture.py', 'LICENSE',
    'scripts/pinned-build-cmake.py', 'packaging/build-tools/cmake-4.4.5-windows-x64.json',
    'packaging/codecs/patches/ffmpeg-9.0.2-makedef-private-stdout.patch')
MAKEDEF_ROLES = ('avcodec', 'avformat', 'avutil', 'swresample')
VARIANT_PATCH = 'packaging/codecs/patches/ffmpeg-9.0.2-makedef-private-stdout.patch'
PUBLIC_FFMPEG_GENERATED = ('.config', 'config.fate', 'config.mak', 'config.sh')
DIAGNOSTIC_REASONS = frozenset(('source-binding', 'missing-layout', 'unexpected-layout',
    'unsupported-role', 'duplicate-role', 'nonempty-ar', 'unsupported-branch',
    'oversized-input', 'unsupported-response-files'))
DLLS = ('avcodec-vgmstream-63.dll', 'avformat-vgmstream-63.dll',
        'avutil-vgmstream-61.dll', 'swresample-vgmstream-7.dll')
BUILD_PHASES = ('extract-msys-base', 'extract-make', 'extract-nasm', 'extract-pkgconf',
    'check-shell', 'check-make', 'check-nasm', 'check-pkgconf', 'configure-opus',
    'build-opus', 'install-opus', 'configure-ffmpeg', 'clean-ffmpeg', 'build-ffmpeg',
    'install-ffmpeg', 'compile-probe', 'observe-and-package')
ERROR_CODES = frozenset(('C1001', 'C1083', 'C1189', 'C1900', 'C2039', 'C2059', 'C2061',
    'C2065', 'C2143', 'C2146', 'C2371', 'C2375', 'C2440', 'C2660', 'C2664', 'C3861',
    'D8016', 'D8021', 'D8022', 'D8027', 'D8036', 'D8037', 'D8045', 'D8048', 'D8049',
    'LNK1104', 'LNK1112', 'LNK1120', 'LNK1169', 'LNK1181', 'LNK2001', 'LNK2005',
    'LNK2019', 'LNK2038', 'MSB1009', 'MSB3073', 'MSB4018', 'MSB6003', 'MSB6006',
    'MSB8020', 'MSB8036', 'MSB8066'))
ERROR_FAMILIES = {'C': ('compiler-error', 'unclassified-compiler-code'),
    'D': ('compiler-command-line-error', 'unclassified-command-line-code'),
    'LNK': ('linker-error', 'unclassified-linker-code'),
    'MSB': ('msbuild-error', 'unclassified-msbuild-code')}
CMAKE_CATEGORIES = {
    'cmake-error': r'\bCMake Error\b',
    'cmake-generator-selection': r'could not create named generator|generator[^\r\n]{0,100}does not match',
    'cmake-toolchain-selection': r'could not find any instance of Visual Studio|does not support platform specification',
    'cmake-compiler-check': r'is not able to compile a simple test program',
    'cmake-package-discovery': r'could not find a package configuration file provided by|could NOT find',
}
# Format observations only: never copy the matched tool, target or message.
MAKE_PREFIX = r'^(?:[^\r\n]*[\\/])?make(?:\.exe)?(?:\[[0-9]+\])?:[ \t]+\*\*\*[ \t]+'
SHELL_PREFIX = r'^(?:[^\r\n]*[\\/])?(?:bash|sh)(?:\.exe)?:[ \t]+(?:line [0-9]+:[ \t]+)?'
TOOL_CATEGORIES = {
    'make-fatal-error': MAKE_PREFIX,
    'make-recipe-error': MAKE_PREFIX + r'\[[^\r\n]+\][ \t]+Error[ \t]+[0-9]+[ \t]*\r?$',
    'make-no-rule': MAKE_PREFIX + r'No rule to make target[ \t]+[^\r\n]+',
    'shell-command-not-found': SHELL_PREFIX + r'[^\r\n]+:[ \t]+command not found[ \t]*\r?$',
    'shell-cannot-execute': SHELL_PREFIX + r'[^\r\n]+:[ \t]+cannot execute(?:[ :][^\r\n]*)?\r?$',
    'shell-permission-denied': SHELL_PREFIX + r'[^\r\n]+:[ \t]+Permission denied[ \t]*\r?$',
    'nasm-assembly-error': r'^[^\r\n]+\.asm(?::[0-9]+:|\([0-9]+\)[ \t]*:)[ \t]+(?:fatal|error):[ \t]+[^\r\n]+',
    'nasm-invocation-error': r'^nasm(?:\.exe)?:[ \t]+(?:fatal|error):[ \t]+[^\r\n]+',
}
MAKEDEF_CATEGORIES = {
    'ffmpeg-makedef-missing-version-script': r'^Version script does not exist\r?$',
    'ffmpeg-makedef-missing-object': r'^Object does not exist:[ \t]+[^\r\n]+',
    'ffmpeg-makedef-temporary-library': r'^Could not create temporary library\.\r?$',
}
FAILURE_LOG_LIMIT = 2 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def policy():
    return json.loads(PIN.read_text(encoding='utf-8'))


def no_links(path):
    path = Path(path).absolute()
    if '..' in path.parts: raise ValueError('Non-canonical experiment input.')
    # Inspect the raw path from root to leaf. Even a descendant stat/lstat can
    # traverse a linked ancestor, before any content-open guard gets a chance.
    for item in (*reversed(path.parents), path):
        try: info = item.lstat()
        except FileNotFoundError:
            return None  # Fresh outputs may have a missing suffix; do not inspect it.
        if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & 0x400:
            raise ValueError('Links and reparse points are not experiment inputs.')
        if item != path and not stat.S_ISDIR(info.st_mode):
            raise ValueError('Experiment input ancestor is not a directory.')
    return info


def regular_file(path):
    info = no_links(path)
    if info is None or not stat.S_ISREG(info.st_mode):
        raise ValueError('Experiment input is not a regular file.')
    return info


def inventory(root):
    root = Path(root); info = no_links(root)
    if info is None or not stat.S_ISDIR(info.st_mode):
        raise ValueError('Experiment inventory root is not a directory.')
    result = {}; pending = [root]
    while pending:
        directory = pending.pop(); no_links(directory)
        for path in sorted(directory.iterdir()):
            info = no_links(path)
            if info is not None and stat.S_ISREG(info.st_mode):
                result[path.relative_to(root).as_posix()] = {
                    'bytes': info.st_size, 'sha256': digest(path.read_bytes())}
            elif info is not None and stat.S_ISDIR(info.st_mode): pending.append(path)
            else: raise ValueError('Non-regular experiment entry.')
    return dict(sorted(result.items()))


def tree_identity(value):
    return {'files': len(value), 'sha256': digest(json.dumps(value, sort_keys=True,
        separators=(',', ':')).encode())}


def public_generated_configuration(root):
    """Bind reviewed configuration publicly; keep the complete log inventory private."""
    directory = root / 'ffmpeg-build/ffbuild'; info = no_links(directory)
    if info is None or not stat.S_ISDIR(info.st_mode):
        raise ValueError('Generated configuration directory is unavailable.')
    private = root / 'PRIVATE-FFMPEG-GENERATED.json'; prior = no_links(private)
    if prior is not None and not stat.S_ISREG(prior.st_mode):
        raise ValueError('Private generated inventory is not a regular file.')
    expected = set(PUBLIC_FFMPEG_GENERATED) | {'config.log'}
    entries = list(itertools.islice(directory.iterdir(), len(expected) + 1))
    if len(entries) != len(expected) or {path.name for path in entries} != expected:
        raise ValueError('Unexpected generated configuration layout.')
    # Refuse every unknown name/type/link before reading any member content.
    checked = [(path, regular_file(path)) for path in sorted(entries)]
    full = {path.name: {'bytes': metadata.st_size, 'sha256': digest(path.read_bytes())}
            for path, metadata in checked}
    write_json(private, full)
    return {name: full[name] for name in PUBLIC_FFMPEG_GENERATED}


def variant_definition(pin):
    variant = pin.get('diagnostic_variant')
    if variant is None and not any(x['component'] == 'ffmpeg' for x in pin['sources']):
        return None  # Authored non-FFmpeg source fixtures only.
    if (type(variant) is not dict or set(variant) != {'schema', 'scope', 'source_member',
            'preimage', 'patch', 'postimage', 'original_tree', 'modified_tree', 'roles', 'original_notice'}
            or variant['schema'] != 'proxy-r19-makedef-stdout-variant-v1'
            or variant['roles'] != list(MAKEDEF_ROLES)
            or type(variant['patch']) is not dict or variant['patch'].get('path') != VARIANT_PATCH):
        raise ValueError('Unsupported fixed diagnostic variant.')
    source = [x for x in pin['sources'] if x['component'] == 'ffmpeg']
    if len(source) != 1 or variant['source_member'] != source[0]['root'] + '/compat/windows/makedef':
        raise ValueError('Diagnostic variant is not the exact FFmpeg script.')
    for key in ('preimage', 'postimage', 'patch'):
        record = variant[key]
        if (type(record) is not dict or set(record) != ({'bytes', 'sha256', 'path'} if key == 'patch' else {'bytes', 'sha256'})
                or type(record['bytes']) is not int or not 0 < record['bytes'] <= 65536
                or not isinstance(record['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', record['sha256'])):
            raise ValueError('Invalid diagnostic byte binding.')
    for key in ('original_tree', 'modified_tree'):
        record = variant[key]
        if (type(record) is not dict or set(record) != {'files', 'sha256'}
                or type(record['files']) is not int or not 0 < record['files'] < 32000
                or not isinstance(record['sha256'], str) or not re.fullmatch('[a-f0-9]{64}', record['sha256'])):
            raise ValueError('Invalid diagnostic source tree binding.')
    return variant


def bound_bytes(path, record):
    regular_file(path)
    if type(record.get('bytes')) is not int or not 0 < record['bytes'] <= 64 * 1024 * 1024:
        raise ValueError('Diagnostic byte count exceeds its fixed bound.')
    with path.open('rb') as stream: raw = stream.read(record['bytes'] + 1)
    if len(raw) != record['bytes'] or digest(raw) != record['sha256']:
        raise ValueError('Diagnostic input differs from its exact byte binding.')
    return raw


def instrument_makedef(original, patch, variant):
    """Apply only the fully bound single-file unified patch, without a tool fallback."""
    for raw, key in ((original, 'preimage'), (patch, 'patch')):
        if len(raw) != variant[key]['bytes'] or digest(raw) != variant[key]['sha256']:
            raise ValueError('Diagnostic patch preimage or patch hash differs.')
    source = original.splitlines(keepends=True); lines = patch.splitlines(keepends=True)
    if lines[:2] != [b'--- a/compat/windows/makedef\n', b'+++ b/compat/windows/makedef\n']:
        raise ValueError('Unsupported diagnostic patch header.')
    result = []; cursor = 0; index = 2; hunks = 0
    while index < len(lines):
        match = re.fullmatch(rb'@@ -([0-9]+)(?:,([0-9]+))? \+([0-9]+)(?:,([0-9]+))? @@\n', lines[index])
        if not match: raise ValueError('Unsupported diagnostic patch hunk.')
        old, count, new, added = [int(x) if x else 1 for x in match.groups()]
        position = old if count == 0 else old - 1
        if position < cursor or position > len(source):
            raise ValueError('Diagnostic patch hunk is outside its preimage.')
        result.extend(source[cursor:position]); cursor = position
        if new != len(result) + 1: raise ValueError('Diagnostic patch position differs.')
        index += 1; removed = inserted = 0
        while index < len(lines) and not lines[index].startswith(b'@@ '):
            line = lines[index]; kind, value = line[:1], line[1:]
            if kind in (b' ', b'-'):
                if cursor >= len(source) or source[cursor] != value:
                    raise ValueError('Diagnostic patch context differs.')
                cursor += 1; removed += 1
            if kind in (b' ', b'+'): result.append(value); inserted += 1
            if kind not in (b' ', b'-', b'+'): raise ValueError('Unsupported diagnostic patch operation.')
            index += 1
        if (removed, inserted) != (count, added): raise ValueError('Diagnostic patch hunk size differs.')
        hunks += 1
    result.extend(source[cursor:]); modified = b''.join(result)
    if (not hunks or len(modified) != variant['postimage']['bytes']
            or digest(modified) != variant['postimage']['sha256']):
        raise ValueError('Diagnostic postimage differs.')
    return modified


def variant_receipt(pin):
    variant = variant_definition(pin)
    if variant is None: return None
    return {'schema': 'proxy-r19-makedef-stdout-variant-receipt-v1',
        'identity': 'diagnostic-makedef-' + digest(json.dumps(variant, sort_keys=True, separators=(',', ':')).encode()),
        'status': 'diagnostic-only; observed-not-approved', 'definition': variant,
        'original_source_archive': next(x for x in pin['sources'] if x['component'] == 'ffmpeg'),
        'source_delivery_approved': False, 'runtime_collection_allowed': False, 'r19_complete': False}


def inputs(pin, *, tools=True):
    records = pin['sources'] + [dict(x, source=x['download']) for x in pin['original_recipes']]
    return records + (pin['build_tools'] if tools else [])


def acquire(destination):
    destination = Path(destination).absolute(); no_links(destination)
    if destination.exists():
        raise ValueError('Input acquisition requires a fresh directory.')
    destination.mkdir(parents=True)
    for record in inputs(policy()):
        # All URLs are committed HTTPS pins, with bounded download time/size.
        if not record['source'].startswith('https://'):
            raise ValueError('Input is not an HTTPS pin.')
        request = urllib.request.Request(record['source'], headers={'User-Agent': 'R19-source-replay'})
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = response.read(64 * 1024 * 1024 + 1)
        if len(raw) > 64 * 1024 * 1024 or digest(raw) != record['sha256']:
            raise ValueError('An acquired input differs from its committed hash.')
        (destination / record['filename']).write_bytes(raw)


def safe_member(name):
    value = name.rstrip('/')
    if (not value or '\\' in value or ':' in value or PurePosixPath(value).is_absolute()
            or any(p in {'', '.', '..'} or p.endswith((' ', '.')) for p in value.split('/'))
            or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        raise ValueError('Non-canonical source archive path.')
    return value


def validate_source(archive, record, notices):
    with tarfile.open(archive) as tar:
        members, seen = tar.getmembers(), set()
        if len(members) > 16000 or sum(m.size for m in members) > 160 * 1024 * 1024:
            raise ValueError('Source archive exceeds experiment bounds.')
        for member in members:
            name = safe_member(member.name)
            if (name.split('/')[0] != record['root'] or name.casefold() in seen
                    or not (member.isfile() or member.isdir())
                    or member.size > 32 * 1024 * 1024
                    or Path(name).suffix.lower() in {'.exe', '.dll', '.lib', '.a', '.so', '.o', '.obj'}):
                raise ValueError('Unsupported or native source archive entry.')
            seen.add(name.casefold())
        for notice in notices:
            stream = tar.extractfile(record['root'] + '/' + notice['path'])
            if stream is None or digest(stream.read()) != notice['sha256']:
                raise ValueError('Original dependency notice differs.')


def original_options(raw):
    lines = [line.strip() for line in raw.decode('utf-8').splitlines()
             if line.strip() and not line.lstrip().startswith('#')]
    if not lines or any(not line.startswith('--') or len(shlex.split(line)) != 1 for line in lines):
        raise ValueError('Original FFmpeg options are not a plain option list.')
    if ('--enable-gpl' in lines or '--enable-nonfree' in lines
            or '--enable-version3' in lines or '--enable-libopus' not in lines):
        raise ValueError('Unexpected experiment configuration licensing boundary.')
    return lines


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')


def preflight_failure(output, observed):
    """Failure-only numeric resource observation, with no native output text."""
    output = Path(output).absolute(); no_links(output)
    if output.exists(): raise ValueError('Preflight failure output must be fresh.')
    fields = {'cmake': {'version', 'bytes', 'sha256'},
              'cl': {'file_version', 'product_version', 'bytes', 'sha256'}}
    if type(observed) is not dict or set(observed) != set(fields):
        raise ValueError('Unexpected numeric preflight observation fields.')
    for name, names in fields.items():
        value = observed[name]
        if type(value) is not dict or set(value) != names:
            raise ValueError('Unexpected numeric tool observation fields.')
        if (type(value['bytes']) is not int or not 0 < value['bytes'] < 256*1024*1024
                or type(value['sha256']) is not str or not re.fullmatch(r'[a-f0-9]{64}', value['sha256'])):
            raise ValueError('Invalid tool byte identity.')
        for field in names - {'bytes', 'sha256'}:
            pattern = r'[0-9]{1,6}(?:\.[0-9]{1,6}){2}' if name == 'cmake' else r'[0-9]{1,6}(?:\.[0-9]{1,6}){3}'
            if type(value[field]) is not str or not re.fullmatch(pattern, value[field]):
                raise ValueError('Tool resource versions must be strictly numeric.')
    manifest_bytes = PIN.read_bytes(); pin = json.loads(manifest_bytes)
    expected = {'cmake': pin['host']['cmake_version'], 'compiler': pin['host']['compiler_version']}
    if (not re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,6}){2}', expected['cmake'])
            or not re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,6}){3}', expected['compiler'])):
        raise ValueError('Expected tool versions must be strictly numeric.')
    mismatches = []
    if observed['cmake']['version'] != expected['cmake']: mismatches.append('cmake-version')
    if observed['cl']['file_version'] != expected['compiler']: mismatches.append('cl-file-resource-version')
    if not mismatches: raise ValueError('No checked tool version mismatch was observed.')
    commit = os.environ.get('GITHUB_SHA', '')
    if not re.fullmatch(r'[a-f0-9]{40}', commit): raise ValueError('A source-bound preflight observation is required.')
    report = {'schema': 'proxy-r19-game-codec-replay-preflight-failure-v1', 'status': 'failed',
        'phase': 'preflight-tool-version', 'source_commit': commit,
        'input_manifest': {'path': 'packaging/codecs/ffmpeg-opus-replay.json',
                           'bytes': len(manifest_bytes), 'sha256': digest(manifest_bytes)},
        'expected_versions': expected, 'observed_tools': observed, 'mismatch_fields': mismatches,
        'cl_product_resource_role': 'observation-only; compiler identification is not inferred from resource versions',
        'raw_log_published': False, 'native_codec_built': False, 'native_codec_executed': False,
        'runtime_collection_allowed': False, 'production_execution_allowed': False,
        'source_delivery_approved': False, 'native_windows_11_acceptance': 'unavailable',
        'installer': 'not-built', 'r19_complete': False}
    # Only a diagnosed mismatch creates this directory, and the caller exits.
    # A matching preflight leaves prepare() its required fresh destination.
    output.mkdir(parents=True)
    write_json(output / 'FAILED-STAGE.json', report)
    return report


def read_preflight_observation(stream):
    raw = stream.read(8193)
    if len(raw) > 8192: raise ValueError('Numeric preflight observation exceeds its bound.')
    def unique(items):
        value = {}
        for key, item in items:
            if key in value: raise ValueError('Duplicate preflight observation field.')
            value[key] = item
        return value
    return json.loads(raw, object_pairs_hook=unique)


def failure(output, phase, exit_code, log, offset, *, include_makedef=False):
    """Emit categories only, never log text/path/arguments or a passing receipt.

    A fixed code allowlist prevents arbitrary numbers/tokens from private input
    becoming diagnostics. Offset excludes earlier successful commands; bounded
    tail reads keep failure parsing independent of an unbounded compiler log.
    """
    if (phase not in BUILD_PHASES or type(exit_code) is not int or exit_code == 0
            or not -(2**31) <= exit_code < 2**32 or type(offset) is not int or offset < 0):
        raise ValueError('Invalid fixed build failure identity.')
    output = Path(output).absolute(); log = Path(log).absolute()
    no_links(output); no_links(log)
    if not output.is_dir() or not log.is_file():
        raise ValueError('Failure diagnosis requires the private build log and existing quarantine.')
    with log.open('rb') as stream:
        stream.seek(0, 2); size = stream.tell()
        if offset > size: raise ValueError('Failure offset exceeds the completed private log.')
        start = max(offset, size - FAILURE_LOG_LIMIT)
        stream.seek(start)
        raw = stream.read(size - start)
    if start > offset:
        # The byte bound may cut through a diagnostic or its original prefix.
        # Never turn that fragment into a new line/word boundary for parsing.
        raw = raw.partition(b'\n')[2]
    codes, categories = classify_failure(raw, phase)
    commit = os.environ.get('GITHUB_SHA', '')
    report = {'schema': 'proxy-r19-game-codec-replay-failure-v1', 'status': 'failed',
        'source_commit': commit if re.fullmatch(r'[a-f0-9]{40}', commit) else None,
        'phase': phase, 'exit_code': exit_code, 'diagnostic_codes': codes,
        'diagnostic_categories': categories,
        'log_scope': 'failed-command-only-bounded-tail', 'log_truncated': start > offset,
        'raw_log_published': False, 'runtime_collection_allowed': False,
        'production_execution_allowed': False, 'source_delivery_approved': False,
        'native_windows_11_acceptance': 'unavailable', 'r19_complete': False}
    if include_makedef and phase in ('build-ffmpeg', 'install-ffmpeg', 'observe-and-package'):
        report['makedef_diagnostics'] = makedef_diagnostics(output)
    write_json(output / 'FAILED-STAGE.json', report)
    return report


def classify_failure(raw, phase, *, unclassified=True):
    text = raw.decode('utf-8', errors='replace')
    observed_codes = {code.upper() for code in re.findall(
        r'\berror[ \t]+((?:C|D|LNK|MSB)[0-9]{4})[ \t]*:', text, flags=re.IGNORECASE)}
    codes = sorted(observed_codes & ERROR_CODES)
    categories = set()
    for code in observed_codes:
        family = re.match(r'[A-Z]+', code).group()
        categories.add(ERROR_FAMILIES[family][0 if code in ERROR_CODES else 1])
    if re.search(CMAKE_CATEGORIES['cmake-error'], text, flags=re.IGNORECASE):
        for category, pattern in CMAKE_CATEGORIES.items():
            if re.search(pattern, text, flags=re.IGNORECASE): categories.add(category)
    for category, pattern in TOOL_CATEGORIES.items():
        if re.search(pattern, text, flags=re.IGNORECASE | re.MULTILINE): categories.add(category)
    if phase in ('build-ffmpeg', 'install-ffmpeg'):
        for category, pattern in MAKEDEF_CATEGORIES.items():
            if re.search(pattern, text, flags=re.MULTILINE): categories.add(category)
    if unclassified and not categories: categories.add('unclassified-command-failure')
    return codes, sorted(categories)


def prepare(input_root, output, *, include_tools=True):
    pin = policy(); input_root = Path(input_root).absolute(); output = Path(output).absolute()
    no_links(input_root); no_links(output)
    if output.exists():
        raise ValueError('A fresh quarantine root is required; existing work is preserved.')
    # Validate every source, recipe and tool hash before creating output.
    for record in inputs(pin, tools=include_tools):
        path = input_root / record['filename']; no_links(path)
        if not path.is_file() or digest(path.read_bytes()) != record['sha256']:
            raise ValueError('Input differs from the exact experiment pin.')
    for record in pin['sources']:
        validate_source(input_root / record['filename'], record,
                        [n for n in pin['notices'] if n['component'] == record['component']])
    variant = variant_definition(pin)
    if variant:
        patch = bound_bytes(ROOT / VARIANT_PATCH, variant['patch'])
        record = next(x for x in pin['sources'] if x['component'] == 'ffmpeg')
        with tarfile.open(input_root / record['filename']) as tar:
            stream = tar.extractfile(variant['source_member'])
            if stream is None: raise ValueError('Exact diagnostic preimage is unavailable.')
            original = stream.read(65537)
        modified = instrument_makedef(original, patch, variant)
    options = original_options((input_root / 'vgmstream-ffmpeg_options.txt').read_bytes())
    output.mkdir(parents=True)
    kit = output / 'source-review'; (kit / 'original-inputs').mkdir(parents=True)
    for record in inputs(pin, tools=False):
        shutil.copyfile(input_root / record['filename'], kit / 'original-inputs' / record['filename'])
    for name in PROJECT_INPUTS:
        target = kit / 'project-orchestration' / name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(ROOT / name, target)
    source = output / 'upstream'; source.mkdir()
    for record in pin['sources']:
        with tarfile.open(input_root / record['filename']) as tar:
            tar.extractall(source, filter='data')
    if variant:
        before = inventory(source)
        if tree_identity(before) != variant['original_tree']:
            raise ValueError('Original diagnostic source inventory differs.')
        write_json(output / 'ORIGINAL-SOURCE.json', before)
        retained = kit / 'diagnostic-variant'; retained.mkdir()
        (retained / 'ORIGINAL-makedef').write_bytes(original)
        (retained / 'MODIFIED-makedef').write_bytes(modified)
        (source / variant['source_member']).write_bytes(modified)
        if tree_identity(inventory(source)) != variant['modified_tree']:
            raise ValueError('Modified diagnostic source inventory differs.')
        receipt = variant_receipt(pin)
        write_json(output / 'DIAGNOSTIC-VARIANT.json', receipt)
        write_json(kit / 'DIAGNOSTIC-VARIANT.json', receipt)
        (output / 'PRIVATE-MAKEDEF').mkdir()
    write_json(output / 'PREPARED-SOURCE.json', inventory(source))
    write_json(output / 'ORIGINAL-OPTIONS.json', options)
    write_json(kit / 'BOUNDARY.json', {'scope': 'source-review-only; not approved corresponding source',
        'licensing_boundary': pin['licensing_boundary'], 'adaptations': pin['adaptations'],
        'source_delivery_approved': False, 'runtime_collection_allowed': False})


def pe_imports(raw):
    """Bounded x64 PE normal/delay import names; no dynamic-load inference."""
    def unpack(fmt, offset):
        if offset < 0 or offset + struct.calcsize(fmt) > len(raw):
            raise ValueError('Truncated PE metadata.')
        return struct.unpack_from(fmt, raw, offset)
    pe, = unpack('<I', 60); opt = pe + 24
    if (raw[:2] != b'MZ' or raw[pe:pe+4] != b'PE\0\0'
            or unpack('<H', pe+4)[0] != 0x8664 or unpack('<H', opt)[0] != 0x20b):
        raise ValueError('Expected x64 PE32+ output.')
    count, = unpack('<H', pe+6); size, = unpack('<H', pe+20)
    if count > 96 or size < 240:
        raise ValueError('Unexpected PE section bounds.')
    sections = [unpack('<IIII', opt + size + i*40 + 8) for i in range(count)]
    def offset(rva):
        for virtual, address, length, start in sections:
            if address <= rva < address + max(virtual, length):
                value = start + rva - address
                if value < start + length and value < len(raw): return value
        raise ValueError('Unmapped PE metadata.')
    result = {}
    for label, index, stride in [('imports', 1, 20), ('delay_imports', 13, 32)]:
        address, length = unpack('<II', opt+112+index*8); names = []
        if address:
            if length > stride*256: raise ValueError('Too many PE imports.')
            for i in range(length // stride):
                entry = offset(address) + i*stride
                fields = unpack('<' + 'I'*(stride//4), entry)
                if not any(fields): break
                name = fields[3] if index == 1 else fields[1]
                if index == 13 and not fields[0] & 1:
                    name -= unpack('<Q', opt+24)[0]
                start = offset(name); end = raw.find(b'\0', start, start+256)
                if end < 0: raise ValueError('Unterminated PE import name.')
                text = raw[start:end].decode('ascii')
                if not text or any(not (c.isalnum() or c in '._-') for c in text):
                    raise ValueError('Non-canonical PE import name.')
                names.append(text)
            else:
                raise ValueError('Unterminated PE import table.')
        result[label] = sorted(set(names), key=str.casefold)
    return result


def verify_sources(root):
    no_links(root / 'PREPARED-SOURCE.json')
    current = inventory(root / 'upstream')
    if current != json.loads((root / 'PREPARED-SOURCE.json').read_text()):
        raise ValueError('Build changed the original verified sources.')
    pin = policy(); variant = variant_definition(pin)
    if variant:
        for record in inputs(pin, tools=False):
            bound_bytes(root / 'source-review/original-inputs' / record['filename'], record)
        no_links(root / 'ORIGINAL-SOURCE.json')
        before = json.loads((root / 'ORIGINAL-SOURCE.json').read_text())
        if tree_identity(before) != variant['original_tree'] or tree_identity(current) != variant['modified_tree']:
            raise ValueError('Diagnostic source inventory differs from the exact original or variant.')
        for path in (root / 'DIAGNOSTIC-VARIANT.json', root / 'source-review/DIAGNOSTIC-VARIANT.json'):
            no_links(path)
            if json.loads(path.read_text()) != variant_receipt(pin):
                raise ValueError('Diagnostic variant identity differs.')
        original = bound_bytes(root / 'source-review/diagnostic-variant/ORIGINAL-makedef', variant['preimage'])
        modified = bound_bytes(root / 'source-review/diagnostic-variant/MODIFIED-makedef', variant['postimage'])
        patch = bound_bytes(ROOT / VARIANT_PATCH, variant['patch'])
        bound_bytes(root / 'source-review/project-orchestration' / VARIANT_PATCH, variant['patch'])
        if instrument_makedef(original, patch, variant) != modified:
            raise ValueError('Diagnostic source transformation differs.')


class DiagnosticUnavailable(ValueError):
    pass


def makedef_diagnostics(root):
    """Read only fixed owned layout and bounded private stdout; publish no text/hash."""
    result = {'schema': 'proxy-r19-makedef-private-stdout-observation-v1',
        'status': 'unavailable', 'reason': 'source-binding', 'variant_identity': None,
        'response_files': 'unavailable', 'archiver_environment': 'unsupported', 'components': [],
        'causal_attribution': 'not-established', 'raw_log_published': False,
        'source_delivery_approved': False, 'runtime_collection_allowed': False, 'r19_complete': False}
    try:
        verify_sources(root)
        receipt = variant_receipt(policy())
        if receipt is None: raise DiagnosticUnavailable('source-binding')
        result['variant_identity'] = receipt['identity']
        config = root / 'ffmpeg-build/ffbuild/config.mak'; regular_file(config)
        with config.open('rb') as stream: data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024: raise DiagnosticUnavailable('oversized-input')
        values = re.findall(rb'^RESPONSE_FILES=([^\r\n]*)\r?$', data, flags=re.MULTILINE)
        if len(values) != 1 or values[0] not in (b'yes', b'no'):
            raise DiagnosticUnavailable('unsupported-response-files')
        result['response_files'] = values[0].decode('ascii')
        private = root / 'PRIVATE-MAKEDEF'; no_links(private)
        if not private.is_dir(): raise DiagnosticUnavailable('missing-layout')
        entries = list(itertools.islice(private.iterdir(), 7))
        if len(entries) > 6: raise DiagnosticUnavailable('unexpected-layout')
        names = {x.name for x in entries}
        if 'unavailable-unknown-role' in names: raise DiagnosticUnavailable('unsupported-role')
        if 'unavailable-duplicate-role' in names: raise DiagnosticUnavailable('duplicate-role')
        if not names or not names <= set(MAKEDEF_ROLES): raise DiagnosticUnavailable('unexpected-layout')
        observations = []
        for role in sorted(names):
            directory = private / role; no_links(directory)
            if not directory.is_dir(): raise DiagnosticUnavailable('unexpected-layout')
            members = list(itertools.islice(directory.iterdir(), 3))
            if len(members) > 2: raise DiagnosticUnavailable('unexpected-layout')
            if {x.name for x in members} not in ({'branch-state'}, {'branch-state', 'stdout.log'}):
                raise DiagnosticUnavailable('unexpected-layout')
            for member in members: regular_file(member)
            branch = directory / 'branch-state'
            with branch.open('rb') as stream: state = stream.read(17)
            if state not in (b'empty\n', b'nonempty\n'): raise DiagnosticUnavailable('unsupported-branch')
            result['archiver_environment'] = state.strip().decode('ascii')
            if state == b'nonempty\n': raise DiagnosticUnavailable('nonempty-ar')
            log = directory / 'stdout.log'
            regular_file(log)
            with log.open('rb') as stream: raw = stream.read(FAILURE_LOG_LIMIT + 1)
            if len(raw) > FAILURE_LOG_LIMIT: raise DiagnosticUnavailable('oversized-input')
            codes, categories = classify_failure(raw, 'build-ffmpeg', unclassified=False)
            observations.append({'role': role, 'archiver_environment': 'empty',
                'diagnostic_codes': codes, 'diagnostic_categories': categories})
        result.update(status='observed-noncausal', reason=None, components=observations)
    except DiagnosticUnavailable as error:
        result['reason'] = error.args[0] if error.args and error.args[0] in DIAGNOSTIC_REASONS else 'source-binding'
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        result['reason'] = 'source-binding'
    return result


def validate_configuration(root, configuration):
    original = json.loads((root / 'ORIGINAL-OPTIONS.json').read_text())
    expected = original + ['--target-os=win64', '--toolchain=msvc', '--arch=x86_64',
                           '--prefix=/c/r19-game-codec-replay/out/ffmpeg-vs-64']
    if shlex.split(configuration) != expected:
        raise ValueError('Actual FFmpeg configuration differs from original options and declared adaptations.')


def sanitized_modules(lines, candidate):
    result = {}; expected = set(DLLS)
    for line in lines:
        if not line.startswith('module\t'): continue
        _, name, value = line.split('\t')
        path = Path(value); no_links(path)
        if name not in expected or name in result or path.resolve() != (candidate / name).resolve():
            raise ValueError('Loaded FFmpeg DLL is not the exact quarantined input.')
        result[name] = {'origin': 'quarantined-candidate', 'sha256': digest(path.read_bytes())}
    if set(result) != expected: raise ValueError('Actual loaded FFmpeg DLL observation is incomplete.')
    return result


def publish_attempt(run, work, previous, expected):
    # A real process failure or wrong PCM never replaces a previous complete output.
    with tempfile.TemporaryDirectory(prefix='decode-', dir=work) as name:
        pending = Path(name) / 'pending.pcm'
        result = run(pending)
        if result.returncode or not pending.is_file() or pending.read_bytes() != expected:
            raise ValueError('Authored decode failed; previous complete output retained.')
        pending.replace(previous)
        return result


def finish(root, cmake_root):
    if sys.platform != 'win32': raise ValueError('Actual Windows source build/probe required.')
    pin = policy(); root = Path(root).absolute(); no_links(root); verify_sources(root)
    makedef = makedef_diagnostics(root)
    if (makedef['status'] != 'observed-noncausal' or len(makedef['components']) != len(MAKEDEF_ROLES)):
        raise ValueError('Exact diagnostic variant observations are unavailable.')
    spec = importlib.util.spec_from_file_location('pinned_build_cmake', ROOT / 'scripts/pinned-build-cmake.py')
    cmake_helper = importlib.util.module_from_spec(spec); spec.loader.exec_module(cmake_helper)
    cmake_supplier = cmake_helper.verify(cmake_root)
    for name in PROJECT_INPUTS:
        if (ROOT / name).read_bytes() != (root / 'source-review/project-orchestration' / name).read_bytes():
            raise ValueError('Project orchestration changed after source preparation.')
    tools = json.loads((root / 'BUILD-TOOLS.json').read_text())
    after = json.loads((root / 'BUILD-TOOLS-AFTER.json').read_text())
    if tools != after: raise ValueError('Controlled build tools changed during the experiment.')
    cache = (root / 'opus-build/CMakeCache.txt').read_text(encoding='utf-8')
    for setting in ('OPUS_STATIC_RUNTIME:BOOL=ON', 'OPUS_BUILD_SHARED_LIBRARY:BOOL=OFF',
                    'OPUS_BUILD_PROGRAMS:BOOL=OFF', 'OPUS_BUILD_TESTING:BOOL=OFF'):
        if setting not in cache.splitlines(): raise ValueError('Actual Opus configuration differs from the original static recipe.')
    candidate = root / 'candidate'; before = inventory(candidate)
    if set(p.name for p in candidate.glob('*.dll')) != set(DLLS):
        raise ValueError('Unexpected dependency DLL set.')
    binary = candidate / 'game-codec-probe.exe'
    sys.path.insert(0, str(ROOT)); from backend.codec_fixture import authored_flac
    data, expected = authored_flac()
    # No developer PATH or external DLL directories in actual probe children.
    environment = {key: os.environ[key] for key in ('SystemRoot', 'WINDIR', 'TEMP', 'TMP') if key in os.environ}
    environment['PATH'] = str(Path(os.environ['SystemRoot']) / 'System32')
    report_lines = []
    with tempfile.TemporaryDirectory(prefix='authored-probe-', dir=root) as name:
        work = Path(name); source = work / 'authored.flac'; output = work / 'complete.pcm'
        source.write_bytes(data); output.write_bytes(b'previous-complete')
        def run(pending, mode='flac'):
            result = subprocess.run([str(binary), mode, str(source), str(pending)], cwd=work,
                env=environment, stdin=subprocess.DEVNULL, capture_output=True, timeout=15)
            # Raw log/module paths never enter public metadata or Actions stdout.
            return result
        valid = publish_attempt(run, work, output, expected)
        report_lines = valid.stdout.decode('utf-8').splitlines()
        for damaged in (data[:-10], data[:-1] + bytes([data[-1] ^ 1])):
            source.write_bytes(damaged)
            exits = []
            def fault_run(pending):
                result = run(pending); exits.append(result.returncode); return result
            try: publish_attempt(fault_run, work, output, expected)
            except ValueError: pass
            else: raise ValueError('Malformed FLAC was accepted.')
            if exits != [1]: raise ValueError('Malformed FLAC did not produce the authored decoder-error exit.')
            if output.read_bytes() != expected: raise ValueError('Failure changed previous output.')
        # Silence is authored PCM encoded with the newly built static Opus and
        # decoded by FFmpeg's external libopus; malformed packet also rejected.
        opus = run(work / 'opus.pcm', 'opus')
        if opus.returncode or opus.stdout.decode('utf-8').splitlines()[-1:] != ['opus-roundtrip-and-fault\tpassed']:
            raise ValueError('Actual static Opus/libopus roundtrip or fault rejection failed.')
        pcm = (work / 'opus.pcm').read_bytes()
        if len(pcm) != 1920 or any(abs(x) > 4 for x in struct.unpack('<960h', pcm)):
            raise ValueError('Opus authored silence differs from the bounded expectation.')
    configurations = [line.split('\t', 1)[1] for line in report_lines if line.startswith('configuration\t')]
    if len(configurations) != 4: raise ValueError('All four FFmpeg configurations must be observed.')
    for configuration in configurations: validate_configuration(root, configuration)
    if 'ffmpeg-version\t9.0.2' not in report_lines or 'opus-version\tlibopus 1.6.1' not in report_lines:
        raise ValueError('Actual dependency version differs from pinned source.')
    licenses = [line.split('\t', 1)[1] for line in report_lines if line.startswith('license\t')]
    if licenses != ['LGPL version 2.1 or later']:
        raise ValueError('Actual FFmpeg self-reported configuration license differs.')
    modules = sanitized_modules(report_lines, candidate)
    if inventory(candidate) != before: raise ValueError('Probe wrote into candidate inputs.')
    imports = {name: pe_imports((candidate / name).read_bytes()) for name in (*DLLS, binary.name)}
    # Preserve every generated/installed header, import/static library, config
    # and notice in runner-local quarantine. Only their inventory is public.
    correspondence = {'sources': pin['sources'], 'original_recipes': pin['original_recipes'],
        'notices': pin['notices'], 'upstream_files': inventory(root / 'upstream'),
        'diagnostic_variant': variant_receipt(pin),
        'cmake_supplier': cmake_supplier,
        'source_review_files': inventory(root / 'source-review'),
        'installed_files': inventory(root / 'out'), 'build_tools': tools,
        'ffmpeg_generated': public_generated_configuration(root),
        'opus_cache_sha256': digest((root / 'opus-build/CMakeCache.txt').read_bytes()),
        'probe_source_sha256': digest((ROOT / 'scripts/fixtures/game-codec-replay.c').read_bytes()),
        'candidate_files': before}
    identity = digest(json.dumps(correspondence, sort_keys=True, separators=(',', ':')).encode())
    report = {'schema': 'proxy-r19-ffmpeg-opus-source-replay-v1', 'status': 'passed',
        'identity': 'quarantined-source-replay-' + identity, 'source_commit': os.environ.get('GITHUB_SHA'),
        'host': pin['host'], 'source_correspondence': correspondence, 'candidate_files': before,
        'makedef_diagnostics': makedef,
        'native_imports': imports, 'actual_configurations': configurations, 'loaded_dlls': modules,
        'ffmpeg_self_reported_license': licenses[0],
        'authored_flac_pcm_sha256': digest(expected), 'authored_flac_pcm_bytes': len(expected),
        'malformed_flac': 'truncation-and-CRC-rejected;previous-output-retained',
        'authored_opus': 'static-encode-and-external-libopus-decode;malformed-packet-rejected',
        'adaptations': pin['adaptations'], 'licensing_boundary': pin['licensing_boundary'],
        'upstream_prebuilt_identity_match': 'not-claimed', 'full_game_codec_parity': 'not-tested',
        'runtime_collection_allowed': False, 'production_execution_allowed': False,
        'source_delivery_approved': False, 'native_windows_11_acceptance': 'unavailable',
        'installer': 'not-built', 'r19_complete': False}
    # Source-only review package, explicitly not approved distribution source.
    with zipfile.ZipFile(root / 'source-review.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted((root / 'source-review').rglob('*')):
            if path.is_file():
                info = zipfile.ZipInfo(path.relative_to(root / 'source-review').as_posix(), (1980, 1, 1, 0, 0, 0))
                info.external_attr = (stat.S_IFREG | 0o644) << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
    # A passing receipt exists only after the complete source archive closes.
    write_json(root / 'REPLAY-RECEIPT.json', report)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['acquire', 'prepare', 'finish', 'failure', 'preflight-failure'])
    parser.add_argument('--input-root', type=Path); parser.add_argument('--output', type=Path)
    parser.add_argument('--cmake-root', type=Path)
    parser.add_argument('--phase', choices=BUILD_PHASES)
    parser.add_argument('--exit-code', type=int); parser.add_argument('--log', type=Path)
    parser.add_argument('--log-offset', type=int)
    parser.add_argument('--include-makedef', action='store_true')
    args = parser.parse_args()
    if args.command == 'acquire': acquire(args.input_root)
    elif args.command == 'prepare': prepare(args.input_root, args.output)
    elif args.command == 'failure': failure(args.output, args.phase, args.exit_code, args.log, args.log_offset,
                                           include_makedef=args.include_makedef)
    elif args.command == 'preflight-failure': preflight_failure(args.output, read_preflight_observation(sys.stdin.buffer))
    else: finish(args.output, args.cmake_root)
