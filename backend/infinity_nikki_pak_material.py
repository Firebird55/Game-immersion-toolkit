"""Discover the original zero-GUID PAK key's registered native producer as data.

This follows the evidenced SHA-1/index/GUID consumer, getter storage, setter and
startup callback. It never scans for candidate key literals or tests a key list.
The current native owner must already be authenticated. Global PAK compatibility
and nonzero/dynamic key GUIDs require separate archive evidence.
"""
from dataclasses import dataclass, field
import hashlib
import struct

from .infinity_nikki_native import _Elf, _call, _literal_pair, _adrp, extract_wrapper_material


def _check(value):
    if not value:
        raise ValueError('Could not verify the current official Infinity Nikki default PAK key producer.')


@dataclass(frozen=True)
class DefaultPakMaterial:
    parameter: bytes = field(repr=False)
    source_sha256: str
    registered_callback: int
    binding_address: int
    source_addresses: tuple[int, ...] = field(repr=False)


def _writable(elf, address, size):
    return any(flags & 2 and start <= address and address + size <= start + length
               for flags, start, length in elf.loads)


def _readonly(elf, address, size):
    sections = [s for s in elf.sections if s['kind'] != 8 and s['flags'] & 2 and not s['flags'] & 5 and
                s['address'] <= address and address + size <= s['address'] + s['size']]
    _check(len(sections) == 1)
    section = sections[0]
    at = section['offset'] + address - section['address']
    return elf.raw[at:at + size]


def _scan(elf):
    code = elf.code
    for at in range(code['offset'], code['offset'] + code['size'], 1024**2):
        raw = elf.raw[at:min(at + 1024**2, code['offset'] + code['size'])]
        for index, (word,) in enumerate(struct.iter_unpack('<I', raw)):
            yield code['address'] + at + index * 4 - code['offset'], word


def _getter_storage(elf, address):
    try:
        words, values = elf.words(address, 160), set()
        for index in range(len(words) - 1):
            pair = _literal_pair(words[index], words[index + 1], address + index * 4)
            if pair is None or pair[0] != 0 or not _writable(elf, pair[1], 16):
                continue
            for following in words[index + 2:index + 8]:
                if following == 0xd65f03c0:
                    values.add(pair[1])
                    break
                if following & 31 == 0 or _call(following, 0) is not None:
                    break
        return values.pop() if len(values) == 1 else None
    except ValueError:
        return None


def _zero_guid_delegate(elf, address):
    try:
        words = elf.words(address, 512)
        # Original default-getkey helper first initializes the complete output
        # to zero, then dispatches its zero-GUID branch through one delegate.
        _check(0x6f00e400 in words[:16] and 0xad000000 in words[:16])
        calls = [_call(word, address + index * 4) for index, word in enumerate(words)]
        repeated = {target for target in calls if target is not None and calls.count(target) >= 2}
        storages = {_getter_storage(elf, target) for target in repeated}
        storages.discard(None)
        return storages.pop() if len(storages) == 1 else None
    except ValueError:
        return None


def _consumer_storage(elf, address):
    try:
        words = elf.words(address, 512)
        storages = set()
        for index, word in enumerate(words):
            target = _call(word, address + index * 4)
            if target is not None:
                storage = _zero_guid_delegate(elf, target)
                if storage is not None:
                    storages.add(storage)
        return storages.pop() if len(storages) == 1 else None
    except ValueError:
        return None


def _function_start(elf, pc):
    # Only the observed bounded setter prologue is accepted. This avoids
    # trusting unrelated/rewritten unwind records as a registration proof.
    low = max(elf.code['address'], pc - 128)
    words = elf.words(low, pc - low + 4)
    for index in range(len(words) - 1, -1, -1):
        word = words[index]
        if (word & 0xffc00000 == 0xa9800000 and word & 31 == 29 and
                (word >> 10) & 31 == 30 and (word >> 5) & 31 == 31):
            start = low + index * 4
            for _ in range(2):
                if start < elf.code['address'] + 4:
                    break
                previous = elf.words(start - 4, 4)[0]
                if previous not in (0xd503245f, 0xd503233f, 0xd503237f):
                    break
                start -= 4
            return start
    return None


def _captures_callback(elf, address, storage):
    words, aliases, pointers, objects = elf.words(address, 512), {0}, {}, {}
    for index, word in enumerate(words):
        if word == 0xd65f03c0:
            return False
        kind, base = word & 0xffc00000, (word >> 5) & 31
        if kind == 0xa9000000 and base in objects:
            amount = (word >> 15) & 127
            if amount & 64:
                amount -= 128
            for offset, source in enumerate((word & 31, (word >> 10) & 31)):
                if source in aliases and objects[base] + amount * 8 + offset * 8 == 24:
                    return True
        if kind == 0xf9000000 and base in objects and word & 31 in aliases:
            if objects[base] + ((word >> 10) & 4095) * 8 == 24:
                return True
        if word & 0xffe0ffe0 == 0xaa0003e0:
            destination, source = word & 31, (word >> 16) & 31
            was_alias = source in aliases
            pointer, obj = pointers.get(source), objects.get(source)
            aliases.discard(destination)
            pointers.pop(destination, None)
            objects.pop(destination, None)
            if was_alias:
                aliases.add(destination)
            if pointer is not None:
                pointers[destination] = pointer
            if obj is not None:
                objects[destination] = obj
        elif word & 0x9f000000 == 0x90000000:
            destination = word & 31
            aliases.discard(destination)
            objects.pop(destination, None)
            pointers[destination] = _adrp(word, address + index * 4)
        elif kind == 0x91000000:
            destination, source, amount = word & 31, base, (word >> 10) & 4095
            pointer, obj = pointers.get(source), objects.get(source)
            aliases.discard(destination)
            pointers.pop(destination, None)
            objects.pop(destination, None)
            if pointer is not None:
                pointers[destination] = pointer + amount
            if obj is not None:
                objects[destination] = obj + amount
        elif kind == 0xf9400000:
            destination = word & 31
            location = pointers.get(base)
            aliases.discard(destination)
            pointers.pop(destination, None)
            objects.pop(destination, None)
            if location is not None and location + ((word >> 10) & 4095) * 8 == storage:
                objects[destination] = 0
        elif word & 0xfc000000 == 0x94000000:
            aliases.difference_update(range(19))
            for destination in range(19):
                pointers.pop(destination, None)
                objects.pop(destination, None)
        elif (word & 0x7c000000 == 0x14000000 or word & 0x7e000000 in (0x34000000, 0x36000000)
              or word & 0xff000010 == 0x54000000):
            continue
        else:
            aliases.discard(word & 31)
            pointers.pop(word & 31, None)
            objects.pop(word & 31, None)
    return False


def _argument_address(elf, pc):
    words = elf.words(pc - 8, 8)
    last = words[-1]
    if last & 0x9f00001f == 0x10000000:  # ADR X0, exact callback
        immediate = ((last >> 29) & 3) | (((last >> 5) & 0x7ffff) << 2)
        if immediate & (1 << 20):
            immediate -= 1 << 21
        return pc - 4 + immediate
    pair = _literal_pair(words[0], words[1], pc - 8)
    return pair[1] if pair and pair[0] == 0 else None


def _copy_output(elf, address):
    registers, values, output, origins = {0: ('output', 0)}, {}, {}, {}
    for index, word in enumerate(elf.words(address, 128)):
        if word in (0xd503201f, 0xd503245f, 0xd503233f, 0xd503237f, 0xd50323bf, 0xd50323ff):
            continue
        if word == 0xd65f03c0:
            _check(set(output) == set(range(32)))
            return bytes(output[i] for i in range(32)), tuple(origins[i] for i in range(32))
        if word & 0x9f000000 == 0x90000000:
            registers[word & 31] = _adrp(word, address + 4 * index)
            values.pop((False, word & 31), None)
            continue
        if word & 0xffe0ffe0 == 0xaa0003e0:
            destination, source = word & 31, (word >> 16) & 31
            pointer, value = registers.get(source), values.get((False, source))
            _check(destination != 31 and (pointer is not None or value is not None))
            registers.pop(destination, None)
            values.pop((False, destination), None)
            if pointer is not None:
                registers[destination] = pointer
            if value is not None:
                values[(False, destination)] = value
            continue
        if word & 0xff800000 == 0x91000000:
            destination, source = word & 31, (word >> 5) & 31
            amount = ((word >> 10) & 4095) << (12 if word & (1 << 22) else 0)
            _check(source in registers and destination != 31)
            value = registers[source]
            registers[destination] = (value[0], value[1] + amount) if isinstance(value, tuple) else value + amount
            values.pop((False, destination), None)
            continue
        kind = word & 0xffc00000
        if kind in (0xad400000, 0xad000000, 0xa9400000, 0xa9000000):
            vector, load = kind in (0xad400000, 0xad000000), kind in (0xad400000, 0xa9400000)
            width, targets = (16 if vector else 8), (word & 31, (word >> 10) & 31)
            amount = (word >> 15) & 127
            if amount & 64:
                amount -= 128
            amount *= width
        elif kind in (0x3dc00000, 0x3d800000, 0xf9400000, 0xf9000000):
            vector, load = kind in (0x3dc00000, 0x3d800000), kind in (0x3dc00000, 0xf9400000)
            width, targets = (16 if vector else 8), (word & 31,)
            amount = ((word >> 10) & 4095) * width
        else:
            raise ValueError('The registered default PAK callback could not be verified as a static copy producer.')
        source = (word >> 5) & 31
        _check(source in registers)
        base = registers[source]
        for position, target in enumerate(targets):
            offset = amount + position * width
            if load:
                _check(type(base) is int and (vector or target != 31))
                at = base + offset
                values[(vector, target)] = (_readonly(elf, at, width), at)
                if not vector:
                    registers.pop(target, None)
            else:
                _check(isinstance(base, tuple) and base[0] == 'output' and (vector, target) in values)
                start = base[1] + offset
                _check(0 <= start <= 32 - width)
                raw, origin = values[(vector, target)]
                for n, value in enumerate(raw):
                    at = start + n
                    _check(at not in output)
                    output[at], origins[at] = value, origin + n
    raise ValueError('The registered default PAK callback has no bounded return.')


def extract_default_pak_material(native, *, expected_native_sha256: str) -> DefaultPakMaterial:
    """Derive the currently registered default PAK output from verified source.

    Index/metadata SHA-1 consumers select the registration path. Candidate
    ciphertext, a legacy key, a key cache or a release-specific address is never
    an input to discovery. Callers must separately validate every archive/GUID.
    """
    wrapper = extract_wrapper_material(native, expected_native_sha256=expected_native_sha256)
    elf = _Elf(native)
    helpers = set()
    for pc, word in _scan(elf):
        if _call(word, pc) != wrapper.hash_function_address or pc < elf.code['address'] + 48:
            continue
        previous = elf.words(pc - 48, 48)
        calls = [(index, _call(value, pc - 48 + index * 4)) for index, value in enumerate(previous)]
        calls = [(index, target) for index, target in calls if target is not None]
        if not calls:
            continue
        index, target = calls[-1]
        if index < 6:
            continue
        guid = previous[max(0, index - 4):index]
        if any(value & 0xffc00000 == 0xa9400000 and value & 31 == 2 and (value >> 10) & 31 == 3 for value in guid):
            helpers.add(target)
    _check(1 <= len(helpers) <= 16)
    storages = {_consumer_storage(elf, target) for target in helpers}
    storages.discard(None)
    _check(len(storages) == 1)
    storage = storages.pop()
    setters = set()
    for pc, word in _scan(elf):
        if word & 0x9f000000 != 0x90000000:
            continue
        try:
            pair = _literal_pair(word, elf.words(pc + 4, 4)[0], pc)
        except ValueError:
            continue
        if pair and pair[1] == storage and pair[0] != 0:
            start = _function_start(elf, pc)
            if start is not None and _captures_callback(elf, start, storage):
                setters.add(start)
    _check(len(setters) == 1)
    setter, candidates = setters.pop(), {}
    for pc, word in _scan(elf):
        if _call(word, pc) != setter or pc < elf.code['address'] + 8:
            continue
        callback = _argument_address(elf, pc)
        _check(callback is not None)
        value, addresses = _copy_output(elf, callback)
        candidates[(callback, value, addresses)] = pc
    _check(len(candidates) == 1)
    (callback, value, addresses), binding = candidates.popitem()
    return DefaultPakMaterial(value, expected_native_sha256, callback, binding, addresses)


def decode_default_index(raw: bytes, material: DefaultPakMaterial, expected_sha1: bytes, *, key_guid: bytes, crypto=None) -> bytes:
    """Read the evidenced default-index AES/XOR format and verify its plaintext.

    No source authentication or nonzero key-GUID support is inferred from a
    matching SHA-1. The caller retains that distinct original archive evidence.
    """
    _check(isinstance(raw, bytes) and 0 < len(raw) <= 64 * 1024**2 and len(raw) % 16 == 0 and
           isinstance(material, DefaultPakMaterial) and len(material.parameter) == 32 and
           isinstance(expected_sha1, bytes) and len(expected_sha1) == 20 and
           isinstance(key_guid, bytes) and key_guid == bytes(16))
    if crypto is None:
        from .publisher_crypto import DesktopPublisherCrypto
        crypto = DesktopPublisherCrypto()
    decoded = crypto.block_cipher('AES', 'ECB', material.parameter, raw)
    _check(isinstance(decoded, bytes) and len(decoded) == len(raw))
    result = bytearray(decoded)
    for start in range(0, len(result), 16):
        result[start] ^= material.parameter[-1]
        result[start + 15] ^= material.parameter[0]
    _check(hashlib.sha1(result).digest() == expected_sha1)
    return bytes(result)
