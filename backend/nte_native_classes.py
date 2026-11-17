"""Read original Unreal native class descriptors without loading client code.

Class names come from registration records. An exact StaticClass pointer joins
those records to packed FClassParams, including the complete property array.
The caller authenticates the PE; this parser supplies bounds and ambiguity
guards, not publisher authentication or permission to activate a schema.
"""
from collections import defaultdict
from dataclasses import dataclass
import re
import struct

from .nte_native_schema import (MAX_NATIVE, MAX_NATIVE_PROPERTIES, MAX_SCAN_MATCHES,
                                NATIVE_FLAGS, _check)


@dataclass(frozen=True)
class NativeClass:
    name: str
    parent: str | None
    parent_callback: int
    outer: int
    inner: int
    flags: int
    cpp_abstract: bool
    descriptors: tuple


def _writable_image(pe):
    """Retain zero-initialized BSS bounds as well as file-backed data bounds."""
    header = pe.unpack('I', 60)[0]
    optional = header + 24
    table = optional + pe.unpack('H', header + 20)[0]
    image_size = pe.unpack('I', optional + 56)[0]
    sections, writable = [], []
    for index in range(pe.unpack('H', header + 6)[0]):
        offset = table + 40 * index
        virtual, rva, size, raw = pe.unpack('4I', offset + 8)
        flags = pe.unpack('I', offset + 36)[0]
        length = max(virtual, size)
        if not length:
            continue
        _check(rva + length <= image_size)
        for start, end in sections:
            _check(rva + length <= start or end <= rva)
        sections.append((rva, rva + length))
        if flags & 0xc0000000 == 0xc0000000 and not flags & 0x20000000:
            writable.append((pe.base + rva, length, raw, size))
    return writable


def _zero_info(pe, sections, pointer):
    if pointer % 8:
        return False
    for start, length, raw, size in sections:
        if start <= pointer and pointer + 16 <= start + length:
            at = pointer - start
            count = min(16, max(0, size - at))
            return not count or pe.read(raw + at, count) == bytes(count)
    return False


def _words(pe, sections):
    for _, length, section, _ in sections:
        start = section + (-section % 8)
        raw = pe.read(start, (section + length - start) // 8 * 8)
        for index, (value,) in enumerate(struct.iter_unpack('<Q', raw)):
            yield start + 8 * index, value, section, section + length


def descriptors(pe):
    """Return bounded class declarations, including duplicate names for refusal.

    Parent identity is another original registration callback. Package callbacks
    remain opaque code pointers; they are never called or disassembled. Types
    and properties are not selected from a game-specific name list.
    """
    readable = [row for row in pe.sections if row[3] & 0x40000000 and not row[3] & 0x20000000]
    writable = _writable_image(pe)
    names, matches = {}, 0
    pattern = rb'(?<![A-Za-z0-9_]\x00)(?:[AUI]\x00)(?:[A-Za-z0-9_]\x00){1,254}\x00\x00'
    for start, length, section, _ in readable:
        for hit in re.finditer(pattern, pe.read(section, length)):
            matches += 1
            _check(matches <= MAX_SCAN_MATCHES)
            if (section + hit.start()) % 2 == 0:
                names[start + hit.start()] = hit.group()[:-2].decode('utf-16le')[1:]
    identities, parents = defaultdict(set), defaultdict(set)
    for offset, pointer, section, end in _words(pe, readable):
        if pointer not in names or offset - 16 < section or offset + 16 > end:
            continue
        outer, inner, _, info = pe.unpack('4Q', offset - 16)
        if (pe.pointer(outer, code=True) is None or pe.pointer(inner, code=True) is None
                or not _zero_info(pe, writable, info)):
            continue
        identities[inner].add((names[pointer], outer))
        parents[outer].add(names[pointer])
        _check(len(identities) <= MAX_NATIVE)
    identities = {pointer: next(iter(values)) for pointer, values in identities.items() if len(values) == 1}
    result, properties, links, candidates = [], 0, 0, 0
    for offset, pointer, _, end in _words(pe, readable):
        if pointer not in identities or offset + 64 > end:
            continue
        candidates += 1
        _check(candidates <= MAX_SCAN_MATCHES)
        inner, config, cpp, deps, functions, fields, interfaces, packed, flags = pe.unpack('7Q2I', offset)
        nd, nf, np, ni = packed & 15, (packed >> 4) & 2047, (packed >> 15) & 2047, packed >> 26
        cpp_at = pe.pointer(cpp, 1)
        if (config and pe.name(config) is None or not flags & 0x80 or flags & 0x40000
                or nd not in (1, 2) or np > 1024 or ni > 32
                or bool(functions) != bool(nf) or bool(fields) != bool(np) or bool(interfaces) != bool(ni)
                or cpp_at is None or pe.read(cpp_at, 1) not in (b'\0', b'\1')):
            continue
        deps_at = pe.pointer(deps, nd * 8)
        if deps_at is None:
            continue
        dependencies = pe.unpack(str(nd) + 'Q', deps_at)
        if (any(pe.pointer(value, code=True) is None for value in dependencies)
                or dependencies[-1] in parents
                or nd == 2 and len(parents.get(dependencies[0], ())) != 1):
            continue
        functions_at = pe.pointer(functions, nf * 16) if nf else 0
        if nf and functions_at is None:
            continue
        links += nf + ni
        _check(links <= MAX_NATIVE_PROPERTIES)
        function_names = []
        for index in range(nf):
            callback, name = pe.unpack('2Q', functions_at + 16 * index)
            name = pe.name(name)
            if pe.pointer(callback, code=True) is None or name is None:
                break
            function_names.append(name)
        else:
            if len(set(function_names)) != nf:
                continue
            interface_at = pe.pointer(interfaces, ni * 16) if ni else 0
            if ni and interface_at is None:
                continue
            for index in range(ni):
                callback, adjustment, implemented, padding = pe.unpack('QiB3s', interface_at + 16 * index)
                if (pe.pointer(callback, code=True) is None or adjustment < 0
                        or implemented not in (0, 1) or padding != bytes(3)):
                    break
            else:
                fields_at = pe.pointer(fields, np * 8) if np else 0
                if np and fields_at is None:
                    continue
                properties += np
                _check(properties <= MAX_NATIVE_PROPERTIES)
                values, seen = [], set()
                for index in range(np):
                    address = pe.unpack('Q', fields_at + index * 8)[0]
                    prop = pe.pointer(address, 56)
                    if prop is None or address in seen:
                        break
                    seen.add(address)
                    name = pe.name(pe.unpack('Q', prop)[0])
                    generator, object_flags = pe.unpack('II', prop + 24)
                    dimension = pe.unpack('H', prop + 48)[0]
                    if not name or object_flags != NATIVE_FLAGS or not dimension:
                        break
                    callback = 0
                    if generator & 63 in (0, 25, 30):
                        if pe.pointer(address, 64) is None:
                            break
                        callback = pe.unpack('Q', prop + 56)[0]
                    values.append((name, generator, dimension, callback))
                else:
                    name, outer = identities[inner]
                    parent = next(iter(parents[dependencies[0]])) if nd == 2 else None
                    result.append(NativeClass(name, parent, dependencies[0] if nd == 2 else 0,
                                              outer, inner, flags, bool(pe.read(cpp_at, 1)[0]), tuple(values)))
                    _check(len(result) <= MAX_NATIVE)
    return tuple(result)
