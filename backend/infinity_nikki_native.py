"""Read the evidenced AArch64 wrapper-owner path as data, without client execution.

Callers must first verify the complete original APK and native member and bind
``expected_native_sha256`` to that receipt. This parser discovers literals/calls
by ELF addresses; it contains no publisher key, seed, suffix or fixed RVA. It
supports the observed authored SHA-1/AES wrapper path, not arbitrary native code.
Unknown or ambiguous paths require reader work, never a guessed/community key.
"""
from dataclasses import dataclass, field
import base64
import hashlib
import json
import re
import struct

from Crypto.Cipher import AES


MAX_NATIVE = 256 * 1024**2
MAX_WRAPPED = 4 * 1024**2
_SHA1_INITIAL = struct.pack('<4I', 0x67452301, 0xefcdab89, 0x98badcfe, 0x10325476)


def _require(condition):
    if not condition:
        raise ValueError('Infinity Nikki original wrapper owner is incomplete, ambiguous or has changed format.')


@dataclass(frozen=True)
class WrapperMaterial:
    seed_utf16: bytes = field(repr=False)
    suffix: bytes = field(repr=False)
    source_sha256: str


class _Elf:
    def __init__(self, raw):
        self.raw = raw
        _require(64 <= len(raw) <= MAX_NATIVE and raw[:6] == b'\x7fELF\x02\x01')
        header = struct.unpack_from('<HHIQQQIHHHHHH', raw, 16)
        _require(header[0] == 3 and header[1] == 183 and header[2] == 1 and header[7] == 64)
        start, entry, count, names_index = header[5], header[10], header[11], header[12]
        _require(entry == 64 and 1 <= count <= 256 and names_index < count and start <= len(raw) - count * entry)
        self.sections = []
        for index in range(count):
            values = struct.unpack_from('<II4QII2Q', raw, start + index * entry)
            name, kind, flags, address, offset, size = values[:6]
            _require(kind == 8 or 0 <= offset <= len(raw) - size)
            self.sections.append({'name_index': name, 'kind': kind, 'flags': flags,
                                  'address': address, 'offset': offset, 'size': size})
        names = self.sections[names_index]
        _require(names['kind'] == 3 and 0 < names['size'] <= 65536)
        strings = raw[names['offset']:names['offset'] + names['size']]
        for section in self.sections:
            index = section.pop('name_index')
            _require(index < len(strings) and b'\0' in strings[index:])
            section['name'] = strings[index:strings.index(b'\0', index)].decode('ascii')
        code = [s for s in self.sections if s['name'] == '.text' and s['kind'] == 1 and s['flags'] & 6 == 6]
        ro = [s for s in self.sections if s['name'] == '.rodata' and s['kind'] == 1 and s['flags'] & 3 == 2]
        _require(len(code) == len(ro) == 1 and 4 <= code[0]['size'] <= MAX_NATIVE and code[0]['size'] % 4 == 0 and
                 code[0]['offset'] % 4 == code[0]['address'] % 4 == 0 and 2 <= ro[0]['size'] <= 64 * 1024**2)
        self.code, self.ro = code[0], ro[0]

    def position(self, address, size=1, *, code=False):
        owners = [s for s in self.sections if s['kind'] != 8 and s['flags'] & 2 and
                  s['address'] <= address and 0 <= size <= s['address'] + s['size'] - address]
        _require(len(owners) == 1 and (not code or owners[0] is self.code))
        return owners[0]['offset'] + address - owners[0]['address']

    def words(self, address, size):
        at = self.position(address, 4, code=True)
        size = min(size, self.code['address'] + self.code['size'] - address) & ~3
        return [word for word, in struct.iter_unpack('<I', self.raw[at:at + size])]

    def string(self, address):
        at = self.position(address, 2)
        owner = next(s for s in self.sections if s['kind'] != 8 and s['flags'] & 2 and
                     s['address'] <= address < s['address'] + s['size'])
        limit = min(512, owner['address'] + owner['size'] - address) & ~1
        end = next((i for i in range(at, at + limit, 2) if self.raw[i:i + 2] == b'\0\0'), None)
        _require(end is not None and end > at)
        value = self.raw[at:end]
        value.decode('utf-16-le')
        return value


def _adrp(word, pc):
    immediate = ((word >> 29) & 3) | (((word >> 5) & 0x7ffff) << 2)
    if immediate & (1 << 20):
        immediate -= 1 << 21
    return (pc & ~4095) + (immediate << 12)


def _literal_pair(first, second, pc):
    if first & 0x9f000000 == 0x90000000 and second & 0xffc00000 == 0x91000000 and (second >> 5) & 31 == first & 31:
        return second & 31, _adrp(first, pc) + ((second >> 10) & 4095)
    return None


def _call(word, pc):
    if word & 0xfc000000 != 0x94000000:
        return None
    relative = word & 0x3ffffff
    if relative & (1 << 25):
        relative -= 1 << 26
    return pc + 4 * relative


def _mov32(word):
    if word & 0xff800000 == 0x52800000:
        return word & 31, ((word >> 5) & 65535) << (((word >> 21) & 1) * 16)
    return None


def _sha1_profile(elf, address):
    try:
        words = elf.words(address, 128)
        pages, constants, found_initial = {}, {}, False
        for index, word in enumerate(words):
            pc = address + index * 4
            if word & 0x9f000000 == 0x90000000:
                pages[word & 31] = _adrp(word, pc)
            move = _mov32(word)
            if move:
                constants[move[0]] = move[1]
            elif word & 0xff800000 == 0x72800000 and word & 31 in constants:
                register, shift = word & 31, ((word >> 21) & 1) * 16
                constants[register] = (constants[register] & ~(65535 << shift)) | (((word >> 5) & 65535) << shift)
            if word & 0xffc00000 == 0x3dc00000 and (word >> 5) & 31 in pages:
                target = pages[(word >> 5) & 31] + (((word >> 10) & 4095) * 16)
                at = elf.position(target, 16)
                found_initial |= elf.raw[at:at + 16] == _SHA1_INITIAL
        return found_initial and 0xc3d2e1f0 in constants.values()
    except (ValueError, struct.error):
        return False


def _builder_suffix(elf, address):
    try:
        words = elf.words(address, 2048)
        end = next(i for i, word in enumerate(words) if word == 0xd65f03c0)
        words = words[:end + 1]
        _require(any(move and move[1] == 20 for move in map(_mov32, words[:16])))
        suffix, shape, first_store = bytearray(), None, None
        for index in range(2, len(words)):
            load, move, store = words[index - 2:index + 1]
            immediate = _mov32(move)
            if store & 0xffe0fc00 != 0x38206800 or not immediate or immediate[0] != store & 31:
                continue
            _require(immediate[1] <= 255 and load & 0xffc00000 == 0xf9400000 and
                     (load >> 10) & 4095 == 0 and load & 31 == (store >> 5) & 31)
            current = ((load >> 5) & 31, (store >> 5) & 31, (store >> 16) & 31)
            _require(shape is None or current == shape)
            shape = current
            first_store = index if first_store is None else first_store
            suffix.append(immediate[1])
        _require(len(suffix) == 18)
        hash_calls = [target for i, word in enumerate(words[:first_store])
                      if (target := _call(word, address + 4 * i)) is not None and _sha1_profile(elf, target)]
        _require(len(hash_calls) == 1)
        return bytes(suffix)
    except (ValueError, StopIteration, struct.error):
        return None


def extract_wrapper_material(native, *, expected_native_sha256: str) -> WrapperMaterial:
    """Discover authored material in the fully verified current native owner.

    Source authenticity belongs to the caller; the hash binds this exact input
    to its verified APK/member receipt. Only the evidenced literal/call/builder
    instruction shapes are read. No native instruction is executed/emulated.
    """
    _require(isinstance(expected_native_sha256, str) and re.fullmatch('[0-9a-f]{64}', expected_native_sha256) and
             64 <= len(native) <= MAX_NATIVE and hashlib.sha256(native).hexdigest() == expected_native_sha256)
    elf = _Elf(native)
    needle, markers, start = '_XYLUAP_\0'.encode('utf-16-le'), set(), elf.ro['offset']
    stop = start + elf.ro['size']
    while (at := native.find(needle, start, stop)) >= 0:
        _require(len(markers) < 8)
        markers.add(elf.ro['address'] + at - elf.ro['offset'])
        start = at + len(needle)
    _require(bool(markers))
    references = []
    code = elf.code
    for start in range(code['offset'], code['offset'] + code['size'], 1024**2):
        raw = native[start:min(start + 1024**2, code['offset'] + code['size'])]
        for index, (word,) in enumerate(struct.iter_unpack('<I', raw)):
            if word & 0x9f000000 != 0x90000000:
                continue
            at = start + index * 4
            if at + 8 > code['offset'] + code['size']:
                continue
            pc = code['address'] + at - code['offset']
            pair = _literal_pair(word, struct.unpack_from('<I', native, at + 4)[0], pc)
            if pair and pair[1] in markers:
                _require(len(references) < 64)
                references.append(pc)
    candidates = set()
    builders = {}
    for reference in references:
        try:
            context = elf.words(reference, 512)
        except ValueError:
            continue
        for index, word in enumerate(context):
            target = _call(word, reference + index * 4)
            if target is None:
                continue
            if target not in builders:
                builders[target] = _builder_suffix(elf, target)
            suffix = builders[target]
            if suffix is None:
                continue
            seed_literal = None
            for previous in range(max(0, index - 10), index - 1):
                pair = _literal_pair(context[previous], context[previous + 1], reference + previous * 4)
                if pair and pair[0] == 1:
                    seed_literal = previous, pair[1]
            if seed_literal is not None:
                previous, seed_address = seed_literal
                # The most recent X1 literal is consumed by one FString
                # constructor before the builder receives that string in X0.
                calls = [_call(context[i], reference + i * 4) for i in range(previous + 2, index)]
                if sum(call is not None for call in calls) == 1:
                    try:
                        candidates.add((elf.string(seed_address), suffix))
                    except (ValueError, UnicodeError):
                        continue
    _require(len(candidates) == 1)
    seed, suffix = candidates.pop()
    return WrapperMaterial(seed, suffix, expected_native_sha256)


def _unique(pairs):
    value = {}
    for key, item in pairs:
        _require(key not in value)
        value[key] = item
    return value


def decode_wrapped_metadata(raw: bytes, material: WrapperMaterial) -> dict:
    """Decode one original metadata wrapper using source-derived material.

    ECB decoding is not an integrity/authentication check. Verify the wrapper's
    official transport/manifest owner separately. The original caller removes
    everything following the first NUL, including last-block allocation data.
    """
    _require(isinstance(raw, bytes) and 8 < len(raw) <= MAX_WRAPPED and raw.startswith(b'_XYLUAP_') and
             isinstance(material, WrapperMaterial) and 0 < len(material.seed_utf16) <= 512 and
             len(material.seed_utf16) % 2 == 0 and len(material.suffix) == 18)
    try:
        body = base64.b64decode(raw[8:], validate=True)
        _require(body and len(body) % 16 == 0)
        key = (hashlib.sha1(material.seed_utf16).digest() + material.suffix)[:32]
        decoded = AES.new(key, AES.MODE_ECB).decrypt(body)
        end = decoded.find(b'\0')
        if end >= 0:
            _require(0 < len(decoded) - end <= 16)
            decoded = decoded[:end]
        result = json.loads(decoded.decode('utf-8-sig'), object_pairs_hook=_unique,
                            parse_constant=lambda _value: _require(False))
        _require(isinstance(result, dict) and bool(result))
        return result
    except (ValueError, UnicodeError, RecursionError) as error:
        raise ValueError('Infinity Nikki original wrapped metadata is incomplete or has changed format.') from error
