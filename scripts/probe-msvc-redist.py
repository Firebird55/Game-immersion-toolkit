"""Metadata-only census of an explicitly selected VS release-CRT layout.

Only the machine vswhere query utility is read/hashed/executed. Candidate CRT
files are never opened, hashed, loaded, copied or inspected for PE/resources.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import select
import stat
import struct
import subprocess
import sys
import time

VERSION_LIMIT = 16
FAMILY_LIMIT = 6
FILES = ('msvcp140.dll', 'msvcp140_1.dll', 'vcruntime140.dll', 'vcruntime140_1.dll')
FAMILIES = {'microsoft.vc' + str(i) + '.crt': 'vc' + str(i) + '-crt' for i in range(140, 146)}
VENDOR_FILE_BYTES = 16 * 1024 * 1024
QUERY_BYTES = 1024 * 1024
QUERY_EXE_BYTES = 16 * 1024 * 1024
INSTANCE_LIMIT = 32
OUTPUT_BYTES = 64 * 1024
DISCOVERY_SECONDS = 30
CLEANUP_SECONDS = 5
DRIVE_LIMIT = 4
DEVICE_BUFFER = 4096
MAPPING_LIMIT = 16
LOCAL_VOLUME = re.compile(r'\\Device\\HarddiskVolume(?:0|[1-9][0-9]{0,9})', re.IGNORECASE | re.ASCII)
VERSION = re.compile(r'(?:0|[1-9][0-9]{0,5})(?:\.(?:0|[1-9][0-9]{0,5})){1,3}')
VS_VERSION = re.compile(r'18(?:\.[0-9]{1,6}){3}')
DEVICES = frozenset({'CON', 'PRN', 'AUX', 'NUL', 'CONIN$', 'CONOUT$', 'CLOCK$'}
    | {prefix + number for prefix in ('COM', 'LPT') for number in '123456789¹²³'})
REASONS = frozenset({'none', 'invalid-input', 'platform-unavailable', 'linked-path', 'missing-layout',
    'nonregular-layout', 'metadata-unavailable', 'version-limit', 'family-limit', 'unknown-version-entry',
    'unknown-family-entry', 'ambiguous-entry', 'required-file-unavailable', 'member-size-limit',
    'instance-unavailable', 'instance-ambiguous', 'instance-version-mismatch', 'instance-metadata-unavailable',
    'instance-limit', 'vswhere-origin', 'vswhere-changed', 'query-unavailable', 'query-limit',
    'query-cleanup-unconfirmed', 'layout-changed', 'deadline', 'output-unavailable', 'output-limit', 'observation-failed'})
EDITIONS = {'Microsoft.VisualStudio.Product.Enterprise': 'enterprise',
    'Microsoft.VisualStudio.Product.Professional': 'professional',
    'Microsoft.VisualStudio.Product.Community': 'community', 'Microsoft.VisualStudio.Product.BuildTools': 'build-tools'}


class CensusError(ValueError):
    def __init__(self, code):
        self.code = code if type(code) is str and code in REASONS else 'observation-failed'
        super().__init__('MSVC redist census unavailable: ' + self.code + '.')


class Budget:
    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.deadline = clock() + DISCOVERY_SECONDS
        self.drive_mappings = {}  # Private current mappings, never receipt data.

    def remaining(self):
        remaining = self.deadline - self.clock()
        if remaining <= 0:
            raise CensusError('deadline')
        return remaining


def canonical_path(value):
    value = os.fspath(value)
    if (type(value) is not str or not 1 <= len(value) <= 32767
            or any(ord(c) < 32 or ord(c) == 127 or c in ',;' for c in value)):
        raise CensusError('invalid-input')
    spelling = value.replace('\\', '/')
    # Validate the raw spelling before Path can discard separators or dots.
    # A colon is permitted only in the leading drive designator, never an ADS.
    components = spelling[3:].split('/') if re.match(r'^[A-Za-z]:/', spelling) else spelling.split('/')
    if (any(c in '<>:"|?*' for part in components for c in part)
            or any(part.endswith((' ', '.')) or part.split('.', 1)[0].rstrip(' ').upper() in DEVICES
                for part in components)):
        raise CensusError('invalid-input')
    path = Path(value)
    if (not path.is_absolute() or path.parent == path or '//' in spelling or spelling.endswith('/')
            or any(part in {'.', '..'} for part in spelling.split('/'))):
        raise CensusError('invalid-input')
    return path


def parse_drive_mapping(raw):
    if type(raw) is not str or not 2 < len(raw) <= DEVICE_BUFFER or not raw.endswith('\0\0'):
        raise CensusError('metadata-unavailable')
    mappings = raw[:-2].split('\0')
    if (not 1 <= len(mappings) <= MAPPING_LIMIT or any(not value for value in mappings)
            or not LOCAL_VOLUME.fullmatch(mappings[0])):
        raise CensusError('metadata-unavailable')
    # The API defines only the first mapping as current. Never follow or expose
    # historical entries, DOS aliases, network roots or native directory suffixes.
    return mappings[0].lower()


def windows_drive_mapping(drive, budget):
    if os.name != 'nt':
        return None
    if type(drive) is not str or not re.fullmatch('[A-Za-z]:', drive):
        raise CensusError('invalid-input')
    import ctypes
    from ctypes import wintypes
    function = ctypes.WinDLL('kernel32', use_last_error=True).QueryDosDeviceW
    function.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    function.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(DEVICE_BUFFER)
    budget.remaining()
    count = function(drive, buffer, len(buffer))
    budget.remaining()
    if type(count) is not int or not 0 < count <= len(buffer):
        raise CensusError('metadata-unavailable')
    return parse_drive_mapping(buffer[:count])


def checked_drive(drive, budget):
    if not re.fullmatch('[A-Za-z]:', drive):
        raise CensusError('invalid-input')
    drive = drive.upper()
    if drive not in budget.drive_mappings and len(budget.drive_mappings) >= DRIVE_LIMIT:
        raise CensusError('metadata-unavailable')
    current = windows_drive_mapping(drive, budget)
    if current is None and os.name != 'nt' and not budget.drive_mappings:
        return None
    if type(current) is not str or not LOCAL_VOLUME.fullmatch(current):
        raise CensusError('metadata-unavailable')
    current = current.lower()
    if drive in budget.drive_mappings and budget.drive_mappings[drive] != current:
        raise CensusError('layout-changed')
    budget.drive_mappings[drive] = current
    return current


def path_identity(path, budget):
    if not path.drive:
        if os.name == 'nt':
            raise CensusError('invalid-input')
        return ('host', *path.parts)
    volume = checked_drive(path.drive, budget)
    if volume is None:  # Only the ordinary non-Windows source fixture route.
        return ('host', *path.parts)
    return ('volume', volume, *(part.lower() for part in path.parts[1:]))


def path_within(path, root, budget):
    child, parent = path_identity(path, budget), path_identity(root, budget)
    return child[:len(parent)] == parent


def recheck_drives(budget):
    for drive in tuple(budget.drive_mappings):
        checked_drive(drive, budget)


def windows_long_spelling(path, budget):
    if os.name != 'nt':
        return None
    import ctypes
    from ctypes import wintypes
    function = ctypes.WinDLL('kernel32', use_last_error=True).GetLongPathNameW
    function.argtypes = (wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD)
    function.restype = wintypes.DWORD
    buffer = ctypes.create_unicode_buffer(32768)
    budget.remaining()
    count = function(str(path), buffer, len(buffer))
    budget.remaining()
    if not 0 < count < len(buffer):
        raise CensusError('metadata-unavailable')
    return buffer.value


def require_long_spelling(path, budget):
    # No tilde heuristic: short names can have other spellings. This name-only
    # query follows the completed raw ancestor guard, never precedes it.
    spelling = windows_long_spelling(path, budget)
    if spelling is not None:
        if type(spelling) is not str or not 0 < len(spelling) <= 32767 or '\0' in spelling:
            raise CensusError('metadata-unavailable')
        if spelling.replace('\\', '/').lower() != str(path).replace('\\', '/').lower():
            raise CensusError('invalid-input')


def info(path, budget, *, missing=False):
    path_identity(path, budget)  # Refuse a mapped-directory drive before lstat.
    # Root first: even descendant lstat/stat can traverse an ancestor link.
    previous = None
    for item in (*reversed(path.parents), path):
        budget.remaining()
        try:
            value = item.lstat()
        except FileNotFoundError:
            if missing:
                if previous is not None:
                    require_long_spelling(previous, budget)
                return None
            raise CensusError('missing-layout') from None
        except OSError:
            raise CensusError('metadata-unavailable') from None
        if stat.S_ISLNK(value.st_mode) or getattr(value, 'st_file_attributes', 0) & 0x400:
            raise CensusError('linked-path')
        if item != path and not stat.S_ISDIR(value.st_mode):
            raise CensusError('nonregular-layout')
        previous = item
    require_long_spelling(path, budget)
    return value


def directory(path, budget):
    value = info(path, budget)
    if not stat.S_ISDIR(value.st_mode):
        raise CensusError('nonregular-layout')
    return value


def fingerprint(value):
    # Private metadata comparison only; never serialize or hash this tuple.
    return tuple(getattr(value, key, None) for key in
        ('st_dev', 'st_ino', 'st_mode', 'st_size', 'st_mtime_ns', 'st_ctime_ns'))


def names(path, limit, reason, budget):
    value = directory(path, budget)
    result = []
    try:
        recheck_drives(budget)
        with os.scandir(path) as entries:
            for entry in entries:
                budget.remaining()
                if len(result) == limit:
                    raise CensusError(reason)
                result.append(entry.name)  # No DirEntry metadata calls.
    except OSError:
        raise CensusError('metadata-unavailable') from None
    if len({name.casefold() for name in result}) != len(result):
        raise CensusError('ambiguous-entry')
    return result, fingerprint(value)


def census(selected_root, budget):
    root = selected_root / 'VC/Redist/MSVC'
    versions, root_key = names(root, VERSION_LIMIT, 'version-limit', budget)
    if not versions:
        raise CensusError('missing-layout')
    if any(not VERSION.fullmatch(name) for name in versions):
        raise CensusError('unknown-version-entry')
    rows, private = [], {'redist-root': root_key}
    for version in sorted(versions):
        version_root = root / version
        private[version] = fingerprint(directory(version_root, budget))
        family_names, key = names(version_root / 'x64', FAMILY_LIMIT, 'family-limit', budget)
        private[version + '/x64'] = key
        if not family_names:
            raise CensusError('missing-layout')
        if any(name.casefold() not in FAMILIES for name in family_names):
            raise CensusError('unknown-family-entry')
        families = []
        for name in sorted(family_names, key=str.casefold):
            family_root = version_root / 'x64' / name
            private[version + '/' + name] = fingerprint(directory(family_root, budget))
            members = {}
            for member in FILES:
                value = info(family_root / member, budget, missing=True)
                if value is None or not stat.S_ISREG(value.st_mode):
                    raise CensusError('required-file-unavailable')
                if not 0 < value.st_size <= VENDOR_FILE_BYTES:
                    raise CensusError('member-size-limit')
                private[version + '/' + name + '/' + member] = fingerprint(value)
                members[member] = {'presence': 'regular-file-present', 'bytes': value.st_size}
            families.append({'role': FAMILIES[name.casefold()], 'files': members})
        rows.append({'version': version, 'families': families})
    return rows, private


def known_program_files_x86():
    if os.name != 'nt' or struct.calcsize('P') != 8:
        raise CensusError('platform-unavailable')
    import ctypes
    from ctypes import wintypes
    import uuid
    class Guid(ctypes.Structure):
        _fields_ = [('a', wintypes.DWORD), ('b', wintypes.WORD), ('c', wintypes.WORD), ('d', ctypes.c_ubyte * 8)]
    guid = Guid.from_buffer_copy(uuid.UUID('7c5a40ef-a0fb-4bfc-874a-c0f2e0b9fa8e').bytes_le)
    shell = ctypes.WinDLL('shell32.dll', use_last_error=True)
    ole = ctypes.WinDLL('ole32.dll', use_last_error=True)
    shell.SHGetKnownFolderPath.argtypes = [ctypes.POINTER(Guid), wintypes.DWORD, wintypes.HANDLE, ctypes.POINTER(ctypes.c_void_p)]
    shell.SHGetKnownFolderPath.restype = ctypes.c_long
    ole.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole.CoTaskMemFree.restype = None
    pointer = ctypes.c_void_p()
    try:
        # Read registered identity without Windows doing an existence walk
        # before our own raw root-first checks. Never request folder creation.
        if shell.SHGetKnownFolderPath(ctypes.byref(guid), 0x4000, None, ctypes.byref(pointer)) != 0 or not pointer.value:
            raise CensusError('vswhere-origin')
        return canonical_path(ctypes.wstring_at(pointer))
    finally:
        if pointer.value:
            ole.CoTaskMemFree(pointer)


def utility_identity(path, budget):
    value = info(path, budget)
    if not stat.S_ISREG(value.st_mode) or not 0 < value.st_size <= QUERY_EXE_BYTES:
        raise CensusError('vswhere-origin')
    checksum, count = hashlib.sha256(), 0
    recheck_drives(budget)
    with path.open('rb') as stream:
        while block := stream.read(min(65536, QUERY_EXE_BYTES + 1 - count)):
            budget.remaining(); count += len(block)
            if count > QUERY_EXE_BYTES:
                raise CensusError('vswhere-changed')
            checksum.update(block)
    after = info(path, budget)
    if fingerprint(after) != fingerprint(value) or count != value.st_size:
        raise CensusError('vswhere-changed')
    return {'bytes': count, 'sha256': checksum.hexdigest()}


def pipe_available(stream):
    """Windows anonymous-pipe availability; never perform a blocking read."""
    import ctypes
    from ctypes import wintypes
    import msvcrt
    function = ctypes.WinDLL('kernel32.dll', use_last_error=True).PeekNamedPipe
    function.argtypes = [wintypes.HANDLE, wintypes.LPVOID, wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
    function.restype = wintypes.BOOL
    available = wintypes.DWORD()
    if not function(wintypes.HANDLE(msvcrt.get_osfhandle(stream.fileno())), None, 0, None, ctypes.byref(available), None):
        if ctypes.get_last_error() == 109:  # ERROR_BROKEN_PIPE, no remaining writer.
            return None
        raise CensusError('query-unavailable')
    return available.value


def bounded_capture(command, budget):
    process = None
    try:
        recheck_drives(budget)
        process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, bufsize=0, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        result = bytearray()
        while True:
            remaining = budget.remaining()
            if os.name == 'nt':
                available = pipe_available(process.stdout)
                if available is None or available == 0 and process.poll() is not None:
                    break
                if not available:
                    time.sleep(min(.02, remaining)); continue
                count = min(available, 16384, QUERY_BYTES + 1 - len(result))
            else:
                if not select.select([process.stdout], [], [], min(.02, remaining))[0]:
                    continue
                count = min(16384, QUERY_BYTES + 1 - len(result))
            block = os.read(process.stdout.fileno(), count)
            if not block:
                break
            result.extend(block)
            if len(result) > QUERY_BYTES:
                raise CensusError('query-limit')
        if process.wait(timeout=budget.remaining()) != 0:
            raise CensusError('query-unavailable')
        return bytes(result)
    except subprocess.TimeoutExpired:
        raise CensusError('deadline') from None
    finally:
        if process is not None:
            try:
                if process.poll() is None:
                    process.kill()
                process.wait(timeout=CLEANUP_SECONDS)
            except (OSError, subprocess.TimeoutExpired):
                raise CensusError('query-cleanup-unconfirmed') from None
            finally:
                if process.stdout is not None:
                    process.stdout.close()
                handle = getattr(process, '_handle', None)
                if os.name == 'nt' and handle is not None:
                    handle.Close()


def query_instance(vswhere, selected_root, version, budget):
    raw = bounded_capture([str(vswhere), '-all', '-prerelease', '-products', '*', '-format', 'json', '-utf8', '-nologo'], budget)
    def unique(items):
        value = {}
        for key, item in items:
            if key in value: raise CensusError('query-unavailable')
            value[key] = item
        return value
    try:
        values = json.loads(raw.decode('utf-8-sig'), object_pairs_hook=unique,
            parse_constant=lambda _value: (_ for _ in ()).throw(CensusError('query-unavailable')))
    except (ValueError, UnicodeError, RecursionError):
        raise CensusError('query-unavailable') from None
    if type(values) is not list or len(values) > INSTANCE_LIMIT:
        raise CensusError('instance-limit')
    matched = []
    for value in values:
        if type(value) is not dict:
            raise CensusError('instance-unavailable')
        path = canonical_path(value.get('installationPath', ''))
        if os.path.normcase(str(path)) == os.path.normcase(str(selected_root)):
            matched.append(value)
    if len(matched) != 1:
        raise CensusError('instance-ambiguous' if matched else 'instance-unavailable')
    value = matched[0]
    if value.get('installationVersion') != version:
        raise CensusError('instance-version-mismatch')
    release = value.get('isPrerelease')
    edition = EDITIONS.get(value.get('productId'), 'unknown')
    if type(release) is not bool or edition == 'unknown' or value.get('isComplete') is not True or value.get('isLaunchable') is not True:
        raise CensusError('instance-metadata-unavailable')
    return {'version': version, 'edition': edition, 'release_state': 'prerelease' if release else 'release'}


def projected_instance(value, version):
    if (type(value) is not dict or set(value) != {'version', 'edition', 'release_state'}
            or type(value['version']) is not str or value['version'] != version or type(value['edition']) is not str
            or value['edition'] not in set(EDITIONS.values()) or type(value['release_state']) is not str
            or value['release_state'] not in {'release', 'prerelease'}):
        raise CensusError('instance-metadata-unavailable')
    return {key: value[key] for key in ('version', 'edition', 'release_state')}


def serialized(report):
    return (json.dumps(report, separators=(',', ':')) + '\n').encode('utf-8')


def observe(selected_vs_root, selected_vs_version, vswhere, source_commit, observation_id, *,
            program_files_provider=known_program_files_x86, query=query_instance, clock=time.monotonic, budget=None):
    report = {'schema': 'proxy-r19-msvc-redist-census-v1', 'status': 'unavailable', 'reason': 'invalid-input',
        'source_commit_label': None, 'source_binding': 'unverified-caller-label', 'observation_id': None,
        'observation_id_authority': 'binding-only', 'selected_instance': {'version': None, 'edition': 'unknown', 'release_state': 'unknown'},
        'query_utility': None, 'requested_architecture': 'x64', 'selection': 'none', 'versions': [],
        'version_count': 0, 'family_count': 0, 'file_count': 0, 'metadata_snapshot_stable': False,
        'vendor_file_content_read': False, 'vendor_file_hashes_observed': False, 'vendor_file_versions_observed': False,
        'vendor_signatures_observed': False, 'entitlement_probe': 'not-performed', 'rights_review': 'pending-owner-and-exact-source',
        'license_eligibility': 'unverified', 'redistribution_approved': False, 'source_delivery_approved': False,
        'runtime_collection_allowed': False, 'production_execution_allowed': False, 'production_activation': False,
        'native_closure': 'unverified', 'native_windows_11_acceptance': 'unavailable', 'r19_complete': False, 'installer': 'not-built'}
    try:
        if type(source_commit) is not str or not re.fullmatch('[0-9a-f]{40}', source_commit):
            raise CensusError('invalid-input')
        if type(observation_id) is not str or not re.fullmatch('[A-Za-z0-9][A-Za-z0-9._-]{0,79}', observation_id):
            raise CensusError('invalid-input')
        report.update(source_commit_label=source_commit, observation_id=observation_id)
        if type(selected_vs_version) is not str or not VS_VERSION.fullmatch(selected_vs_version):
            raise CensusError('invalid-input')
        budget = Budget(clock) if budget is None else budget
        root, utility = canonical_path(selected_vs_root), canonical_path(vswhere)
        machine_root = canonical_path(program_files_provider())
        expected = machine_root / 'Microsoft Visual Studio/Installer/vswhere.exe'
        if os.path.normcase(str(utility)) != os.path.normcase(str(expected)):
            raise CensusError('vswhere-origin')
        directory(root, budget)
        initial = utility_identity(utility, budget)
        recheck_drives(budget)
        instance = projected_instance(query(utility, root, selected_vs_version, budget), selected_vs_version)
        if utility_identity(utility, budget) != initial:
            raise CensusError('vswhere-changed')
        report.update(selected_instance=instance, query_utility=initial)
        rows, private = census(root, budget)
        again, after = census(root, budget)
        if rows != again or private != after:
            raise CensusError('layout-changed')
        recheck_drives(budget)
        if (canonical_path(program_files_provider()) != machine_root or utility_identity(utility, budget) != initial
                or projected_instance(query(utility, root, selected_vs_version, budget), selected_vs_version) != instance
                or utility_identity(utility, budget) != initial):
            raise CensusError('vswhere-changed')
        report.update(status='observed-not-approved', reason='none', versions=rows, version_count=len(rows),
            family_count=sum(len(row['families']) for row in rows),
            file_count=sum(len(family['files']) for row in rows for family in row['families']), metadata_snapshot_stable=True)
        if len(serialized(report)) > OUTPUT_BYTES:
            raise CensusError('output-limit')
    except Exception as error:
        code = error.__dict__.get('code') if type(error) is CensusError else None
        code = code if type(code) is str and code in REASONS else 'observation-failed'
        report.update(status='unavailable', reason=code, versions=[], version_count=0, family_count=0, file_count=0, metadata_snapshot_stable=False)
    return report


def report_target(path, *, forbidden_roots=(), budget=None):
    path = canonical_path(path)
    budget = Budget() if budget is None else budget
    # Even an unavailable census cannot use a short-name forbidden root to
    # authorize a sink under that installation's long spelling.
    forbidden_roots = tuple(canonical_path(root) for root in forbidden_roots)
    for root in forbidden_roots:
        info(root, budget, missing=True)
    if any(path_within(path, root, budget) for root in forbidden_roots):
        raise CensusError('output-unavailable')
    directory(path.parent, budget)
    if info(path, budget, missing=True) is not None:
        raise CensusError('output-unavailable')
    return path


def write_report(path, report, *, forbidden_roots=(), budget=None):
    budget = Budget() if budget is None else budget
    path = report_target(path, forbidden_roots=forbidden_roots, budget=budget)
    raw = serialized(report)
    if len(raw) > OUTPUT_BYTES:
        raise CensusError('output-limit')
    recheck_drives(budget)
    with path.open('xb') as stream:
        stream.write(raw)


class SafeParser(argparse.ArgumentParser):
    def error(self, _message):
        raise CensusError('invalid-input')


def main(arguments=None):
    parser = SafeParser()
    parser.add_argument('command', choices=['observe'])
    for name in ('selected-vs-root', 'selected-vs-version', 'vswhere', 'source-commit', 'observation-id', 'output'):
        parser.add_argument('--' + name, required=True)
    try:
        args = parser.parse_args(arguments)
        forbidden_roots = (canonical_path(args.selected_vs_root), canonical_path(args.vswhere).parent)
        budget = Budget()
        report_target(args.output, forbidden_roots=forbidden_roots, budget=budget)
        report = observe(args.selected_vs_root, args.selected_vs_version, args.vswhere, args.source_commit, args.observation_id, budget=budget)
        write_report(args.output, report, forbidden_roots=forbidden_roots, budget=budget)
        print('MSVC redist census: ' + report['status'] + ' (' + report['reason'] + ').')
        return 0 if report['status'] == 'observed-not-approved' else 2
    except Exception:
        print('MSVC redist census unavailable; no source admitted.', file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
