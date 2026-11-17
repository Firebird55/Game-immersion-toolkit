"""Bounded original TextMap reader; no production catalog or Setup integration.

The caller authenticates publisher payloads and supplies an owned x64 native
reader method window. Hashes identify inputs, not their authenticity. Parameter
recovery recognizes the inspected compiled arithmetic shapes; it is not a
general disassembler and does not find native metadata/method ownership. No
client code executes and no game version, address, path or parameter is pinned.
"""
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import re
import struct

from .game_tools import _atomic_file


MAX_METHOD = 64 * 1024
MAX_SHARD = 64 * 1024**2
MAX_INPUT = 256 * 1024**2
MAX_SHARDS = 4096
MAX_ROWS = 2_000_000
MASK64 = (1 << 64) - 1


def _check(value):
    if not value:
        raise ValueError('Unsupported, ambiguous or incomplete original Genshin TextMap input')


@dataclass(frozen=True)
class NativeTextMapParameters:
    count_add: int
    count_xor: int
    mul0: int
    add0: int
    rot0: int
    mul1: int
    add1: int
    xor1: int
    rot1: int
    mul2: int
    key_xor: int
    text_xor: int
    method_sha256: str

    def __post_init__(self):
        for name, value in asdict(self).items():
            if name == 'method_sha256':
                _check(isinstance(value, str) and re.fullmatch('[a-f0-9]{64}', value))
                continue
            maximum = 0xffffffff if name.startswith('count_') else 63 if name.startswith('rot') else MASK64
            _check(type(value) is int and 0 <= value <= maximum)
        _check(self.rot0 and self.rot1 and self.mul0 & 1 and self.mul1 & 1 and self.mul2 & 1
               and self.key_xor != self.text_xor)

    def fingerprint(self):
        fields = {key: value for key, value in asdict(self).items() if key != 'method_sha256'}
        return hashlib.sha256(json.dumps(fields, sort_keys=True).encode()).hexdigest()


@dataclass(frozen=True)
class _Register:
    number: int
    bits: int


@dataclass(frozen=True)
class _Memory:
    base: int | None
    index: int | None
    scale: int
    displacement: int
    bits: int


@dataclass(frozen=True)
class _Instruction:
    operation: str
    destination: _Register | _Memory
    source: _Register | _Memory | int
    end: int


def _instruction(data, start):
    """Decode only the fixed instruction forms used by the parameter templates."""
    at, rex = start, 0

    def take(size):
        nonlocal at
        if size > len(data) - at:
            raise ValueError('Truncated instruction')
        raw = data[at:at + size]
        at += size
        return raw

    def number(size, signed=False):
        return int.from_bytes(take(size), 'little', signed=signed)

    try:
        opcode = number(1)
        if 0x40 <= opcode <= 0x4f:
            rex, opcode = opcode, number(1)
        bits = 64 if rex & 8 else 32
        if 0xb8 <= opcode <= 0xbf:
            destination = _Register(opcode - 0xb8 + (8 if rex & 1 else 0), bits)
            return _Instruction('mov', destination, number(bits // 8), at)
        if opcode == 0x0f:
            if number(1) != 0xaf:
                return None
            opcode = 0x0faf
        if opcode not in (0x03, 0x01, 0x33, 0x31, 0x8b, 0x89, 0x63, 0x0faf, 0xc1, 0x81, 0x83):
            return None
        modrm = number(1)
        mode, group = modrm >> 6, (modrm >> 3) & 7
        register = _Register(group + (8 if rex & 4 else 0), bits)
        rm_number = (modrm & 7) + (8 if rex & 1 else 0)
        memory_bits = 32 if opcode == 0x63 else bits
        if mode == 3:
            rm = _Register(rm_number, memory_bits)
        else:
            base, index, scale = rm_number, None, 1
            if modrm & 7 == 4:
                sib = number(1)
                scale = 1 << (sib >> 6)
                index_number = ((sib >> 3) & 7) + (8 if rex & 2 else 0)
                index = None if index_number == 4 else index_number
                base = (sib & 7) + (8 if rex & 1 else 0)
                if mode == 0 and sib & 7 == 5:
                    base = None
            elif mode == 0 and modrm & 7 == 5:
                base = None  # RIP-relative accesses cannot own a count template.
            displacement = number(1, True) if mode == 1 else number(4, True) if mode == 2 or base is None else 0
            rm = _Memory(base, index, scale, displacement, memory_bits)
        if opcode in (0x81, 0x83):
            operation = {0: 'add', 1: 'or', 4: 'and', 5: 'sub', 6: 'xor'}.get(group)
            if operation is None:
                return None
            immediate = number(1 if opcode == 0x83 else 4, True) & ((1 << bits) - 1)
            return _Instruction(operation, rm, immediate, at)
        if opcode == 0xc1:
            if group != 0:
                return None
            return _Instruction('rol', rm, number(1), at)
        operation = {0x03: 'add', 0x01: 'add', 0x33: 'xor', 0x31: 'xor', 0x8b: 'mov',
                     0x89: 'mov', 0x63: 'movsxd', 0x0faf: 'imul'}[opcode]
        destination, source = (rm, register) if opcode in (0x01, 0x31, 0x89) else (register, rm)
        return _Instruction(operation, destination, source, at)
    except ValueError:
        return None


def _mix_at(method, start):
    pattern = ('mov', 'imul', 'mov', 'add', 'rol', 'mov', 'imul', 'mov',
               'add', 'mov', 'xor', 'rol', 'mov', 'imul', 'mov', 'xor')
    at, accumulator, key = start, None, None
    constants, rotations = [], []
    for operation in pattern:
        for skipped in range(4):
            instruction = _instruction(method, at)
            if instruction is None:
                return None
            destination, source = instruction.destination, instruction.source
            matched = False
            if instruction.operation == operation and isinstance(destination, _Register) and destination.bits == 64:
                if operation == 'mov' and type(source) is int and destination.number != accumulator:
                    key = destination.number
                    constants.append(source)
                    matched = True
                elif operation == 'rol' and destination.number == accumulator and type(source) is int and 0 < source < 64:
                    rotations.append(source)
                    matched = True
                elif (operation in ('imul', 'add', 'xor') and isinstance(source, _Register)
                      and source.bits == 64 and source.number == key):
                    if accumulator is None:
                        accumulator = destination.number
                    matched = destination.number == accumulator and accumulator != key
            at = instruction.end
            if matched:
                break
            # Compilers can interleave buffer-position loads between the final
            # arithmetic steps. Only independent, understood moves may be skipped.
            if (accumulator is None or instruction.operation not in ('mov', 'movsxd')
                    or isinstance(destination, _Register) and destination.number == accumulator
                    or operation in ('imul', 'add', 'xor') and isinstance(destination, _Register) and destination.number == key
                    or instruction.operation == 'mov' and type(source) is int):
                return None
        else:
            return None
    return tuple(constants), tuple(rotations)


def _count_at(method, start):
    first = _instruction(method, start)
    if not first or first.operation != 'mov' or not isinstance(first.destination, _Register) or first.destination.bits != 32 or type(first.source) is not int:
        return None
    added = _instruction(method, first.end)
    if (not added or added.operation != 'add' or added.destination != first.destination
            or not isinstance(added.source, _Memory) or added.source.bits != 32
            or added.source.base is None or added.source.index is None
            or added.source.displacement != 0x20):
        return None
    at = added.end
    for _ in range(3):
        last = _instruction(method, at)
        if not last:
            return None
        if last.operation == 'xor' and last.destination == first.destination and type(last.source) is int:
            return first.source, last.source
        if last.operation != 'mov' or isinstance(last.destination, _Register) and last.destination.number == first.destination.number:
            return None
        at = last.end
    return None


def derive_native_parameters(method: bytes) -> NativeTextMapParameters:
    """Recover arithmetic from a caller-proved original x64 reader method.

    The supplied window must be one actual reader, not a whole executable or a
    concatenation. Recovery rejects missing, conflicting and duplicate shapes.
    Method ownership, publisher authentication and native bootstrap stay with
    the caller. This function neither executes nor loads native code.
    """
    _check(isinstance(method, bytes) and 64 <= len(method) <= MAX_METHOD)
    mixes, counts = [], []
    for at in range(len(method)):
        if mix := _mix_at(method, at):
            mixes.append(mix)
        if count := _count_at(method, at):
            counts.append(count)
    _check(len(mixes) == 4 and len(counts) == 2 and counts[0] == counts[1])
    core = mixes[0][0][:-1], mixes[0][1]
    _check(all((constants[:-1], rotations) == core for constants, rotations in mixes))
    finishes = [constants[-1] for constants, _ in mixes]
    _check(finishes[0] == finishes[2] and finishes[1] == finishes[3] and finishes[0] != finishes[1])
    constants, rotations = core
    return NativeTextMapParameters(*counts[0], constants[0], constants[1], rotations[0],
        constants[2], constants[3], constants[4], rotations[1], constants[5], finishes[0],
        finishes[1], hashlib.sha256(method).hexdigest())


def discover_native_parameters(image):
    """Find one unique complete format contract in original unwind ranges.

    This is format discovery, not semantic method ownership. The caller must
    authenticate the whole original executable and validate complete original
    TextMap inputs before publication. No address or parameter is reused across
    revisions. All equivalent method descriptions are returned, sorted by hash;
    no method is selected as a semantic owner. Different parameter contracts are
    ambiguous and require a reviewed description or complete input validation.
    """
    from .genshin_native_x64 import Image
    _check(isinstance(image, Image))
    candidates, attempts = [], 0
    for start, end in zip(image.function_starts, image.function_ends):
        size = end - start
        if not 64 <= size <= MAX_METHOD:
            continue
        offset = image.offset(start, size)
        method = image.data[offset:offset + size]
        # Necessary opcode counts only; the full typed matcher owns acceptance.
        if method.count(b'\x0f\xaf') < 12 or len(re.findall(rb'[\x48\x49]\xc1[\xc0-\xc7].', method, re.S)) < 8:
            continue
        attempts += 1
        _check(attempts <= 128)
        try:
            candidates.append(derive_native_parameters(method))
        except ValueError:
            continue
    _check(candidates and len({candidate.fingerprint() for candidate in candidates}) == 1)
    return tuple(sorted(candidates, key=lambda candidate: candidate.method_sha256))


def _mix(value, parameters, finish):
    def rotate(value, shift):
        return ((value << shift) | (value >> (64 - shift))) & MASK64
    value = (value * parameters.mul0 + parameters.add0) & MASK64
    value = (rotate(value, parameters.rot0) * parameters.mul1 + parameters.add1) & MASK64
    return ((rotate(value ^ parameters.xor1, parameters.rot1) * parameters.mul2) & MASK64) ^ finish


def _decode_shard(data, parameters):
    _check(isinstance(data, bytes) and 8 <= len(data) <= MAX_SHARD)
    at = 0

    def take(size):
        nonlocal at
        _check(0 <= size <= len(data) - at)
        start, at = at, at + size
        return data[start:at]

    def u32():
        return struct.unpack('<I', take(4))[0]

    def count(minimum_size):
        value = ((u32() + parameters.count_add) & 0xffffffff) ^ parameters.count_xor
        _check(value <= min(MAX_ROWS, (len(data) - at) // minimum_size))
        return value

    values, aliases = {}, {}
    strings = count(6)
    for index in range(strings):
        key_mix = _mix(index, parameters, parameters.key_xor)
        key = ((u32() ^ (key_mix & 0xffffffff)) + (key_mix >> 32)) & 0xffffffff
        text_mix = _mix((index + key) & 0xffffffff, parameters, parameters.text_xor)
        length = ((struct.unpack('<H', take(2))[0] + (text_mix & 0xffff)) & 0xffff) ^ ((text_mix >> 32) & 0xffff)
        cipher, key_bytes = take(length), text_mix.to_bytes(8, 'little')
        text = bytes(value ^ key_bytes[number & 7] for number, value in enumerate(cipher)).decode('utf-8', errors='strict')
        _check(key not in values)
        values[key] = text
    for offset in range(count(8)):
        index = strings + offset
        key_mix = _mix(index, parameters, parameters.key_xor)
        key = ((u32() ^ (key_mix & 0xffffffff)) + (key_mix >> 32)) & 0xffffffff
        alias_mix = _mix((index + key) & 0xffffffff, parameters, parameters.text_xor)
        target = ((u32() + (alias_mix & 0xffffffff)) & 0xffffffff) ^ (alias_mix >> 32)
        _check(key not in values and key not in aliases)
        aliases[key] = target
    _check(at == len(data) and len(values) + len(aliases) <= MAX_ROWS)
    return values, aliases


def decode_textmaps(shards, parameters: NativeTextMapParameters) -> dict[int, str]:
    """Read a complete shard set, resolving aliases without mutating old data."""
    _check(isinstance(parameters, NativeTextMapParameters))
    values, aliases, total_bytes, shard_count = {}, {}, 0, 0
    for data in shards:
        shard_count += 1
        _check(shard_count <= MAX_SHARDS and isinstance(data, bytes))
        total_bytes += len(data)
        _check(total_bytes <= MAX_INPUT)
        direct, links = _decode_shard(data, parameters)
        _check(not any(key in values or key in aliases for key in direct.keys() | links.keys()))
        _check(len(values) + len(aliases) + len(direct) + len(links) <= MAX_ROWS)
        values.update(direct)
        aliases.update(links)
    _check(shard_count > 0)
    for identity in aliases:
        chain, seen, target = [], set(), identity
        while target not in values:
            _check(target in aliases and target not in seen)
            chain.append(target)
            seen.add(target)
            target = aliases[target]
        for key in chain:
            values[key] = values[target]
    return values


def refresh_textmap_cache(destination: Path, shards, parameters: NativeTextMapParameters, *, source_sha256: str):
    """Publish only a complete validated text cache; failure retains the old file.

    The source fingerprint is a caller-provided immutable publisher-generation
    identity, not authentication. This independent cache does not activate a
    game language or replace the production dialogue/voice catalog.
    """
    _check(isinstance(source_sha256, str) and re.fullmatch('[a-f0-9]{64}', source_sha256))
    values = decode_textmaps(shards, parameters)
    _check(values)
    payload = {'format': 'genshin-original-textmap-v1', 'source_sha256': source_sha256,
               'method_sha256': parameters.method_sha256, 'parameters_sha256': parameters.fingerprint(),
               'texts': values}
    _atomic_file(Path(destination), json.dumps(payload, ensure_ascii=False).encode('utf-8'))
    return len(values)
