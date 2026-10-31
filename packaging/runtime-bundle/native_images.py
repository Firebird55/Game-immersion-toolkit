"""Original bounded PE/CLR inspection from Microsoft format documentation.

No parser code is copied from the separately licensed codec build recipes.
This reads declared image headers, never loads a DLL or resolves an import.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import struct

MAX_IMAGE_BYTES = 512 * 1024 * 1024
MAX_INVENTORY_BYTES = 16 * 1024 * 1024
MAX_NATIVE_FILES = 20000
MAX_TOTAL_NATIVE_BYTES = 8 * 1024 * 1024 * 1024
MAX_IMPORTS = 512
MACHINES = {0x14c: 'i386', 0x8664: 'amd64', 0xaa64: 'arm64'}
CODES = frozenset({'invalid-inventory', 'inventory-changed', 'unsafe-image-path', 'image-changed',
    'image-limit', 'malformed-pe', 'ambiguous-rva', 'invalid-import', 'invalid-clr', 'unsupported-architecture'})


class NativeImageError(ValueError):
    def __init__(self, code):
        self.code = code if code in CODES else 'malformed-pe'
        super().__init__('Native image review refused: ' + self.code + '.')


def _require(condition, code='malformed-pe'):
    if not condition:
        raise NativeImageError(code)


class _Image:
    def __init__(self, data):
        _require(isinstance(data, bytes) and 64 <= len(data) <= MAX_IMAGE_BYTES)
        self.data = data
        _require(data[:2] == b'MZ')
        pe = self.number('<I', 60)
        _require(pe >= 64 and self.take(pe, 4) == b'PE\0\0')
        self.machine = self.number('<H', pe + 4)
        count, optional_size = self.number('<H', pe + 6), self.number('<H', pe + 20)
        self.is_dll = bool(self.number('<H', pe + 22) & 0x2000)
        _require(self.number('<H', pe + 22) & 2)  # IMAGE_FILE_EXECUTABLE_IMAGE.
        _require(1 <= count <= 96 and 96 <= optional_size <= 4096)
        self.optional = pe + 24
        self.take(self.optional, optional_size)
        magic = self.number('<H', self.optional)
        _require(magic in (0x10b, 0x20b))
        self.plus = magic == 0x20b
        self.width = 8 if self.plus else 4
        _require(self.machine in MACHINES, 'unsupported-architecture')
        _require((self.machine == 0x14c) != self.plus)
        self.base = self.number('<Q' if self.plus else '<I', self.optional + (24 if self.plus else 28))
        self.image_size = self.number('<I', self.optional + 56)
        self.headers = self.number('<I', self.optional + 60)
        directory_start = 112 if self.plus else 96
        _require(optional_size >= directory_start)
        directory_count = self.number('<I', self.optional + directory_start - 4)
        _require(directory_count <= 16 and directory_start + 8 * directory_count <= optional_size)
        self.directories = [self.numbers('<II', self.optional + directory_start + i * 8)
                            for i in range(directory_count)]
        section_start = self.optional + optional_size
        _require(section_start + 40 * count <= self.headers <= len(data) and self.headers <= self.image_size)
        self.sections = []
        for i in range(count):
            offset = section_start + i * 40
            virtual_size, address, raw_size, raw_start = self.numbers('<IIII', offset + 8)
            span = max(virtual_size, raw_size)
            _require(address >= self.headers and address + span <= self.image_size
                and address + span <= 0x100000000)
            if raw_size:
                _require(raw_start >= self.headers)
                self.bounds(raw_start, raw_size)
            self.sections.append((address, span, raw_start, raw_size, self.number('<I', offset + 36)))
        for i, first in enumerate(self.sections):
            for second in self.sections[i + 1:]:
                _require(not self.overlap(first[0], first[1], second[0], second[1]), 'ambiguous-rva')
                _require(not self.overlap(first[2], first[3], second[2], second[3]), 'ambiguous-rva')
        entry = self.number('<I', self.optional + 16)
        if entry:
            self.locate(entry, 1)

    @staticmethod
    def overlap(start, length, other, size):
        return length and size and max(start, other) < min(start + length, other + size)

    def bounds(self, offset, size):
        _require(0 <= offset <= len(self.data) and 0 <= size <= len(self.data) - offset)

    def take(self, offset, size):
        self.bounds(offset, size)
        return self.data[offset:offset + size]

    def numbers(self, shape, offset):
        self.take(offset, struct.calcsize(shape))
        return struct.unpack_from(shape, self.data, offset)

    def number(self, shape, offset):
        return self.numbers(shape, offset)[0]

    def locate(self, rva, size, *, backed=True):
        _require(0 < rva <= 0xffffffff and 0 < size <= 0x100000000 - rva)
        candidates = []
        if rva < self.headers and rva + size <= self.headers:
            candidates.append((rva, self.headers))
        for address, span, raw_start, raw_size, _flags in self.sections:
            delta = rva - address
            if 0 <= delta and delta + size <= span:
                if not backed or delta + size <= raw_size:
                    candidates.append((raw_start + delta, raw_start + raw_size))
        _require(len(candidates) == 1, 'ambiguous-rva' if len(candidates) > 1 else 'malformed-pe')
        offset, end = candidates[0]
        if backed:
            self.bounds(offset, size)
        return offset, end

    def directory(self, index, maximum):
        address, size = self.directories[index] if index < len(self.directories) else (0, 0)
        _require(bool(address) == bool(size) and size <= maximum)
        if address:
            self.locate(address, size)
        return address, size

    def module_name(self, rva):
        start, end = self.locate(rva, 1)
        end = self.data.find(b'\0', start, min(end, start + 256))
        _require(end > start, 'invalid-import')
        try:
            name = self.take(start, end - start).decode('ascii', errors='strict')
        except UnicodeDecodeError:
            raise NativeImageError('invalid-import') from None
        _require(re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.+@-]{0,254}', name)
            and not name.endswith('.') and name.casefold().split('.')[0] not in
            {'con', 'prn', 'aux', 'nul', *(f'com{i}' for i in range(1, 10)), *(f'lpt{i}' for i in range(1, 10))}, 'invalid-import')
        return name

    def imports(self, *, delayed=False):
        stride = 32 if delayed else 20
        address, size = self.directory(13 if delayed else 1, 4 * 1024 * 1024)
        if not address:
            return []
        _require(size >= stride, 'invalid-import')
        result, folded = [], set()
        for i in range(min(size // stride, MAX_IMPORTS + 1)):
            position, _end = self.locate(address + i * stride, stride)
            fields = self.numbers('<' + 'I' * (stride // 4), position)
            if not any(fields):
                return sorted(result, key=lambda name: (name.casefold(), name))
            _require(len(result) < MAX_IMPORTS, 'invalid-import')
            if delayed:
                _require(fields[0] in (0, 1), 'invalid-import')
                pointers = [value - (0 if fields[0] else self.base) if value else 0 for value in fields[1:7]]
                name, handle, iat, names, bound, unload = pointers
                _require(name > 0 and iat > 0 and names > 0, 'invalid-import')
                for pointer in (handle, iat):
                    if pointer:
                        self.locate(pointer, self.width, backed=False)
                for pointer in (names, bound, unload):
                    if pointer:
                        self.locate(pointer, self.width)
            else:
                names, _stamp, _forwarder, name, iat = fields
                _require(name > 0 and iat > 0, 'invalid-import')
                self.locate(iat, self.width, backed=False)
                if names:
                    self.locate(names, self.width)
            text = self.module_name(name)
            _require(text.casefold() not in folded, 'invalid-import')
            folded.add(text.casefold()); result.append(text)
        raise NativeImageError('invalid-import')

    def clr(self):
        address, size = self.directory(14, 4096)
        if not address:
            return None
        start, _end = self.locate(address, size)
        _require(size >= 72 and self.number('<I', start) == 72, 'invalid-clr')
        major, minor = self.numbers('<HH', start + 4)
        _require(major > 0, 'invalid-clr')
        flags, entry = self.numbers('<II', start + 16)
        _require(flags & ~0x3001f == 0, 'invalid-clr')
        required, preferred, il_only, native_entry = (bool(flags & bit) for bit in (2, 0x20000, 1, 0x10))
        _require(not preferred or required, 'invalid-clr')
        _require(not (il_only and native_entry), 'invalid-clr')
        # 32BITREQUIRED/PREFERRED are a two-bit field, not independent flags.
        _require(not (required and (self.plus or self.machine != 0x14c)), 'invalid-clr')
        _require(not preferred or il_only, 'invalid-clr')
        regions = {}
        for offset in (8, 24, 32, 40, 48, 56, 64):
            rva, length = self.numbers('<II', start + offset)
            _require(bool(rva) == bool(length), 'invalid-clr')
            if rva:
                self.locate(rva, length)
            regions[offset] = (rva, length)
        metadata, length = regions[8]
        _require(metadata and 20 <= length <= 32 * 1024 * 1024, 'invalid-clr')
        metadata_start, _end = self.locate(metadata, length)
        _require(self.take(metadata_start, 4) == b'BSJB', 'invalid-clr')
        version_length = self.number('<I', metadata_start + 12)
        _require(1 <= version_length <= 256 and 16 + version_length + 4 <= length, 'invalid-clr')
        _require(b'\0' in self.take(metadata_start + 16, version_length), 'invalid-clr')
        if native_entry:
            _require(entry > 0, 'invalid-clr')
            self.locate(entry, 1)
            entry_kind = 'native-rva'
        elif entry:
            _require(entry >> 24 in (6, 38) and entry & 0xffffff, 'invalid-clr')
            entry_kind = 'managed-method' if entry >> 24 == 6 else 'managed-file'
        else:
            entry_kind = 'none'
        native_hint = native_entry or not il_only or any(regions[offset][0] for offset in (40, 48, 56, 64))
        _require(not preferred or not native_hint, 'invalid-clr')
        return {'runtime_header_version': [major, minor], 'flags': flags, 'il_only': il_only,
            'bit32_required': required and not preferred, 'bit32_preferred': preferred,
            'entry_point': entry_kind, 'managed_native_header': bool(regions[64][0]), 'native_hints': native_hint}


def inspect_pe(data: bytes) -> dict:
    """Observe supported image headers; this is not a Windows/CLR loader."""
    try:
        image = _Image(data)
        clr = image.clr()
        machine = MACHINES[image.machine]
        architecture = {'amd64': 'x64', 'i386': 'x86', 'arm64': 'arm64'}[machine]
        implementation = 'native' if clr is None else 'managed-native' if clr['native_hints'] else 'managed-il'
        if implementation == 'managed-il' and machine == 'i386' and not clr['bit32_required']:
            architecture = 'anycpu-32bit-preferred' if clr['bit32_preferred'] else 'anycpu'
        return {'machine': machine, 'machine_code': image.machine, 'format': 'PE32+' if image.plus else 'PE32',
            'image_kind': 'dll' if image.is_dll else 'executable', 'implementation': implementation,
            'architecture': architecture, 'clr': clr, 'imports': image.imports(), 'delay_imports': image.imports(delayed=True)}
    except NativeImageError:
        raise
    except Exception:
        raise NativeImageError('malformed-pe') from None


def _unique_json(pairs):
    result = {}
    for name, value in pairs:
        _require(name not in result, 'invalid-inventory')
        result[name] = value
    return result


def _inventory(value):
    from native_ownership import _relative, _sha
    keys = {'schema', 'source_commit', 'profile', 'build_id', 'files', 'directories', 'file_count', 'bytes',
        'components', 'helpers', 'codecs', 'native_input_ownership', 'gates', 'r19_complete',
        'native_windows_11_acceptance', 'installer'}
    _require(isinstance(value, dict) and set(value) == keys, 'invalid-inventory')
    _require(value['schema'] == 'proxy-r19-runtime-inventory-v1' and value['profile'] == 'runtime-experiment'
        and isinstance(value['source_commit'], str) and re.fullmatch(r'[a-f0-9]{40}', value['source_commit'])
        and isinstance(value['build_id'], str) and re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,79}', value['build_id'])
        and value['r19_complete'] is False and value['native_windows_11_acceptance'] == 'unavailable'
        and value['installer'] == 'not-built', 'invalid-inventory')
    _require(isinstance(value['files'], list) and 1 <= len(value['files']) <= 100000
        and isinstance(value['directories'], list) and len(value['directories']) <= 100000
        and type(value['file_count']) is int and value['file_count'] == len(value['files'])
        and type(value['bytes']) is int and isinstance(value['components'], list)
        and all(isinstance(value[key], dict) for key in ('helpers', 'codecs', 'native_input_ownership', 'gates')), 'invalid-inventory')
    names, directories, total = set(), set(), 0
    for directory in value['directories']:
        directory = _relative(directory)
        _require(directory != '.' and directory.casefold() not in names and '\x7f' not in directory, 'invalid-inventory')
        names.add(directory.casefold()); directories.add(directory)
    for entry in value['files']:
        _require(isinstance(entry, dict) and set(entry) == {'path', 'bytes', 'sha256'}, 'invalid-inventory')
        name = _relative(entry['path']); _sha(entry['sha256'])
        _require(name != '.' and name.casefold() not in names and '\x7f' not in name and type(entry['bytes']) is int
            and 0 <= entry['bytes'] <= 8 * 1024 * 1024 * 1024, 'invalid-inventory')
        names.add(name.casefold()); total += entry['bytes']
    _require(value['bytes'] == total and total <= 64 * 1024 * 1024 * 1024, 'invalid-inventory')
    for name in [*directories, *(item['path'] for item in value['files'])]:
        _require(all(parent.as_posix() in directories for parent in Path(name).parents if parent != Path('.')), 'invalid-inventory')


def review_native_images(inventory: dict, inventory_path: Path, application_root: Path) -> dict:
    """Consume the existing final inventory only; do not walk or change outputs.

    The caller owns candidate trust and writes a sidecar only after this returns.
    AnyCPU describes CLR headers, not P/Invoke or dynamic-load compatibility.
    """
    from record_runtime import native_path, native_file_identity
    try:
        inventory_path = native_path(inventory_path)
        _require(inventory_path.stat().st_size <= MAX_INVENTORY_BYTES, 'invalid-inventory')
        identity = native_file_identity(inventory_path)
        _require(identity['bytes'] <= MAX_INVENTORY_BYTES, 'invalid-inventory')
        with inventory_path.open('rb') as stream:
            raw = stream.read(MAX_INVENTORY_BYTES + 1)
        def invalid_constant(_value):
            raise NativeImageError('invalid-inventory')
        observed = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique_json, parse_constant=invalid_constant)
        _require(observed == inventory and hashlib.sha256(raw).hexdigest() == identity['sha256']
            and len(raw) == identity['bytes'], 'inventory-changed')
        _inventory(observed)  # Validate ALL paths and entries before selecting one image.
        root = native_path(application_root, directory=True)
        selected = [item for item in observed['files'] if Path(item['path']).suffix.lower() in {'.exe', '.dll', '.pyd'}]
        _require(2 <= len(selected) <= MAX_NATIVE_FILES, 'invalid-inventory')
        _require(sum(item['bytes'] for item in selected) <= MAX_TOTAL_NATIVE_BYTES, 'image-limit')
        _require({'ProxyTranscriptRuntime.exe', 'asr/ProxyTranscriptAsr.exe'} <= {item['path'] for item in selected}, 'invalid-inventory')
        records = []
        for entry in sorted(selected, key=lambda item: item['path']):
            _require(64 <= entry['bytes'] <= MAX_IMAGE_BYTES, 'image-limit')
            try:
                path = native_path(root / entry['path'])
            except Exception:
                raise NativeImageError('unsafe-image-path') from None
            expected = {key: entry[key] for key in ('bytes', 'sha256')}
            _require(native_file_identity(path) == expected, 'image-changed')
            with path.open('rb') as stream:
                data = stream.read(entry['bytes'] + 1)
            _require(len(data) == entry['bytes'] and hashlib.sha256(data).hexdigest() == entry['sha256'], 'image-changed')
            image = inspect_pe(data)
            _require(image['architecture'] in {'x64', 'anycpu'}, 'unsupported-architecture')
            if entry['path'] in {'ProxyTranscriptRuntime.exe', 'asr/ProxyTranscriptAsr.exe'}:
                _require(image['implementation'] == 'native' and image['architecture'] == 'x64'
                    and image['image_kind'] == 'executable', 'unsupported-architecture')
            _require(native_file_identity(path) == expected, 'image-changed')
            records.append({**entry, 'tree': 'asr' if entry['path'].startswith('asr/') else 'main', **image})
            del data
        _require(native_file_identity(inventory_path) == identity, 'inventory-changed')
        return {'schema': 'proxy-r19-native-images-v1', 'status': 'observed-not-approved',
            **{key: observed[key] for key in ('source_commit', 'build_id', 'profile')},
            'inventory': identity, 'files': records, 'file_count': len(records),
            'architecture_policy': 'x64-native-or-declared-il-only-anycpu',
            'dynamic_loading': 'unverified', 'pinvoke_compatibility': 'unverified', 'native_closure': 'unverified',
            'rights_review': 'pending-exact-output', 'source_delivery_approved': False,
            'production_execution_allowed': False, 'native_windows_11_acceptance': 'unavailable',
            'r19_complete': False, 'installer': 'not-built'}
    except NativeImageError:
        raise
    except Exception:
        raise NativeImageError('invalid-inventory') from None
